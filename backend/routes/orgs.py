# ============================================================
# FreqLearn — routes/orgs.py
# Organization auth + listing management
#
# SETUP REQUIRED (one-time SQL before deploying):
#   ALTER TABLE organizations
#       ADD COLUMN password_hash VARCHAR(255) NULL,
#       ADD COLUMN org_token_secret VARCHAR(100) NULL;
#
# Register in main.py:
#   from routes.orgs import router as orgs_router
#   app.include_router(orgs_router, prefix="/api/orgs", tags=["orgs"])
#
# Endpoints:
#   POST /api/orgs/register              — register a new org account
#   POST /api/orgs/login                 — login → org access token
#   GET  /api/orgs/me                    — get org profile
#   PATCH /api/orgs/me                   — update org profile
#   GET  /api/orgs/me/listings           — list this org's listings
#   POST /api/orgs/listings              — create a listing
#   PATCH /api/orgs/listings/{id}        — update a listing
#   DELETE /api/orgs/listings/{id}       — delete a listing
#   GET  /api/orgs/listings/{id}/matches — who expressed interest
#   GET  /api/orgs/messages/{match_id}   — Pnyx thread (org side)
#   POST /api/orgs/messages/{match_id}   — send message to learner
# ============================================================

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

import bcrypt
import jwt

from db import get_db
from models import Organization, OpportunityListing, OpportunityMatch, Learner, Message
from cookie_auth import ORG_ACCESS_COOKIE, set_org_cookies, clear_org_cookies

router = APIRouter()

ORG_JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
ORG_JWT_ALG    = "HS256"
ORG_TOKEN_EXP  = timedelta(days=30)


# ── Auth helpers ───────────────────────────────────────────

def _hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def _check_pw(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def _make_token(org_id: int) -> str:
    payload = {
        "sub":  f"org:{org_id}",
        "exp":  datetime.now(timezone.utc) + ORG_TOKEN_EXP,
        "type": "org",
    }
    return jwt.encode(payload, ORG_JWT_SECRET, algorithm=ORG_JWT_ALG)

def _decode_token(token: str) -> dict:
    return jwt.decode(token, ORG_JWT_SECRET, algorithms=[ORG_JWT_ALG])


async def get_current_org(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Dependency: validates org access token from the fl_org_access httpOnly
    cookie (2026-07-16, P-SEC1 — previously a Bearer header, script-readable
    when stashed in localStorage)."""
    token = request.cookies.get(ORG_ACCESS_COOKIE)
    if not token:
        raise HTTPException(401, "Org token required")
    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

    if payload.get("type") != "org":
        raise HTTPException(401, "Not an org token")

    org_id = int(payload["sub"].split(":")[1])
    result = await db.execute(
        select(Organization).where(Organization.id == org_id, Organization.is_active == True)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(401, "Organization not found or inactive")
    return org


# ── Pydantic models ────────────────────────────────────────

class OrgRegister(BaseModel):
    name:          str
    email:         str
    password:      str
    org_type:      str = "other"    # ngo | educational | cooperative | community | social_enterprise | other
    website:       Optional[str] = None
    description:   Optional[str] = None

class OrgLogin(BaseModel):
    email:    str
    password: str

class OrgUpdate(BaseModel):
    name:          Optional[str] = None
    description:   Optional[str] = None
    website:       Optional[str] = None
    contact_email: Optional[str] = None
    org_type:      Optional[str] = None

class ListingCreate(BaseModel):
    title:         str
    description:   Optional[str] = None
    listing_type:  str = "project"  # volunteer | job | project | internship
    required_arts: list[str] = []   # list of art slugs
    source_url:    Optional[str] = None
    phase_min:     Optional[int] = None
    phase_max:     Optional[int] = None

class ListingUpdate(BaseModel):
    title:         Optional[str] = None
    description:   Optional[str] = None
    listing_type:  Optional[str] = None
    required_arts: Optional[list[str]] = None
    source_url:    Optional[str] = None
    is_active:     Optional[bool] = None

class MessageIn(BaseModel):
    body: str


# ── Serialisers ────────────────────────────────────────────

def _org_dict(org: Organization) -> dict:
    return {
        "id":            org.id,
        "name":          org.name,
        "slug":          org.slug,
        "description":   org.description,
        "website":       org.website,
        "contact_email": org.contact_email,
        "org_type":      org.org_type,
        "is_verified":   org.is_verified,
        "created_at":    org.created_at.isoformat() if org.created_at else None,
    }

def _listing_dict(listing: OpportunityListing) -> dict:
    required = listing.required_arts or []
    if isinstance(required, dict):
        required = list(required.keys())
    return {
        "id":              listing.id,
        "title":           listing.title,
        "description":     listing.description,
        "listing_type":    listing.listing_type,
        "required_arts":   required,
        "source_url":      listing.source_url,
        "is_active":       listing.is_active,
        "pending_approval": not listing.is_active and not listing.scavenged,
        "created_at":      listing.created_at.isoformat() if listing.created_at else None,
    }


# ── Auth endpoints ─────────────────────────────────────────

import re, unicodedata

def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")


@router.post("/register")
async def register_org(req: OrgRegister, response: Response, db: AsyncSession = Depends(get_db)):
    """Register a new organization account."""
    if not req.name.strip() or not req.email.strip() or not req.password:
        raise HTTPException(400, "name, email, and password are required")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    # Check email uniqueness
    existing = await db.execute(
        select(Organization).where(Organization.contact_email == req.email.strip().lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "An organization with this email already exists")

    # Generate unique slug
    base_slug = _slugify(req.name)
    slug = base_slug
    n = 1
    while True:
        chk = await db.execute(select(Organization).where(Organization.slug == slug))
        if not chk.scalar_one_or_none():
            break
        slug = f"{base_slug}-{n}"
        n += 1

    org = Organization(
        name=req.name.strip(),
        slug=slug,
        description=req.description,
        website=req.website,
        contact_email=req.email.strip().lower(),
        org_type=req.org_type,
        password_hash=_hash_pw(req.password),
        is_verified=False,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)

    set_org_cookies(response, _make_token(org.id))
    return {
        "ok":  True,
        "org": _org_dict(org),
    }


@router.post("/login")
async def login_org(req: OrgLogin, response: Response, db: AsyncSession = Depends(get_db)):
    """Login and receive an org access token (set as an httpOnly cookie)."""
    result = await db.execute(
        select(Organization).where(
            Organization.contact_email == req.email.strip().lower(),
            Organization.is_active == True,
        )
    )
    org = result.scalar_one_or_none()

    if not org or not org.password_hash:
        raise HTTPException(401, "Invalid credentials")
    if not _check_pw(req.password, org.password_hash):
        raise HTTPException(401, "Invalid credentials")

    set_org_cookies(response, _make_token(org.id))
    return {
        "ok":  True,
        "org": _org_dict(org),
    }


@router.post("/logout")
async def logout_org(response: Response):
    """Org access tokens are single long-lived tokens (no server-side refresh
    record), so logout just clears the cookies client-side."""
    clear_org_cookies(response)
    return {"ok": True}


# ── Org profile ────────────────────────────────────────────

@router.get("/me")
async def get_me(org: Organization = Depends(get_current_org)):
    return _org_dict(org)


@router.patch("/me")
async def update_me(
    req: OrgUpdate,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    if req.name:          org.name          = req.name.strip()
    if req.description:   org.description   = req.description
    if req.website:       org.website        = req.website
    if req.contact_email: org.contact_email  = req.contact_email.strip().lower()
    if req.org_type:      org.org_type       = req.org_type
    await db.commit()
    return _org_dict(org)


# ── Listing management ─────────────────────────────────────

@router.get("/me/listings")
async def get_my_listings(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OpportunityListing)
        .where(OpportunityListing.org_id == org.id)
        .order_by(OpportunityListing.created_at.desc())
    )
    listings = result.scalars().all()

    # Augment each listing with its match count
    out = []
    for l in listings:
        d = _listing_dict(l)
        matches_q = await db.execute(
            select(OpportunityMatch).where(OpportunityMatch.listing_id == l.id)
        )
        d["match_count"] = len(matches_q.scalars().all())
        out.append(d)
    return out


@router.post("/listings")
async def create_listing(
    req: ListingCreate,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    if not req.title.strip():
        raise HTTPException(400, "Title is required")
    if req.listing_type not in ("volunteer", "job", "project", "internship"):
        raise HTTPException(400, "listing_type must be volunteer | job | project | internship")

    listing = OpportunityListing(
        org_id=org.id,
        title=req.title.strip(),
        description=req.description,
        listing_type=req.listing_type,
        required_skills={},
        required_arts=req.required_arts,
        phase_min=req.phase_min,
        phase_max=req.phase_max,
        source_url=req.source_url,
        is_active=False,   # pending admin approval
        scavenged=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return {"ok": True, "listing": _listing_dict(listing)}


@router.patch("/listings/{listing_id}")
async def update_listing(
    listing_id: int,
    req: ListingUpdate,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")

    if req.title         is not None: listing.title         = req.title.strip()
    if req.description   is not None: listing.description   = req.description
    if req.listing_type  is not None: listing.listing_type  = req.listing_type
    if req.required_arts is not None: listing.required_arts = req.required_arts
    if req.source_url    is not None: listing.source_url    = req.source_url
    if req.is_active     is not None: listing.is_active     = req.is_active

    await db.commit()
    return {"ok": True, "listing": _listing_dict(listing)}


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")

    # Soft-delete by deactivating rather than hard delete
    # (preserves existing match records and messages)
    listing.is_active = False
    await db.commit()
    return {"ok": True}


@router.get("/listings/{listing_id}/matches")
async def get_listing_matches(
    listing_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Returns all learners who expressed interest in this listing."""
    # Verify org owns this listing
    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    if not listing_q.scalar_one_or_none():
        raise HTTPException(404, "Listing not found")

    matches_q = await db.execute(
        select(OpportunityMatch)
        .where(OpportunityMatch.listing_id == listing_id)
        .order_by(OpportunityMatch.matched_at.desc())
    )
    matches = matches_q.scalars().all()

    out = []
    for m in matches:
        learner_q = await db.execute(
            select(Learner).where(Learner.id == m.learner_id)
        )
        learner = learner_q.scalar_one_or_none()
        out.append({
            "match_id":      m.id,
            "learner_id":    m.learner_id,
            "display_name":  learner.display_name if learner else "—",
            "avatar_emoji":  learner.avatar_emoji if learner else "🌱",
            "avatar_color":  learner.avatar_color if learner else "#1D9E75",
            "learner_status": m.learner_status,
            "org_status":    m.org_status,
            "match_score":   m.match_score,
            "matched_at":    m.matched_at.isoformat() if m.matched_at else None,
        })
    return out


@router.patch("/listings/{listing_id}/matches/{match_id}")
async def update_match_status(
    listing_id: int,
    match_id: int,
    data: dict,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Org updates its status on a match: pending | reviewing | connected | declined."""
    valid_statuses = ("pending", "reviewing", "connected", "declined")
    new_status = data.get("org_status")
    if new_status not in valid_statuses:
        raise HTTPException(400, f"org_status must be one of: {valid_statuses}")

    # Verify listing belongs to org
    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    if not listing_q.scalar_one_or_none():
        raise HTTPException(404, "Listing not found")

    match_q = await db.execute(
        select(OpportunityMatch).where(
            OpportunityMatch.id == match_id,
            OpportunityMatch.listing_id == listing_id,
        )
    )
    match = match_q.scalar_one_or_none()
    if not match:
        raise HTTPException(404, "Match not found")

    match.org_status = new_status
    await db.commit()
    return {"ok": True, "org_status": new_status}


# ── Pnyx (org side) ────────────────────────────────────────

@router.get("/messages/{match_id}")
async def get_thread(
    match_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Get Pnyx messages for a match. Org must own the listing."""
    match_q = await db.execute(
        select(OpportunityMatch).where(OpportunityMatch.id == match_id)
    )
    match = match_q.scalar_one_or_none()
    if not match:
        raise HTTPException(404, "Match not found")

    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == match.listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    if not listing_q.scalar_one_or_none():
        raise HTTPException(403, "Not your listing")

    msgs_q = await db.execute(
        select(Message)
        .where(Message.match_id == match_id)
        .order_by(Message.created_at.asc())
    )
    msgs = msgs_q.scalars().all()
    return [
        {
            "id":          m.id,
            "sender_type": m.sender_type,
            "sender_id":   m.sender_id,
            "body":        m.body,
            "read_at":     m.read_at.isoformat() if m.read_at else None,
            "created_at":  m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]


@router.post("/messages/{match_id}")
async def send_message(
    match_id: int,
    req: MessageIn,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Org sends a message to a learner in a match thread."""
    if not req.body.strip():
        raise HTTPException(400, "Message body cannot be empty")

    match_q = await db.execute(
        select(OpportunityMatch).where(OpportunityMatch.id == match_id)
    )
    match = match_q.scalar_one_or_none()
    if not match:
        raise HTTPException(404, "Match not found")

    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == match.listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    if not listing_q.scalar_one_or_none():
        raise HTTPException(403, "Not your listing")

    msg = Message(
        match_id=match_id,
        sender_type="org",
        sender_id=org.id,
        body=req.body.strip(),
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return {
        "ok":          True,
        "id":          msg.id,
        "sender_type": "org",
        "body":        msg.body,
        "created_at":  msg.created_at.isoformat(),
    }
