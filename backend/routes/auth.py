# ============================================================
# FreqLearn Backend — routes/auth.py
# Registration, login, JWT access + refresh tokens
# ============================================================

import os
import re
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr

from db import get_db
from models import Learner, LearnerPreferences, LearnerStreak, RefreshToken
from mail import send_mail
from cookie_auth import (
    ACCESS_COOKIE, REFRESH_COOKIE,
    set_learner_cookies, clear_learner_cookies,
)

router = APIRouter()

JWT_SECRET  = os.getenv("JWT_SECRET", "change-this-in-production-please")
JWT_ALG     = "HS256"
ACCESS_EXP  = 30          # minutes
REFRESH_EXP = 30          # days


# ── Pydantic schemas ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:        EmailStr
    password:     str

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class RegisterResponse(BaseModel):
    """Registration no longer logs the learner in (2026-07-20 — gating access
    on email verification). No cookies are set on this response; the learner
    must click the emailed link, then log in normally."""
    ok:      bool = True
    email:   EmailStr
    message: str = "Check your inbox to verify your account."

class AuthResponse(BaseModel):
    """Tokens no longer travel in the body (P-SEC1, 2026-07-16) — they're set
    as httpOnly cookies by the route handler instead. Kept minimal for the
    frontend to update its own state."""
    learner_id:          int
    display_name:        str | None
    onboarding_complete: bool = False

class PatchMeRequest(BaseModel):
    bioregion:           str  | None = None
    display_name:        str  | None = None
    language:            str  | None = None
    onboarding_complete: bool | None = None


# ── Helpers ───────────────────────────────────────────────────

def make_access_token(learner_id: int) -> str:
    payload = {
        "sub": str(learner_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXP),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def make_refresh_token() -> str:
    return secrets.token_urlsafe(48)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

async def _generate_unique_username(db: AsyncSession, email: str) -> str:
    """Registration dropped the visible username field (2026-07-20 — email +
    password only). `Learner.username` is still unique/NOT NULL in the DB, so
    derive one from the email's local part and disambiguate on collision.
    Learners can still set a display_name in onboarding; this is only the
    internal unique handle."""
    base = re.sub(r"[^a-z0-9]", "", email.split("@")[0].lower())[:30] or "learner"
    candidate = base
    suffix = 0
    while True:
        result = await db.execute(select(Learner).where(Learner.username == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        suffix += 1
        candidate = f"{base}{suffix}"


# ── Email verification helpers ──────────────────────────────

_VERIFY_URL_BASE = os.getenv("FREQLEARN_VERIFY_URL_BASE", "https://build.onehouse.top")


def _generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def _send_verification_email(to_addr: str, display_name: str, token: str) -> None:
    link = f"{_VERIFY_URL_BASE}/app.html?token={token}"
    subject = "Verify your email — Surfing the Frequencies"
    body = (
        f"Hi {display_name},\n\n"
        "Time to Surf the Frequencies!\n\n"
        "Please verify your email address by clicking the link below:\n\n"
        f"{link}\n\n"
        "This link expires in 24 hours.\n\n"
        "Note: If you don't see this email in your inbox, please check your spam or junk folder.\n"
        "If you did not create this account, you can safely ignore this message.\n"
    )
    try:
        send_mail(to=to_addr, subject=subject, body=body)
    except Exception as e:
        logger = __import__("logging").getLogger("freqlearn.auth")
        logger.warning(f"Failed to send verification email to {to_addr}: {e}")


# ── Dependency: get current learner from the fl_access cookie ─

async def get_current_learner(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Learner:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        learner_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(Learner).where(Learner.id == learner_id))
    learner = result.scalar_one_or_none()
    if not learner or not learner.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Learner not found")

    # Update last_seen
    learner.last_seen_at = datetime.now(timezone.utc)
    return learner


# ── Routes ────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse)
async def register(
    req: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        existing = await db.execute(
            select(Learner).where(Learner.email == req.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="An account with this email already exists")

        username = await _generate_unique_username(db, req.email)
        hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

        learner = Learner(
            username=username,
            email=req.email,
            password_hash=hashed,
        )
        db.add(learner)
        await db.flush()

        token = _generate_verification_token()
        learner.verification_token = token
        learner.verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

        db.add(LearnerPreferences(learner_id=learner.id))
        db.add(LearnerStreak(learner_id=learner.id))

        await db.commit()

        # Send verification email in background (don't block the response)
        background_tasks.add_task(
            _send_verification_email,
            learner.email,
            username,
            token,
        )

        # 2026-07-20: registration no longer logs the learner in. Previously
        # this set login cookies immediately, so a fresh signup skipped email
        # verification entirely (login() checks email_verified, but register()
        # never did) — new accounts got full access without ever confirming
        # the address. Now: no cookies, no refresh token issued here; the
        # learner must click the emailed link, then log in normally.
        return RegisterResponse(email=learner.email)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {type(e).__name__}: {str(e)[:200]}",
        )


@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """
    Verify email using the token sent during registration.
    Returns {ok: True} on success, 400 on invalid/expired token.
    """
    try:
        result = await db.execute(
            select(Learner).where(Learner.verification_token == token)
        )
        learner = result.scalar_one_or_none()
        if not learner:
            raise HTTPException(status_code=400, detail="Invalid verification token")

        # verification_expires comes back from MariaDB as a naive datetime (the
        # column isn't DateTime(timezone=True)) even though it was written from
        # an aware datetime.now(timezone.utc) at registration — MySQL just stores
        # the wall-clock value. Comparing it directly against an aware "now"
        # raises TypeError ("can't compare offset-naive and offset-aware
        # datetimes"), which was silently 500ing this endpoint uncaught. Strip
        # tzinfo off "now" to match what's actually stored, rather than changing
        # the column type (bigger migration, not needed just for this).
        if learner.verification_expires and learner.verification_expires < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(status_code=400, detail="Verification link has expired")

        learner.email_verified = True
        learner.verification_token = None
        learner.verification_expires = None
        await db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {type(e).__name__}: {str(e)[:200]}",
        )


@router.post("/resend-verification")
async def resend_verification(
    req: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Re-send verification email. Body: {"email": "..."}.
    Returns 429 if a recent email was already sent.
    """
    email = req.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    result = await db.execute(
        select( Learner).where(Learner.email == email, Learner.email_verified == False)
    )
    learner = result.scalar_one_or_none()
    if not learner:
        # Don't reveal whether email exists
        return {"ok": True, "message": "If an unverified account exists, a verification email has been sent."}

    # Basic rate limit: don't resend if one was sent in the last 5 minutes
    # (In production you'd store sent_at; for now we rely on the fact that
    #  each call sets a new token.)
    token = _generate_verification_token()
    learner.verification_token = token
    learner.verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    await db.commit()

    background_tasks.add_task(
        _send_verification_email,
        learner.email,
        learner.display_name or learner.username,
        token,
    )
    return {"ok": True, "message": "Verification email sent."}


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Learner).where(Learner.email == req.email))
    learner = result.scalar_one_or_none()

    if not learner or not bcrypt.checkpw(req.password.encode(), learner.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not learner.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")

    if not learner.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")

    refresh_raw = make_refresh_token()
    db.add(RefreshToken(
        learner_id=learner.id,
        token_hash=hash_token(refresh_raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_EXP)
    ))
    await db.commit()

    set_learner_cookies(response, make_access_token(learner.id), refresh_raw)
    return AuthResponse(
        learner_id=learner.id,
        display_name=learner.display_name,
        onboarding_complete=bool(learner.onboarding_complete),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="No refresh token")

    hashed = hash_token(raw)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashed,
            RefreshToken.expires_at > datetime.now(timezone.utc)
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        clear_learner_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    await db.delete(stored)  # rotate — one use only

    new_refresh = make_refresh_token()
    db.add(RefreshToken(
        learner_id=stored.learner_id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_EXP)
    ))
    await db.commit()

    learner = await db.get(Learner, stored.learner_id)
    set_learner_cookies(response, make_access_token(stored.learner_id), new_refresh)
    return AuthResponse(
        learner_id=stored.learner_id,
        display_name=learner.display_name if learner else None,
        onboarding_complete=bool(learner.onboarding_complete) if learner else False,
    )


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        hashed = hash_token(raw)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hashed))
        stored = result.scalar_one_or_none()
        if stored:
            await db.delete(stored)
            await db.commit()
    clear_learner_cookies(response)
    return {"ok": True}

@router.patch("/me")
async def patch_me(
    req: PatchMeRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    """Update mutable learner fields. Currently: bioregion, display_name, language."""
    updated = False
    if req.bioregion is not None:
        learner.bioregion    = req.bioregion.strip() or None
        updated = True
    if req.display_name is not None:
        learner.display_name = req.display_name.strip() or learner.display_name
        updated = True
    if req.language is not None:
        learner.language     = req.language.strip() or learner.language
        updated = True
    if req.onboarding_complete is not None:
        learner.onboarding_complete = req.onboarding_complete
        updated = True
    if updated:
        await db.commit()
    return {"ok": True}
