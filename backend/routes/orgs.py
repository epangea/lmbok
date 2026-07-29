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
#   GET  /api/orgs/listings/{id}/matches — who expressed interest (+ anonymized AI candidates)
#   GET  /api/orgs/messages/{match_id}   — Pnyx thread (org side)
#   POST /api/orgs/messages/{match_id}   — send message to learner
#   POST /api/orgs/listings/{id}/parse-needs      — P11: AI parses needs_text -> skill targets
#   POST /api/orgs/listings/{id}/generate-matches — P11: rank learners, create top-10 ai_suggested matches
#   POST /api/orgs/listings/{id}/matches/{mid}/notify — P11: invite one anonymized candidate
#   GET  /api/orgs/matches/{mid}/validation                  — P8: task/skill validation state for a connected match
#   POST /api/orgs/matches/{mid}/tasks/{idx}/verify           — P8: org rep verifies/rejects a task line item
#   POST /api/orgs/matches/{mid}/skills/{skill_id}/verify     — P8: org rep verifies a skill demonstration level
# ============================================================

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

import bcrypt
import jwt

from db import get_db
from models import (
    Organization, OpportunityListing, OpportunityMatch, Learner, Message,
    TaskCompletion, VerifiedSkill, Skill, Session,
)
from cookie_auth import ORG_ACCESS_COOKIE, set_org_cookies, clear_org_cookies
from mail import send_mail

router = APIRouter()
logger = logging.getLogger("freqlearn.orgs")

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
    bioregion:     Optional[str] = None  # P11: self-service bioregion (auto-detected client-side)

class ListingCreate(BaseModel):
    title:         str
    description:   Optional[str] = None
    listing_type:  str = "project"  # volunteer | job | project | internship
    required_arts: list[str] = []   # list of art slugs
    needs_text:    Optional[str] = None  # P11: free-text needs, parsed into skill targets separately
    source_url:    Optional[str] = None
    phase_min:     Optional[int] = None
    phase_max:     Optional[int] = None

class ListingUpdate(BaseModel):
    title:         Optional[str] = None
    description:   Optional[str] = None
    listing_type:  Optional[str] = None
    required_arts: Optional[list[str]] = None
    needs_text:    Optional[str] = None
    needs_skill_targets: Optional[list[dict]] = None
    needs_tasks:   Optional[list[str]] = None
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
        "bioregion":     org.bioregion,
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
        "needs_text":      listing.needs_text,
        "needs_skill_targets": listing.needs_skill_targets or [],
        "needs_tasks":     listing.needs_tasks or [],
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
    if req.bioregion:     org.bioregion      = req.bioregion.strip()
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
        needs_text=req.needs_text,
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
    if req.needs_text    is not None: listing.needs_text    = req.needs_text
    if req.needs_skill_targets is not None: listing.needs_skill_targets = req.needs_skill_targets
    if req.needs_tasks   is not None: listing.needs_tasks   = req.needs_tasks
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

    # P11 consent model: an ai_suggested match stays anonymous to the org
    # until the learner has accepted (learner_status moves to 'interested').
    # 'suggested' = ranked, not yet notified. 'invited' = notified, awaiting
    # the learner's response. Neither reveals identity. Everything else
    # (learner_initiated matches, or ai_suggested ones the learner accepted)
    # is fully visible, same as before.
    out = []
    anon_i = 0
    for m in matches:
        anon = m.origin == "ai_suggested" and m.learner_status in ("suggested", "invited")
        if anon:
            anon_i += 1
            out.append({
                "match_id":      m.id,
                "learner_id":    None,
                "display_name":  f"Candidate {anon_i}",
                "avatar_emoji":  "❔",
                "avatar_color":  "#8892a0",
                "anonymized":    True,
                "origin":        m.origin,
                "learner_status": m.learner_status,
                "org_status":    m.org_status,
                "match_score":   m.match_score,
                "arts_met":      m.arts_met,
                "matched_at":    m.matched_at.isoformat() if m.matched_at else None,
                "notified_at":   m.notified_at.isoformat() if m.notified_at else None,
            })
            continue
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
            "anonymized":    False,
            "origin":        m.origin,
            "learner_status": m.learner_status,
            "org_status":    m.org_status,
            "match_score":   m.match_score,
            "arts_met":      m.arts_met,
            "matched_at":    m.matched_at.isoformat() if m.matched_at else None,
            "notified_at":   m.notified_at.isoformat() if m.notified_at else None,
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


# ── P11: AI needs-matching ──────────────────────────────────
# Added 2026-07-24. Full spec: PROJECT_MASTER PART 18.
#   POST /listings/{id}/parse-needs      — AI parses needs_text into skill targets
#   POST /listings/{id}/generate-matches — ranks learners, creates top-10 ai_suggested matches
#   POST /listings/{id}/matches/{mid}/notify — org invites one anonymized candidate

@router.post("/listings/{listing_id}/parse-needs")
async def parse_listing_needs(
    listing_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Parses needs_text against the closed vocabulary of active skills, returns
    a candidate needs_skill_targets list for the org to review — does NOT save
    it; the org confirms via PATCH /listings/{id} with the reviewed list."""
    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    listing = listing_q.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    if not listing.needs_text or not listing.needs_text.strip():
        raise HTTPException(400, "needs_text is empty — write what you're looking for first")

    from models import Skill
    skills = (await db.execute(select(Skill).where(Skill.is_active == True))).scalars().all()
    vocab = "\n".join(f"- {s.slug}: {s.name}" + (f" ({s.subcategory})" if s.subcategory else "") for s in skills)

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(503, "GROQ_API_KEY not configured")

    system_prompt = f"""You are matching an organization's stated needs to a fixed catalog of learner skills for "Surfing the Frequencies", a free lifelong learning platform.

CLOSED VOCABULARY — you may ONLY use skill slugs from this list, never invent new ones:
{vocab}

The organization wrote this free-text description of what they need:
\"\"\"{listing.needs_text.strip()}\"\"\"

Do two things with this text:

1. Pick the skill slugs (from the list above only) that best match what they're looking for, and a minimum proficiency level for each (levels run 0-3, use 1 for "some experience", 2 for "solid", 3 for "advanced").
2. Break the need down into a short list of concrete, checkable tasks a learner could actually complete and an org rep could later verify happened (e.g. "Facilitate two group discussions", "Draft a first-aid checklist") — not restatements of the skills, actual deliverables/actions.

Respond with ONLY a JSON object, no preamble, no markdown fences, in this exact shape:
{{"needs_skill_targets": [{{"slug": "skill-slug", "min_level": 1}}, ...], "needs_tasks": ["task description", ...]}}
Include at most 6 skills — the ones most central to the need, not every tangential match. Include at most 5 tasks."""

    import httpx, json as _json
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": system_prompt}],
                    "max_tokens": 700,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},  # forces Groq to emit strictly valid JSON rather than trusting free-form text-stripping
                },
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        # Defensive: even in JSON mode, models occasionally wrap the object in
        # a stray sentence — grab the outermost {...} span before parsing.
        brace_start, brace_end = raw.find("{"), raw.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            raw = raw[brace_start:brace_end + 1]
        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as je:
            # Log the actual raw text so a future failure is debuggable from
            # /var/log/freqlearn/api-error.log without needing a manual curl
            # (same pattern as admin.py's Scavenger JSON-parse-failure log).
            logger.error(f"parse-needs JSON parse failed: {je}\nRaw: {raw[:500]}")
            raise
    except Exception as e:
        raise HTTPException(503, f"Needs-parsing unavailable: {str(e)[:120]}")

    if not isinstance(parsed, dict):
        parsed = {}

    valid_slugs = {s.slug: s for s in skills}
    targets = []
    for item in parsed.get("needs_skill_targets") or []:
        slug = item.get("slug") if isinstance(item, dict) else None
        if slug in valid_slugs:
            s = valid_slugs[slug]
            targets.append({
                "skill_id":  s.id,
                "slug":      s.slug,
                "name":      s.name,
                "min_level": max(0, min(3, int(item.get("min_level", 1) or 1))),
            })

    tasks = [
        t.strip()[:300] for t in (parsed.get("needs_tasks") or [])
        if isinstance(t, str) and t.strip()
    ][:5]

    return {"needs_skill_targets": targets, "needs_tasks": tasks}


@router.post("/listings/{listing_id}/generate-matches")
async def generate_ai_matches(
    listing_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Ranks all active learners against listing.needs_skill_targets and creates
    (or refreshes) the top 10 as ai_suggested matches, anonymized to the org
    until the learner is notified and accepts. Does not touch existing
    learner_initiated matches or matches the learner has already acted on."""
    from models import LearnerSkillProgress

    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    listing = listing_q.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    targets = listing.needs_skill_targets or []
    if not targets:
        raise HTTPException(400, "No needs_skill_targets set — run parse-needs and save it first")

    learners = (await db.execute(select(Learner).where(Learner.is_active == True))).scalars().all()
    progress_rows = (await db.execute(select(LearnerSkillProgress))).scalars().all()
    by_learner: dict[int, dict[int, LearnerSkillProgress]] = {}
    for p in progress_rows:
        by_learner.setdefault(p.learner_id, {})[p.skill_id] = p

    ranked = []
    for learner in learners:
        prog = by_learner.get(learner.id, {})
        met, gap, surplus = [], [], 0
        for t in targets:
            level = (prog[t["skill_id"]].current_level or 0) if t["skill_id"] in prog else 0
            if level >= t["min_level"]:
                met.append(t["slug"])
                surplus += (level - t["min_level"])
            else:
                gap.append(t["slug"])
        if not met:
            continue
        score = round((len(met) / len(targets)) * 100 + surplus * 3)
        ranked.append((min(score, 100), learner, met, gap))

    ranked.sort(key=lambda x: -x[0])
    top10 = ranked[:10]

    created, refreshed = 0, 0
    for score, learner, met, gap in top10:
        existing = (await db.execute(
            select(OpportunityMatch).where(
                OpportunityMatch.learner_id == learner.id,
                OpportunityMatch.listing_id == listing_id,
            )
        )).scalar_one_or_none()
        if existing:
            # Don't clobber a match the learner already acted on themselves
            # (learner_initiated, or an ai_suggested one already invited/answered).
            if existing.origin == "ai_suggested" and existing.learner_status == "suggested":
                existing.match_score = score
                existing.arts_met = met
                refreshed += 1
            continue
        db.add(OpportunityMatch(
            learner_id=learner.id, listing_id=listing_id,
            origin="ai_suggested", match_score=score,
            arts_met=met, skills_gap=gap,
            learner_status="suggested", org_status="pending",
        ))
        created += 1
    await db.commit()
    return {"ok": True, "created": created, "refreshed": refreshed, "considered": len(ranked)}


@router.post("/listings/{listing_id}/matches/{match_id}/notify")
async def notify_ai_match(
    listing_id: int,
    match_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Org invites one anonymized AI-suggested candidate — sends an email,
    moves them from 'suggested' to 'invited'. Identity stays hidden from the
    org until the learner accepts."""
    listing_q = await db.execute(
        select(OpportunityListing).where(
            OpportunityListing.id == listing_id,
            OpportunityListing.org_id == org.id,
        )
    )
    listing = listing_q.scalar_one_or_none()
    if not listing:
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
    if match.origin != "ai_suggested" or match.learner_status != "suggested":
        raise HTTPException(400, "This match has already been notified or isn't an AI suggestion")

    learner_q = await db.execute(select(Learner).where(Learner.id == match.learner_id))
    learner = learner_q.scalar_one_or_none()
    if not learner:
        raise HTTPException(404, "Learner not found")

    subject = f"{org.name} thinks you'd be a great fit for \"{listing.title}\""
    body = (
        f"Hi {learner.display_name or 'there'},\n\n"
        f"{org.name} is looking for help with \"{listing.title}\" and your skills "
        f"on Surfing the Frequencies came up as a strong match.\n\n"
        f"Sign in and visit the Koinonia to see the details and accept or decline — "
        f"your name and profile stay private to them unless you accept.\n\n"
        f"— Surfing the Frequencies"
    )
    try:
        send_mail(to=learner.email, subject=subject, body=body)
    except Exception:
        pass  # best-effort — the in-app 'invited' status is the source of truth either way

    match.learner_status = "invited"
    match.notified_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


# ── P8: org validation (task line items + skill demonstrations) ──────
# Added 2026-07-25. Full spec: PROJECT_MASTER PART 22. Both endpoints below
# only work on a match the org has explicitly marked 'connected' (the same
# org_status PATCH /listings/{id}/matches/{id} already sets) — validation is
# scoped to matches that have become a real, ongoing working relationship,
# not every candidate that ever crossed the org's screen.

async def _require_connected_match(match_id: int, org: Organization, db: AsyncSession) -> tuple[OpportunityMatch, OpportunityListing]:
    match_q = await db.execute(
        select(OpportunityMatch, OpportunityListing)
        .join(OpportunityListing, OpportunityListing.id == OpportunityMatch.listing_id)
        .where(OpportunityMatch.id == match_id, OpportunityListing.org_id == org.id)
    )
    row = match_q.first()
    if not row:
        raise HTTPException(404, "Match not found")
    match, listing = row
    if match.org_status != "connected":
        raise HTTPException(400, "Validation is only available once this match is marked 'connected'")
    return match, listing


@router.get("/matches/{match_id}/validation")
async def get_org_validation(
    match_id: int,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Org rep's view of a connected match: the listing's task line items
    (with any learner submission / org verification state) and skill targets
    (with any org-verified level)."""
    match, listing = await _require_connected_match(match_id, org, db)

    tc_rows = (await db.execute(
        select(TaskCompletion).where(TaskCompletion.match_id == match_id)
    )).scalars().all()
    tc_by_idx = {t.task_index: t for t in tc_rows}
    tasks = []
    for i, text in enumerate(listing.needs_tasks or []):
        t = tc_by_idx.get(i)
        tasks.append({
            "task_index":   i,
            "task_text":    text,
            "status":       t.status if t else "open",
            "learner_note": t.learner_note if t else None,
            "session_ids":  t.session_ids if t else None,
            "submitted_at": t.submitted_at.isoformat() if t and t.submitted_at else None,
            "verified_at":  t.verified_at.isoformat() if t and t.verified_at else None,
            "verified_by":  t.verified_by if t else None,
            "org_note":     t.org_note if t else None,
        })

    vs_rows = (await db.execute(
        select(VerifiedSkill).where(VerifiedSkill.match_id == match_id)
    )).scalars().all()
    vs_by_skill = {v.skill_id: v for v in vs_rows}
    skills_out = []
    for target in listing.needs_skill_targets or []:
        sid = target.get("skill_id")
        v = vs_by_skill.get(sid)
        skills_out.append({
            "skill_id":    sid,
            "name":        target.get("name") or target.get("slug"),
            "min_level":   target.get("min_level"),
            "level":       v.level if v else None,
            "session_ids": v.session_ids if v else None,
            "note":        v.note if v else None,
            "verified_by": v.verified_by if v else None,
            "verified_at": v.verified_at.isoformat() if v else None,
        })

    # Learner's session/LECKO history, light summary only (no prompt/response
    # content) — org rep uses this alongside whatever session_ids the learner
    # cited to judge the skill demonstration, without exposing full session
    # transcripts the learner never explicitly submitted as evidence.
    sess_q = await db.execute(
        select(Session)
        .where(Session.learner_id == match.learner_id, Session.status == "completed")
        .order_by(Session.completed_at.desc())
        .limit(50)
    )
    sessions_out = [
        {
            "id":            s.id,
            "title":         s.title,
            "primary_skill_id": s.primary_skill_id,
            "lecko_id":      s.lecko_id,
            "xp_earned":     s.xp_earned,
            "completed_at":  s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sess_q.scalars().all()
    ]

    return {"tasks": tasks, "skills": skills_out, "learner_sessions": sessions_out}


class TaskVerifyIn(BaseModel):
    status:      str            # verified | rejected
    note:        Optional[str] = None
    verified_by: Optional[str] = None

@router.post("/matches/{match_id}/tasks/{task_index}/verify")
async def verify_task(
    match_id: int,
    task_index: int,
    req: TaskVerifyIn,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Org rep checks off (or rejects) a task line item — works whether or
    not the learner submitted first (P8 scoping: org can validate proactively
    off the learner's session history, not only review a learner submission)."""
    if req.status not in ("verified", "rejected"):
        raise HTTPException(400, "status must be 'verified' or 'rejected'")
    match, listing = await _require_connected_match(match_id, org, db)
    tasks = listing.needs_tasks or []
    if task_index < 0 or task_index >= len(tasks):
        raise HTTPException(404, "Task line item not found")

    row = (await db.execute(
        select(TaskCompletion).where(
            TaskCompletion.match_id == match_id,
            TaskCompletion.task_index == task_index,
        )
    )).scalar_one_or_none()
    if not row:
        row = TaskCompletion(
            match_id=match_id, task_index=task_index, task_text=tasks[task_index],
            status="submitted", created_at=datetime.now(timezone.utc),
        )
        db.add(row)

    row.status      = req.status
    row.verified_at = datetime.now(timezone.utc)
    row.verified_by = req.verified_by
    row.org_note     = req.note
    await db.commit()
    return {"ok": True, "status": row.status}


class SkillVerifyIn(BaseModel):
    level:       str            # developing | proficient | master
    session_ids: Optional[list[int]] = None
    note:        Optional[str] = None
    verified_by: Optional[str] = None

@router.post("/matches/{match_id}/skills/{skill_id}/verify")
async def verify_skill(
    match_id: int,
    skill_id: int,
    req: SkillVerifyIn,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Org rep confirms a skill demonstration at developing/proficient/master.
    Writes to verified_skills only — deliberately NOT learner_skill_progress
    (see PART 22): this is a citable credential tied to this Need, not an
    automatic write to the learner's self-paced global skill level."""
    if req.level not in ("developing", "proficient", "master"):
        raise HTTPException(400, "level must be developing | proficient | master")
    match, listing = await _require_connected_match(match_id, org, db)
    target_skill_ids = {t.get("skill_id") for t in (listing.needs_skill_targets or [])}
    if skill_id not in target_skill_ids:
        raise HTTPException(400, "That skill isn't one of this listing's needs_skill_targets")

    row = (await db.execute(
        select(VerifiedSkill).where(
            VerifiedSkill.match_id == match_id,
            VerifiedSkill.skill_id == skill_id,
        )
    )).scalar_one_or_none()
    if not row:
        row = VerifiedSkill(match_id=match_id, skill_id=skill_id)
        db.add(row)

    row.level       = req.level
    row.session_ids = req.session_ids
    row.note         = req.note
    row.verified_by  = req.verified_by
    row.verified_at  = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "level": row.level}


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
