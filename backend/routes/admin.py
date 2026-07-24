# ============================================================
# FreqLearn — routes/admin.py
# Admin-only endpoints (X-Admin-Key auth)
#
# ENV REQUIRED:
#   ADMIN_KEY=<your-secret>   — set in /var/www/freqlearn/backend/.env
#
# Register in main.py:
#   from routes.admin import router as admin_router
#   app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
#
# Endpoints:
#   GET    /api/admin/scavenger/listings            — ALL pending/live listings (scavenged AND
#                                                       org-submitted — see 2026-07-17 fix note below)
#   POST   /api/admin/scavenger/run                 — AI scavenger run → inserts listings
#   PATCH  /api/admin/scavenger/listings/{id}/approve — approve (set is_active=1), any source
#   DELETE /api/admin/scavenger/listings/{id}       — hard delete; scavenged listings only
#                                                       (org-submitted listings can't be deleted
#                                                       here — see note below)
#   GET    /api/admin/coverage                      — Phase × Art session counts (P24)
#   GET    /api/admin/seed-profiles                 — read-only list of bioregion_seed_profiles (P_FIELDGUIDE)
#   GET    /api/admin/learners                      — all learners with streak/XP stats (real data)
#
# FIX 2026-07-17 (found during P2 org+Polis end-to-end test build):
#   Org-submitted listings (orgs.py POST /api/orgs/listings sets scavenged=False,
#   is_active=False, "pending admin approval") were UNAPPROVABLE — the only admin
#   listing endpoints filtered `scavenged == True`, so an org-submitted listing
#   never appeared in `GET /scavenger/listings` and could never be PATCHed live.
#   Orgs could register, log in, and submit a listing that would then sit inactive
#   forever with zero admin-visible path to activate it. Fixed by dropping the
#   `scavenged == True` filter from the list/approve endpoints below (both sources
#   now show up, each tagged with a `source` field so admin can tell them apart);
#   DELETE (hard-delete/reject) stays scavenged-only since destroying a real org's
#   submitted data isn't the right "reject" behavior — an org listing that isn't
#   approved just stays inactive.
#   GET    /api/admin/coverage                      — Phase × Art session counts (P24)
#   GET    /api/admin/seed-profiles                 — read-only list of bioregion_seed_profiles (P_FIELDGUIDE)
#   GET    /api/admin/learners                      — all learners with streak/XP stats (real data)
# ============================================================

import os
import re
import json
import secrets
import asyncio
import logging
import httpx
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, desc
from typing import Optional
from jose import jwt, JWTError
from pydantic import BaseModel

from db import get_db
from models import OpportunityListing, Organization, Lecko, Arts, DevPhase, Session, OutreachDraft
from routes.weekly_report import main as weekly_report_main
from cookie_auth import ADMIN_ACCESS_COOKIE, set_admin_cookies, clear_admin_cookies
from mail import send_mail

logger = logging.getLogger("freqlearn.admin")

router = APIRouter()

ADMIN_KEY        = os.getenv("ADMIN_KEY", "")
# ── Admin session signing (P-SEC2, 2026-07-17) ──────────────
# Reuses the same JWT_SECRET env var learner/org auth already sign with —
# not a new secret to manage, and admin-session JWTs carry their own
# "scope": "admin" claim so they can't be confused with a learner/org token
# even though the signing key is shared.
JWT_SECRET       = os.getenv("JWT_SECRET", "change-this-in-production-please")
JWT_ALG          = "HS256"
ADMIN_SESSION_EXP_MIN = 8 * 60   # 8 hours — admin re-logs-in after this, no refresh token (single trusted operator, not worth the complexity)
SCAVENGER_ORG_ID = 18   # organizations.id for 'freqlearn-scavenger'
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL       = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL         = "https://api.groq.com/openai/v1/chat/completions"

# Valid art slugs for the platform
VALID_ARTS = [
    "move", "eat", "feel", "notice", "express",
    "live", "listen", "give", "receive", "collaborate",
    "understand", "respect", "build", "grow", "consume",
]

VALID_TYPES = ("job", "internship", "volunteer", "project", "contract", "gig", "other")


# ── Auth dependency (P-SEC2, 2026-07-17) ────────────────────
# ADMIN_KEY itself is now only ever checked once, server-side, inside
# /login below. Every route below this line is gated on a short-lived
# signed session cookie instead — the raw ADMIN_KEY never travels back to
# the browser and is never stored client-side (fl_admin_key localStorage
# is retired). This mirrors get_current_learner in routes/auth.py: 401 for
# "not authenticated" (missing/invalid/expired cookie), not 403 — 403 is
# for "authenticated but not allowed," which doesn't apply here since
# there's only one admin role.

def require_admin(request: Request):
    token = request.cookies.get(ADMIN_ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        if payload.get("scope") != "admin":
            raise JWTError("wrong scope")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired admin session")


class AdminLoginRequest(BaseModel):
    admin_key: str


@router.post("/login")
async def admin_login(req: AdminLoginRequest, response: Response):
    if not ADMIN_KEY:
        raise HTTPException(500, "ADMIN_KEY not configured on server")
    # constant-time compare — this is a shared secret comparison, same class
    # of check as a password, worth doing properly even though it's a single
    # trusted operator today
    if not secrets.compare_digest(req.admin_key, ADMIN_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")
    token = jwt.encode(
        {
            "scope": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=ADMIN_SESSION_EXP_MIN),
            "iat": datetime.now(timezone.utc),
        },
        JWT_SECRET, algorithm=JWT_ALG,
    )
    set_admin_cookies(response, token)
    return {"ok": True}


@router.post("/logout")
async def admin_logout(response: Response):
    clear_admin_cookies(response)
    return {"ok": True}


@router.get("/session")
async def admin_session(_: None = Depends(require_admin)):
    """Cheap endpoint for the frontend to check 'am I still logged in?' on
    page load — the session cookie is httpOnly so JS can't just read it."""
    return {"ok": True}


# ── Serialiser ─────────────────────────────────────────────

def _listing_out(listing: OpportunityListing, org: Optional[Organization] = None) -> dict:
    required = listing.required_arts or []
    if isinstance(required, str):
        try:
            required = json.loads(required)
        except Exception:
            required = []
    return {
        "id":           listing.id,
        "title":        listing.title,
        "description":  listing.description or "",
        "listing_type": listing.listing_type,
        "required_arts": required,
        "source_url":   listing.source_url,
        "is_active":    bool(listing.is_active),
        "scavenged":    bool(listing.scavenged),
        # 2026-07-17: distinguishes AI-scavenged listings from real org
        # submissions in the shared review queue below (P2 fix).
        "source":       "scavenger" if listing.scavenged else "org",
        "org_id":       listing.org_id,
        "org_name":     org.name if org else None,
        "created_at":   listing.created_at.isoformat() if listing.created_at else None,
    }


# ── Routes ─────────────────────────────────────────────────

@router.get("/scavenger/listings")
async def get_scavenged_listings(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return all listings pending/live review — both AI-scavenged AND
    org-submitted (2026-07-17 fix, see module docstring). Each item's
    `source` field ("scavenger" | "org") tells the two apart."""
    rows = (await db.execute(
        select(OpportunityListing)
        .order_by(OpportunityListing.created_at.desc())
    )).scalars().all()
    org_ids = {r.org_id for r in rows if r.org_id}
    orgs = {}
    if org_ids:
        org_rows = (await db.execute(
            select(Organization).where(Organization.id.in_(org_ids))
        )).scalars().all()
        orgs = {o.id: o for o in org_rows}
    return [_listing_out(r, orgs.get(r.org_id)) for r in rows]


@router.post("/scavenger/run")
async def run_scavenger(
    data: dict = {},
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Ask Claude to generate realistic opportunity listings that match
    the 15 Arts of Living. Inserts them with is_active=False (pending review).
    Optional body: { "count": 5, "focus": "NGO volunteer roles in Southeast Asia" }
    """
    count = min(int(data.get("count", 5)), 10)
    focus = data.get("focus", "NGO, educational, cooperative, and community opportunities globally")

    prompt = f"""You are a scout for Surfing the Frequencies, a free lifelong learning platform built around 15 "Arts of Living":
move, eat, feel, notice, express, live, listen, give, receive, collaborate, understand, respect, build, grow, consume.

Generate {count} realistic opportunity listings (jobs, volunteer roles, internships, projects) that organisations actually post.
Focus area: {focus}

For each listing return a JSON object with these exact keys:
- title: string (specific role title, not generic)
- description: string (2-3 sentences, what the person will actually do)
- listing_type: one of: job | internship | volunteer | project | contract | gig | other
- required_arts: array of 2-5 art slugs from this list only: {', '.join(VALID_ARTS)}
- source_url: a plausible URL (real org website or careers page if you know it, otherwise null)

Return ONLY a JSON array of {count} objects. No preamble, no markdown, no explanation."""

    if not GROQ_API_KEY:
        raise HTTPException(503, "GROQ_API_KEY not configured — add it to .env")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a scout for Surfing the Frequencies, a free lifelong learning platform. "
                    "You always respond with valid JSON only. No preamble, no markdown, no explanation."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens":  2000,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GROQ_URL, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.ConnectError:
        logger.error("Scavenger: cannot reach Groq API")
        raise HTTPException(502, "Cannot reach Groq API")
    except httpx.HTTPStatusError as e:
        logger.error(f"Scavenger Groq HTTP error: {e.response.status_code}")
        if e.response.status_code == 401:
            raise HTTPException(502, "Invalid GROQ_API_KEY")
        if e.response.status_code == 429:
            raise HTTPException(429, "Groq rate limit — try again in a minute")
        raise HTTPException(502, f"Groq API error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Scavenger Groq call failed: {e}")
        raise HTTPException(502, f"AI call failed: {str(e)}")

    data = response.json()
    raw  = data["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    # Extract JSON array if wrapped in object
    start = raw.find("[")
    end   = raw.rfind("]") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    try:
        listings_data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Scavenger JSON parse failed: {e}\nRaw: {raw[:500]}")
        raise HTTPException(502, "AI returned malformed JSON — try again")

    if not isinstance(listings_data, list):
        raise HTTPException(502, "AI returned unexpected format")

    inserted = []
    for item in listings_data:
        # Sanitise arts — only allow valid slugs
        arts = [a for a in (item.get("required_arts") or []) if a in VALID_ARTS]
        ltype = item.get("listing_type", "other")
        if ltype not in VALID_TYPES:
            ltype = "other"

        listing = OpportunityListing(
            org_id=SCAVENGER_ORG_ID,
            title=(item.get("title") or "Untitled")[:200],
            description=item.get("description"),
            listing_type=ltype,
            required_skills={},
            required_arts=arts,
            source_url=(item.get("source_url") or None),
            is_active=False,   # held for admin review
            scavenged=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(listing)
        inserted.append(listing)

    await db.commit()
    for l in inserted:
        await db.refresh(l)

    logger.info(f"Scavenger inserted {len(inserted)} listings (pending review)")
    return {
        "ok": True,
        "inserted": len(inserted),
        "listings": [_listing_out(l) for l in inserted],
    }


@router.patch("/scavenger/listings/{listing_id}/approve")
async def approve_listing(
    listing_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve a listing — makes it visible to learners. Works for both
    AI-scavenged and org-submitted listings (2026-07-17 fix — previously
    scoped to `scavenged == True` only, which left every org-submitted
    listing permanently unapprovable; see module docstring)."""
    listing = (await db.execute(
        select(OpportunityListing).where(OpportunityListing.id == listing_id)
    )).scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")

    listing.is_active = True
    await db.commit()
    logger.info(f"Listing {listing_id} approved (source={'scavenger' if listing.scavenged else 'org'})")
    org = None
    if listing.org_id:
        org = (await db.execute(
            select(Organization).where(Organization.id == listing.org_id)
        )).scalar_one_or_none()
    return {"ok": True, "listing": _listing_out(listing, org)}


@router.delete("/scavenger/listings/{listing_id}")
async def reject_listing(
    listing_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete a scavenged listing (safe — no learner matches exist while
    is_active=False). Deliberately scavenged-only (2026-07-17): unlike an
    AI-generated draft, an org-submitted listing is a real org's real
    submission — silently hard-deleting it isn't the right "reject" behavior.
    Leaving it inactive (the default state until approved) is reject enough;
    the org itself can also delete/deactivate its own listing via
    orgs.py DELETE /api/orgs/listings/{id}."""
    listing = (await db.execute(
        select(OpportunityListing).where(OpportunityListing.id == listing_id)
    )).scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    if not listing.scavenged:
        raise HTTPException(
            400,
            "This is an org-submitted listing, not an AI-scavenged draft — "
            "it can't be deleted from here. Leave it unapproved to keep it "
            "hidden, or ask the org to remove it themselves."
        )

    await db.delete(listing)
    await db.commit()
    logger.info(f"Scavenged listing {listing_id} rejected and deleted")
    return {"ok": True}


# ── Seed session endpoints ─────────────────────────────────

VENV_PYTHON  = "/var/www/freqlearn/backend/venv/bin/python3"
SEED_SCRIPT  = "/var/www/freqlearn/scripts/seed_sessions.py"

# In-memory job store (single admin user, one job at a time)
_seed_job: dict = {"running": False, "progress": 0, "total": 0,
                   "log": [], "done": False, "error": None}


def _parse_total(line: str) -> int | None:
    """Extract total session count from the summary header line."""
    m = re.search(r"Total:\s+(\d+)", line)
    return int(m.group(1)) if m else None


@router.get("/seed/status")
async def seed_status(_: None = Depends(require_admin)):
    """Poll this while a seed job is running."""
    return {
        "running":  _seed_job["running"],
        "progress": _seed_job["progress"],
        "total":    _seed_job["total"],
        "pct":      round(_seed_job["progress"] / _seed_job["total"] * 100)
                    if _seed_job["total"] else 0,
        "log":      _seed_job["log"][-40:],   # last 40 lines
        "done":     _seed_job["done"],
        "error":    _seed_job["error"],
    }


async def _run_seed(args: list[str]):
    """Run seed_sessions.py in a subprocess, updating _seed_job as lines arrive."""
    global _seed_job
    _seed_job.update({"running": True, "progress": 0, "total": 0,
                      "log": [], "done": False, "error": None})
    cmd = [VENV_PYTHON, SEED_SCRIPT] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            _seed_job["log"].append(line)
            logger.info(f"[seed] {line}")
            # Parse total from header
            if "Total:" in line:
                t = _parse_total(line)
                if t:
                    _seed_job["total"] = t
            # Count completed sessions (lines with ✓)
            if line.strip().startswith("✓") or " ✓ " in line:
                _seed_job["progress"] += 1
        await proc.wait()
        if proc.returncode != 0:
            _seed_job["error"] = f"Process exited with code {proc.returncode}"
    except Exception as e:
        _seed_job["error"] = str(e)
        logger.error(f"Seed subprocess error: {e}")
    finally:
        _seed_job["running"] = False
        _seed_job["done"]    = True


@router.post("/seed/dry-run")
async def seed_dry_run(
    data: dict = {},
    _: None = Depends(require_admin),
):
    """
    Dry run — calls AI, prints what would be generated, writes nothing to DB.
    Returns immediately with the full output (dry runs are fast — no DB writes,
    no 3s delays between calls).
    """
    arts   = data.get("arts", "")
    phases = data.get("phases", "")
    per    = str(data.get("per_art", 1))

    args = ["--dry-run", "--yes"]
    if arts:   args += ["--arts",    arts]
    if phases: args += ["--phases",  phases]
    args += ["--per-art", per]

    cmd = [VENV_PYTHON, SEED_SCRIPT] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        # Extract summary line
        summary = next((l for l in reversed(lines) if "Done:" in l), None)
        return {"ok": True, "lines": lines, "summary": summary}
    except asyncio.TimeoutError:
        raise HTTPException(504, "Dry run timed out after 120s")
    except Exception as e:
        raise HTTPException(502, f"Dry run failed: {e}")


@router.post("/seed/run")
async def seed_run(
    data: dict = {},
    _: None = Depends(require_admin),
):
    """
    Real run — generates sessions and writes to DB.
    Launches as background task; poll GET /api/admin/seed/status for progress.
    """
    global _seed_job
    if _seed_job["running"]:
        raise HTTPException(409, "A seed job is already running")

    arts   = data.get("arts", "")
    phases = data.get("phases", "")
    per    = str(data.get("per_art", 2))

    args = ["--yes"]
    if arts:   args += ["--arts",    arts]
    if phases: args += ["--phases",  phases]
    args += ["--per-art", per]

    # Fire and forget — frontend polls /seed/status
    asyncio.ensure_future(_run_seed(args))
    return {"ok": True, "message": f"Seed job started — poll /api/admin/seed/status for progress"}


# ── Coverage matrix (P24) ──────────────────────────────────

@router.get("/coverage")
async def get_coverage(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Phase × Art session counts for the admin coverage matrix.
    Returns up to 60 rows (15 arts × 4 phases) — much cheaper than
    shipping the full library to the browser for client-side counting.
    """
    result = await db.execute(text("""
        SELECT a.slug AS art_slug, dp.slug AS phase, COUNT(*) AS cnt
        FROM sessions s
        JOIN arts a       ON a.id  = s.art_id
        JOIN dev_phases dp ON dp.id = s.dev_phase_id
        WHERE s.dev_phase_id IS NOT NULL
          AND s.warmup_prompt IS NOT NULL
        GROUP BY a.slug, dp.slug
        ORDER BY a.sort_order, dp.sort_order
    """))
    rows = result.fetchall()
    return {
        "coverage": [
            {"art_slug": row[0], "phase": row[1], "count": int(row[2])}
            for row in rows
        ]
    }


# ── Bioregion seed profiles — read-only (P_FIELDGUIDE) ──────────────────────
# Layer 1 ("Where I Stand" dashboard card + public Field Guide tab) is
# author-curated, not AI-generated, so this is intentionally read-only.
# Uses SELECT * rather than named columns — bioregion_seed_profiles' exact
# schema hasn't been confirmed via DESCRIBE in this file, and a generic
# row→dict pass-through means this endpoint can't break on a column-name
# mismatch. The public GET /api/bioregions/seed-profiles endpoint (already
# live, unauthenticated) returns the same data — this route exists purely so
# the admin panel doesn't need a second round trip or a different auth model
# to show the same table.
#
# NOTE: write endpoints (create/update/delete) are intentionally NOT included
# here. Adding them safely requires confirming bioregion_seed_profiles'
# column names with DESCRIBE first — see MAINTENANCE.md gotchas.

@router.get("/seed-profiles")
async def get_seed_profiles_admin(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin view of all bioregion_seed_profiles rows (Layer 1, read-only)."""
    result = await db.execute(text("SELECT * FROM bioregion_seed_profiles ORDER BY id"))
    rows = result.mappings().all()
    return {"profiles": [dict(r) for r in rows]}


# ── Server logs tail ─────────────────────────────────────────
# Log files confirmed on server (2026-06-23):
#   /var/log/freqlearn/api.log        <- main uvicorn log
#   /var/log/freqlearn/api-error.log  <- error-only stream
# journalctl is NOT available on this host; we read the files directly.
_APP_LOG_KEYS = ["learning_progress", "session_start", "quiz_submit", "reflection_submit", "xp_award", "streak_update"]
_LOG_PATHS = [
    "/var/log/freqlearn/api.log",
    "/var/log/freqlearn/api-error.log",
]


def _find_tail() -> str | None:
    for candidate in ("/usr/bin/tail", "/bin/tail"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None

@router.get("/logs")
async def get_logs(
    _: None = Depends(require_admin),
    lines: int = Query(default=100, ge=10, le=500),
    which: str = Query(default="main", pattern="^(main|error)$"),
):
    """
    Tail the uvicorn log files directly.
    ``which=main`` → api.log, ``which=error`` → api-error.log.
    """
    paths = {"main": _LOG_PATHS[0], "error": _LOG_PATHS[1]}
    path = paths.get(which, _LOG_PATHS[0])
    tail_cmd = _find_tail()
    if not tail_cmd:
        return {
            "lines": [
                "tail binary not found at /usr/bin/tail or /bin/tail.",
                f"Manual: try 'tail -n {lines} {path}' on the host to verify access.",
            ],
            "source": "no-tail",
        }
    try:
        proc = await asyncio.create_subprocess_exec(
            tail_cmd, "-n", str(lines), path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:300]
            return {
                "lines": [f"tail exited {proc.returncode}: {err}"],
                "source": "tail-error",
                "path": path,
            }
        output = stdout.decode("utf-8", errors="replace")
        log_lines = [l.rstrip() for l in output.splitlines() if l.strip()]
        return {"lines": log_lines, "source": f"file:{path}", "which": which}
    except FileNotFoundError:
        return {"lines": ["tail not available"], "source": "none"}
    except asyncio.TimeoutError:
        return {"lines": ["Log fetch timed out after 10s"], "source": "timeout"}
    except Exception as e:
        return {"lines": [f"Error reading logs: {str(e)}"], "source": "error"}


# ── Dashboard stats ────────────────────────────────────────
@router.get("/stats")
async def get_stats(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregated platform stats for the admin dashboard.
    All counts are live DB queries; art activity is last-7-days.
    """
    rows = (await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM learners)                           AS learners_total,
            (SELECT COUNT(*) FROM learners WHERE created_at >= NOW() - INTERVAL 7 DAY) AS learners_week,
            (SELECT COUNT(*) FROM organizations)                      AS orgs_total,
            (SELECT COUNT(*) FROM opportunity_matches)                AS matches_total,
            (SELECT COUNT(*) FROM opportunity_matches
               WHERE matched_at >= NOW() - INTERVAL 7 DAY)            AS matches_week,
            (SELECT COUNT(*) FROM sessions WHERE status='completed')  AS sessions_total,
            (SELECT COUNT(*) FROM sessions
               WHERE status='completed' AND created_at >= NOW() - INTERVAL 7 DAY) AS sessions_week
    """))).mappings().first()

    art_rows = (await db.execute(text("""
        SELECT a.slug, COUNT(*) AS cnt
        FROM sessions s
        JOIN arts a ON a.id = s.art_id
        WHERE s.status = 'completed'
          AND s.created_at >= NOW() - INTERVAL 7 DAY
        GROUP BY a.id, a.slug
        ORDER BY cnt DESC
        LIMIT 6
    """))).mappings().all()

    max_art = max((r["cnt"] for r in art_rows), default=1)
    art_activity = [
        {
            "name": r["slug"],
            "count": int(r["cnt"]),
            "pct": round(int(r["cnt"]) / max_art * 100),
        }
        for r in art_rows
    ]

    recent_learners = (await db.execute(text("""
        SELECT username, display_name, created_at
        FROM learners
        ORDER BY created_at DESC
        LIMIT 5
    """))).mappings().all()

    recent_matches = (await db.execute(text("""
        SELECT om.id, om.matched_at,
               l.display_name AS learner_name,
               ol.title        AS listing_title
          FROM opportunity_matches om
          JOIN learners l          ON l.id = om.learner_id
          JOIN opportunity_listings ol ON ol.id = om.listing_id
      ORDER BY om.matched_at DESC
         LIMIT 5
    """))).mappings().all()

    return {
        "learners_total":  int(rows["learners_total"] or 0),
        "learners_week":   int(rows["learners_week"] or 0),
        "orgs_total":      int(rows["orgs_total"] or 0),
        "matches_total":   int(rows["matches_total"] or 0),
        "matches_week":    int(rows["matches_week"] or 0),
        "sessions_total":  int(rows["sessions_total"] or 0),
        "sessions_week":   int(rows["sessions_week"] or 0),
        "art_activity":    art_activity,
        "recent_learners": [
            {
                "username":     r["username"],
                "display_name": r["display_name"] or r["username"],
                "created_at":   r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_learners
        ],
        "recent_matches": [
            {
                "match_id":     r["id"],
                "matched_at":   r["matched_at"].isoformat() if r["matched_at"] else None,
                "learner_name": r["learner_name"],
                "listing_title": r["listing_title"],
            }
            for r in recent_matches
        ],
    }


# ── Learners (real data) ───────────────────────────────────
#
# Schema used — all columns confirmed via DESCRIBE learners (2026-06-23):
#   learners:        id, username, email, display_name (nullable), created_at,
#                    last_seen_at, bioregion, is_active, phase_id
#                    NOTE: no 'name' column — display name is 'display_name'
#   learner_streaks: learner_id, current_streak, longest_streak,
#                    total_sessions, total_xp, total_minutes, last_activity_date
#   sessions:        learner_id, art_id, status  (status='completed' confirmed enum value)
#   arts:            id, slug
#
# Top art is derived from completed sessions (most frequent art_id per learner)
# rather than learner_arts, whose schema has not been DESCRIBE'd in this file.
# This is also more accurate — it reflects what the learner actually completes.
#
# display_name is aliased as 'name' in the response; COALESCE with username so
# the field is never null even if the learner skipped setting a display name.

@router.get("/learners")
async def get_learners(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """All learners with denormalized streak/XP stats and derived top art."""
    result = await db.execute(text("""
        SELECT
            l.id,
            l.username,
            COALESCE(l.display_name, l.username) AS name,
            l.email,
            l.bioregion,
            l.is_active,
            l.created_at,
            l.last_seen_at,
            COALESCE(ls.current_streak,  0) AS current_streak,
            COALESCE(ls.longest_streak,  0) AS longest_streak,
            COALESCE(ls.total_sessions,  0) AS total_sessions,
            COALESCE(ls.total_xp,        0) AS total_xp,
            COALESCE(ls.total_minutes,   0) AS total_minutes,
            ls.last_activity_date,
            (SELECT a.slug
             FROM sessions s
             JOIN arts a ON a.id = s.art_id
             WHERE s.learner_id = l.id
               AND s.status = 'completed'
             GROUP BY s.art_id
             ORDER BY COUNT(*) DESC
             LIMIT 1) AS top_art
        FROM learners l
        LEFT JOIN learner_streaks ls ON ls.learner_id = l.id
        ORDER BY l.created_at DESC
    """))
    rows = result.mappings().all()
    return {
        "learners": [
            {
                "id":                 row["id"],
                "username":           row["username"],
                "name":               row["name"],
                "email":              row["email"],
                "created_at":         row["created_at"].isoformat() if row["created_at"] else None,
                "last_seen_at":       row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
                "bioregion":          row["bioregion"],
                "is_active":          bool(row["is_active"]),
                "current_streak":     int(row["current_streak"]),
                "longest_streak":     int(row["longest_streak"]),
                "total_sessions":     int(row["total_sessions"]),
                "total_xp":           int(row["total_xp"]),
                "total_minutes":      int(row["total_minutes"]),
                "last_activity_date": str(row["last_activity_date"]) if row["last_activity_date"] else None,
                "top_art":            row["top_art"],
            }
            for row in rows
        ]
    }


# ── Organizations (admin CRUD) ────────────────────────────

@router.get("/orgs")
async def list_orgs(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Organization).order_by(Organization.created_at.desc())
    )
    orgs = result.scalars().all()

    # Pre-fetch listing counts for each org
    counts = {}
    if orgs:
        count_rows = (await db.execute(text("""
            SELECT org_id, COUNT(*) AS cnt
            FROM opportunity_listings
            WHERE org_id IN :ids
            GROUP BY org_id
        """), {"ids": tuple(o.id for o in orgs)})).mappings().all()
        for r in count_rows:
            counts[r["org_id"]] = int(r["cnt"])

    return [
        {
            "id":            o.id,
            "name":          o.name,
            "slug":          o.slug,
            "contact_email": o.contact_email,
            "org_type":      o.org_type,
            "is_verified":   bool(o.is_verified),
            "is_active":     bool(o.is_active),
            "created_at":    o.created_at.isoformat() if o.created_at else None,
            "bioregion":     o.bioregion,
            "website":       o.website,
            "listing_count": counts.get(o.id, 0),
        }
        for o in orgs
    ]


@router.post("/orgs")
async def create_org(
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin creates an org. Required: name, contact_email.
    Optional: org_type, website, description, password.
    If password is provided the org can log in at /api/orgs/login.
    """
    name  = data.get("name", "").strip()
    email = data.get("contact_email", "").strip().lower()
    if not name or not email:
        raise HTTPException(400, "name and contact_email are required")

    dup = await db.execute(
        select(Organization).where(
            (Organization.contact_email == email) |
            (Organization.slug == _slugify(name))
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(409, "An organization with this email or slug already exists")

    slug = _slugify(name)
    n = 1
    while True:
        chk = await db.execute(select(Organization).where(Organization.slug == slug))
        if not chk.scalar_one_or_none():
            break
        slug = f"{_slugify(name)}-{n}"
        n += 1

    org = Organization(
        name=name,
        slug=slug,
        contact_email=email,
        org_type=data.get("org_type") or "other",
        website=data.get("website"),
        description=data.get("description"),
        bioregion=data.get("bioregion"),
        is_verified=bool(data.get("is_verified", False)),
        is_active=bool(data.get("is_active", True)),
        created_at=datetime.now(timezone.utc),
    )
    if data.get("password"):
        import bcrypt as _bc
        org.password_hash = _bc.hashpw(data["password"].encode(), _bc.gensalt()).decode()

    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "contact_email": org.contact_email,
    }


@router.patch("/orgs/{org_id}")
async def update_org(
    org_id: int,
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")

    for key in ("name", "org_type", "website", "description", "bioregion", "is_verified", "is_active"):
        if key in data:
            setattr(org, key, data[key])

    if "contact_email" in data:
        org.contact_email = data["contact_email"].strip().lower()
    if "name" in data and data["name"].strip():
        org.slug = _slugify(data["name"].strip())

    await db.commit()
    await db.refresh(org)
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "contact_email": org.contact_email,
    }


@router.delete("/orgs/{org_id}")
async def delete_org(
    org_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")

    org.is_active = False
    org.password_hash = None
    await db.commit()
    return {"ok": True}


@router.get("/orgs/{org_id}/listings")
async def org_listings(
    org_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OpportunityListing)
        .where(OpportunityListing.org_id == org_id)
        .order_by(OpportunityListing.created_at.desc())
    )
    listings = result.scalars().all()
    return [
        {
            "id":          l.id,
            "title":       l.title,
            "listing_type":l.listing_type,
            "is_active":   bool(l.is_active),
            "created_at":  l.created_at.isoformat() if l.created_at else None,
        }
        for l in listings
    ]


def _slugify(text: str) -> str:
    import re, unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")


# ── LECKO library (admin catalog) ────────────────────────
@router.get("/leckos")
async def admin_list_leckos(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """List all LECKOs, optionally filtered by active status."""
    q = select(Lecko)
    if active_only:
        q = q.where(Lecko.is_active == True)
    q = q.order_by(desc(Lecko.utility_score), desc(Lecko.created_at))
    result = await db.execute(q)
    leckos = result.scalars().all()

    arts_q = await db.execute(select(Arts))
    art_map = {a.id: a.name for a in arts_q.scalars().all()}
    ph_q = await db.execute(select(DevPhase))
    ph_map = {p.id: p.name for p in ph_q.scalars().all()}

    return [
        {
            "id": l.id,
            "title": l.title,
            "art_id": l.art_id,
            "art_name": art_map.get(l.art_id, ""),
            "phase_id": l.phase_id,
            "phase_name": ph_map.get(l.phase_id, ""),
            "skill_type": l.skill_type,
            "assessment_type": l.assessment_type,
            "community_need": l.community_need,
            "source_credit": l.source_credit,
            "evidence_url": l.evidence_url,
            "utility_score": l.utility_score,
            "is_active": bool(l.is_active),
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in leckos
    ]


@router.patch("/leckos/{lecko_id}")
async def admin_update_lecko(
    lecko_id: int,
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle LECKO active/inactive or update fields."""
    result = await db.execute(select(Lecko).where(Lecko.id == lecko_id))
    lecko = result.scalar_one_or_none()
    if not lecko:
        raise HTTPException(404, "LECKO not found")

    for key in ("title", "description", "learning_domain", "skill_type", "assessment_type", "assessment_desc", "community_need", "source_credit", "evidence_url", "utility_score"):
        if key in data:
            setattr(lecko, key, data[key])

    if "is_active" in data:
        lecko.is_active = bool(data["is_active"])

    if "art_id" in data:
        lecko.art_id = int(data["art_id"])
    if "phase_id" in data:
        lecko.phase_id = int(data["phase_id"])

    await db.commit()
    await db.refresh(lecko)
    return {"ok": True, "id": lecko.id, "is_active": lecko.is_active}


# ── Reports ────────────────────────────────────────────────
@router.post("/reports/weekly")
async def trigger_weekly_report(
    _: None = Depends(require_admin),
):
    try:
        await weekly_report_main()
        return {"ok": True, "message": "Weekly report sent"}
    except Exception as e:
        raise HTTPException(500, f"Report failed: {str(e)}")


# Platform Settings (Admin Settings persistence)
# Added 2026-06-27 -- backed by platform_settings table (see scripts/2026-06-27-platform-settings.sql)
@router.get("/settings")
async def admin_get_settings(_: None = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT key_name, value, category, description FROM platform_settings ORDER BY category, key_name"))
    rows = result.fetchall()
    return {
        "settings": {row.key_name: {"value": row.value, "category": row.category, "description": row.description} for row in rows},
        "count": len(rows),
    }


@router.patch("/settings")
async def admin_update_settings(
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = data.get("settings", {})
    if not isinstance(settings, dict) or not settings:
        raise HTTPException(400, "Body must be {'settings': {key: value, ...}}")

    updated = 0
    for key, value in settings.items():
        result = await db.execute(text("SELECT id FROM platform_settings WHERE key_name = :k"), {"k": key})
        if not result.fetchone():
            await db.execute(
                text("INSERT INTO platform_settings (key_name, value, category) VALUES (:k, :v, 'general') ON DUPLICATE KEY UPDATE value = :v"),
                {"k": key, "v": str(value)},
            )
        else:
            await db.execute(
                text("UPDATE platform_settings SET value = :v, updated_at = NOW() WHERE key_name = :k"),
                {"k": key, "v": str(value)},
            )
        updated += 1

    await db.commit()
    return {"ok": True, "updated": updated}


@router.post("/settings/{key_name}")
async def admin_set_single_setting(
    key_name: str,
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if "value" not in data:
        raise HTTPException(400, "Body must contain value field")
    value = str(data["value"])
    await db.execute(
        text('INSERT INTO platform_settings (key_name, value, category) VALUES (:k, :v, \'general\') ON DUPLICATE KEY UPDATE value = :v, updated_at = NOW()'),
        {"k": key_name, "v": value},
    )
    await db.commit()
    return {"ok": True, "key": key_name, "value": value}


@router.delete("/settings/{key_name}")
async def admin_delete_setting(
    key_name: str,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(text("DELETE FROM platform_settings WHERE key_name = :k"), {"k": key_name})
    await db.commit()
    return {"ok": True, "deleted": key_name}


# Admin Sessions Library (template browser for AI generation)
# Added 2026-06-27 -- browse the seed/template library that powers AI session generation
@router.get("/sessions")
async def admin_list_sessions(
    limit: int = 50,
    offset: int = 0,
    art_id: Optional[int] = None,
    dev_phase_id: Optional[int] = None,
    q: Optional[str] = None,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List sessions in the library (template browser). Paginated."""
    from sqlalchemy import or_, func

    # Build base query
    q1 = select(Session).where(Session.completed_at.is_(None))  # Library = uncompleted sessions
    count_q = select(func.count(Session.id)).where(Session.completed_at.is_(None))

    if art_id:
        q1 = q1.where(Session.art_id == art_id)
        count_q = count_q.where(Session.art_id == art_id)
    if dev_phase_id:
        q1 = q1.where(Session.dev_phase_id == dev_phase_id)
        count_q = count_q.where(Session.dev_phase_id == dev_phase_id)
    if q:
        like_q = f"%{q}%"
        q1 = q1.where(or_(Session.title.like(like_q), Session.warmup_prompt.like(like_q)))
        count_q = count_q.where(or_(Session.title.like(like_q), Session.warmup_prompt.like(like_q)))

    # Count total
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page
    result = await db.execute(
        q1.order_by(desc(Session.created_at)).offset(offset).limit(limit)
    )
    sessions = result.scalars().all()

    # Get art and skill names for display
    arts_q = await db.execute(select(Arts))
    art_map = {a.id: a.name for a in arts_q.scalars().all()}
    ph_q = await db.execute(select(DevPhase))
    ph_map = {p.id: p.name for p in ph_q.scalars().all()}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "art_id": s.art_id,
                "art_name": art_map.get(s.art_id, ""),
                "dev_phase_id": s.dev_phase_id,
                "dev_phase_name": ph_map.get(s.dev_phase_id, ""),
                "primary_skill_id": s.primary_skill_id,
                "language": getattr(s, 'language', 'en'),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "warmup_preview": (s.warmup_prompt[:120] + "...") if s.warmup_prompt and len(s.warmup_prompt) > 120 else s.warmup_prompt,
            }
            for s in sessions
        ],
    }


@router.get("/sessions/{session_id}")
async def admin_get_session(
    session_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full session detail for editing."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    arts_q = await db.execute(select(Arts))
    art_map = {a.id: a.name for a in arts_q.scalars().all()}
    ph_q = await db.execute(select(DevPhase))
    ph_map = {p.id: p.name for p in ph_q.scalars().all()}

    return {
        "id": session.id,
        "title": session.title,
        "art_id": session.art_id,
        "art_name": art_map.get(session.art_id, ""),
        "dev_phase_id": session.dev_phase_id,
        "dev_phase_name": ph_map.get(session.dev_phase_id, ""),
        "primary_skill_id": session.primary_skill_id,
        "secondary_skill_ids": session.secondary_skill_ids,
        "recommended_by": session.recommended_by,
        "language": getattr(session, 'language', 'en'),
        "warmup_prompt": session.warmup_prompt,
        "explore_content": session.explore_content,
        "challenge_prompt": session.challenge_prompt,
        "reflect_prompt": session.reflect_prompt,
        "assess_question": session.assess_question,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.patch("/sessions/{session_id}")
async def admin_update_session(
    session_id: int,
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update session fields. Library templates only (completed_at is NULL)."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    if session.completed_at is not None:
        raise HTTPException(400, "Cannot edit completed sessions (use learner transcript tools instead)")

    editable = ("title", "warmup_prompt", "explore_content", "challenge_prompt",
                "reflect_prompt", "language")
    for key in editable:
        if key in data:
            setattr(session, key, data[key])

    if "art_id" in data:
        session.art_id = int(data["art_id"])
    if "dev_phase_id" in data:
        session.dev_phase_id = int(data["dev_phase_id"]) if data["dev_phase_id"] else None
    if "primary_skill_id" in data:
        session.primary_skill_id = int(data["primary_skill_id"])

    await db.commit()
    await db.refresh(session)
    return {"ok": True, "id": session.id}


@router.delete("/sessions/{session_id}")
async def admin_delete_session(
    session_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a library session template (only if completed_at IS NULL)."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    if session.completed_at is not None:
        raise HTTPException(400, "Cannot delete completed sessions")

    await db.delete(session)
    await db.commit()
    return {"ok": True, "deleted": session_id}

# ============================================================
# P9 — Outreach section (2026-07-24)
# Real review/send/discard mechanics for the admin Outreach queue.
# Charbel's call: placeholder seed data for now (see migration
# 2026-07-24-outreach-drafts.sql) — real org/learner auto-matching
# to populate this table is a separate, later scoping pass.
#
#   GET    /api/admin/outreach              — list drafts (pending first, then newest)
#   PATCH  /api/admin/outreach/{id}         — edit subject/body before sending
#   POST   /api/admin/outreach/{id}/send    — send via mail.send_mail(), mark sent
#   PATCH  /api/admin/outreach/{id}/discard — mark discarded (no hard delete)
# ============================================================

@router.get("/outreach")
async def admin_list_outreach(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """List outreach drafts, pending first, then most recent."""
    q = select(OutreachDraft).order_by(
        (OutreachDraft.status != "pending"),
        desc(OutreachDraft.created_at),
    )
    result = await db.execute(q)
    drafts = result.scalars().all()
    return [
        {
            "id": d.id,
            "org_name": d.org_name,
            "contact_email": d.contact_email,
            "match_count": d.match_count,
            "subject": d.subject,
            "body": d.body,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        }
        for d in drafts
    ]


@router.patch("/outreach/{draft_id}")
async def admin_update_outreach(
    draft_id: int,
    data: dict,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Edit a draft's subject/body before sending. Only pending drafts are editable."""
    result = await db.execute(select(OutreachDraft).where(OutreachDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Outreach draft not found")
    if draft.status != "pending":
        raise HTTPException(400, f"Cannot edit a draft that is already '{draft.status}'")

    for key in ("subject", "body"):
        if key in data:
            setattr(draft, key, data[key])

    await db.commit()
    return {"ok": True, "id": draft_id}


@router.post("/outreach/{draft_id}/send")
async def admin_send_outreach(
    draft_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Send the draft's current subject/body to contact_email, then mark sent."""
    result = await db.execute(select(OutreachDraft).where(OutreachDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Outreach draft not found")
    if draft.status != "pending":
        raise HTTPException(400, f"Draft is already '{draft.status}'")

    try:
        send_mail(to=draft.contact_email, subject=draft.subject, body=draft.body)
    except Exception as e:
        logger.error(f"Outreach send failed for draft {draft_id}: {e}")
        raise HTTPException(502, f"Send failed: {e}")

    draft.status = "sent"
    draft.sent_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "id": draft_id, "status": "sent"}


@router.patch("/outreach/{draft_id}/discard")
async def admin_discard_outreach(
    draft_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark a draft discarded. Soft — never hard-deleted."""
    result = await db.execute(select(OutreachDraft).where(OutreachDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Outreach draft not found")
    if draft.status != "pending":
        raise HTTPException(400, f"Draft is already '{draft.status}'")

    draft.status = "discarded"
    await db.commit()
    return {"ok": True, "id": draft_id, "status": "discarded"}
