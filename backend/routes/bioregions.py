# ============================================================
# FreqLearn — routes/bioregions.py
# Learner-contributed bioregion profiles + AI collective portraits
# ============================================================

import json
import os
import math
import re
import logging
import httpx
from datetime import datetime, timezone
from typing import List, Optional
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from db import get_db
from routes.auth import get_current_learner
from models import BioregionContribution, BioregionPortrait, Learner

logger = logging.getLogger("freqlearn")
router = APIRouter()

ADMIN_KEY    = os.environ.get("ADMIN_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


async def _call_groq(prompt: str, max_tokens: int = 900, temperature: float = 0.7) -> str:
    """Call Groq via httpx. Returns the text content. Raises HTTPException on failure."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured.")
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GROQ_URL, headers=headers, json=payload)
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except httpx.ConnectError:
        logger.error("Bioregions: cannot reach Groq API")
        raise HTTPException(status_code=502, detail="Cannot reach Groq API.")
    except httpx.HTTPStatusError as e:
        logger.error(f"Bioregions Groq HTTP error: {e.response.status_code}")
        if e.response.status_code == 401:
            raise HTTPException(status_code=502, detail="Invalid GROQ_API_KEY.")
        if e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="Groq rate limit — try again in a minute.")
        raise HTTPException(status_code=502, detail=f"Groq API error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Bioregions Groq call failed: {e}")
        raise HTTPException(status_code=502, detail=f"AI call failed: {e}")


# ── Auth helpers ──────────────────────────────────────────────

def _require_admin(x_admin_key: str = Header(default="")):
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Geo helpers ───────────────────────────────────────────────

def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Return great-circle distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))


async def _find_or_create_portrait(db: AsyncSession, name: str, lat: Optional[float], lng: Optional[float]) -> int:
    """
    Find an existing portrait whose center is within radius_km of (lat, lng)
    and whose label matches (case-insensitive), or create a new one.
    Returns portrait_id.
    """
    result = await db.execute(select(BioregionPortrait))
    portraits = result.scalars().all()

    # First try: name match + proximity (if coords available)
    for p in portraits:
        name_match = p.cluster_label.lower() == name.lower()
        if name_match:
            if lat is None or lng is None or p.center_lat is None or p.center_lng is None:
                return p.id
            dist = _haversine_km(lat, lng, p.center_lat, p.center_lng)
            if dist <= p.radius_km:
                return p.id

    # Second try: proximity only (different names, same area)
    if lat is not None and lng is not None:
        for p in portraits:
            if p.center_lat is None or p.center_lng is None:
                continue
            dist = _haversine_km(lat, lng, p.center_lat, p.center_lng)
            if dist <= p.radius_km:
                return p.id

    # Create new portrait
    portrait = BioregionPortrait(
        cluster_label=name,
        center_lat=lat,
        center_lng=lng,
        radius_km=50,
        contributor_count=0,
    )
    db.add(portrait)
    await db.flush()
    return portrait.id


# ── Schemas ───────────────────────────────────────────────────

class ContributeIn(BaseModel):
    bioregion_name: str = Field(..., min_length=2, max_length=100)
    statement:      str = Field(..., min_length=20, max_length=2000)
    lat:            Optional[float] = None
    lng:            Optional[float] = None

class DraftIn(BaseModel):
    lat:        float = Field(..., ge=-90,  le=90)
    lng:        float = Field(..., ge=-180, le=180)
    place_name: str   = Field(..., min_length=2, max_length=100)

class GeneratePortraitRequest(BaseModel):
    """Optional body for POST /admin/portraits/{id}/generate"""
    change_notes: Optional[str] = None

class BioVersionOut(BaseModel):
    """One entry in a portrait's version history (list view)"""
    id: int
    version_number: int
    contributor_count: int
    vitality_snapshot: Optional[str]
    change_notes: Optional[str]
    generated_at: datetime

class BioVersionDetailOut(BioVersionOut):
    """Full version detail including summary text"""
    summary: str


# ── Learner endpoints ─────────────────────────────────────────

@router.post("/contribute")
async def contribute_bioregion(
    body: ContributeIn,
    db:   AsyncSession = Depends(get_db),
    learner: Learner   = Depends(get_current_learner),
):
    """Submit a personal bioregion statement (goes to moderation queue)."""
    existing = await db.execute(
        select(BioregionContribution)
        .where(BioregionContribution.learner_id == learner.id)
        .where(BioregionContribution.status.in_(["pending", "approved"]))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You already have an active contribution. Edit or withdraw it first.")

    portrait_id = await _find_or_create_portrait(db, body.bioregion_name, body.lat, body.lng)

    contrib = BioregionContribution(
        learner_id=learner.id,
        bioregion_name=body.bioregion_name,
        lat=body.lat,
        lng=body.lng,
        statement=body.statement,
        status="pending",
        portrait_id=portrait_id,
    )
    db.add(contrib)
    await db.commit()
    return {"ok": True, "id": contrib.id, "portrait_id": portrait_id}


@router.get("/my-contribution")
async def my_contribution(
    db:      AsyncSession = Depends(get_db),
    learner: Learner      = Depends(get_current_learner),
):
    """Return the learner's own latest contribution (any status)."""
    result = await db.execute(
        select(BioregionContribution)
        .where(BioregionContribution.learner_id == learner.id)
        .order_by(BioregionContribution.created_at.desc())
    )
    c = result.scalar_one_or_none()
    if not c:
        return {"contribution": None}
    return {"contribution": {
        "id": c.id,
        "bioregion_name": c.bioregion_name,
        "statement": c.statement,
        "status": c.status,
        "portrait_id": c.portrait_id,
        "created_at": c.created_at.isoformat(),
    }}


@router.delete("/my-contribution")
async def withdraw_contribution(
    db:      AsyncSession = Depends(get_db),
    learner: Learner      = Depends(get_current_learner),
):
    """Withdraw a pending contribution (cannot withdraw approved)."""
    result = await db.execute(
        select(BioregionContribution)
        .where(BioregionContribution.learner_id == learner.id)
        .where(BioregionContribution.status == "pending")
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="No pending contribution found.")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/draft")
async def draft_portrait(
    body:    DraftIn,
    db:      AsyncSession = Depends(get_db),
    learner: Learner      = Depends(get_current_learner),
):
    """Generate an AI draft bioregion portrait for a location with no nearby portrait.
    Returns {draft: {...}} or {draft: null, reason: 'portrait_exists', portrait_id: int}.
    """
    # If a portrait already exists within 100 km, no draft needed
    result = await db.execute(
        select(BioregionPortrait).where(BioregionPortrait.contributor_count > 0)
    )
    for p in result.scalars().all():
        if p.center_lat is not None and p.center_lng is not None:
            if _haversine_km(body.lat, body.lng, p.center_lat, p.center_lng) <= 100:
                return {"draft": None, "reason": "portrait_exists", "portrait_id": p.id}

    # Look up matching seed profile to enrich the prompt with resources context
    seed_result = await db.execute(
        text("""
            SELECT resources, species, climate, watershed
            FROM bioregion_seed_profiles
            WHERE min_lat <= :lat AND max_lat >= :lat
              AND min_lng <= :lng AND max_lng >= :lng
            LIMIT 1
        """),
        {"lat": body.lat, "lng": body.lng}
    )
    seed = seed_result.mappings().fetchone()

    context_block = ""
    if seed:
        parts = []
        if seed.get("resources"):
            parts.append(f"Natural resources: {seed['resources']}")
        if seed.get("species"):
            parts.append(f"Key species: {seed['species']}")
        if seed.get("climate"):
            parts.append(f"Climate: {seed['climate']}")
        if seed.get("watershed"):
            parts.append(f"Watershed: {seed['watershed']}")
        if parts:
            context_block = (
                "\n\nRegional ecological context (use this to ground your response in "
                "real specifics — name actual species, rivers, materials, and trades):\n"
                + "\n".join(f"- {p}" for p in parts)
                + "\n"
            )

    prompt = f"""You are an ecologist writing a bioregion portrait to help a learner describe their home place.

Location: "{body.place_name}" ({body.lat:.4f}°N, {body.lng:.4f}°E){context_block}
Return ONLY a valid JSON object — no preamble, no markdown fences. Each value must be 1–2 vivid, specific sentences grounded in real ecology and the material life of this place.

{{
  "summary":          "3–4 sentence evocative portrait of this region as a living place",
  "watershed":        "primary river systems, their sources and destinations",
  "climate":          "climate type, key seasonal rhythms, notable weather phenomena",
  "species":          "2–4 significant, endemic or ecologically important species with brief context",
  "vitality":         "current ecological health — key pressures and any signs of recovery",
  "economy":          "traditional and current livelihoods rooted in this land — how people have made a living from its specific resources, minerals, fisheries, or forests",
  "material_culture": "tools, crafts, foods, medicines, or building traditions tied to local species and materials — what this place has given to human hands"
}}"""

    raw = await _call_groq(prompt, max_tokens=900, temperature=0.7)
    # Strip markdown fences if present, then extract first JSON object
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*", "", raw).strip().rstrip("`").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        logger.error("Draft JSON parse error: no JSON object in response")
        raise HTTPException(status_code=502, detail="AI returned an unparseable response.")
    try:
        draft_data = json.loads(m.group())
    except json.JSONDecodeError as e:
        logger.error(f"Draft JSON parse error: {e}")
        raise HTTPException(status_code=502, detail="AI returned an unparseable response.")

    return {"draft": {
        "place_name":       body.place_name,
        "lat":              body.lat,
        "lng":              body.lng,
        "summary":          draft_data.get("summary",          ""),
        "watershed":        draft_data.get("watershed",        ""),
        "climate":          draft_data.get("climate",          ""),
        "species":          draft_data.get("species",          ""),
        "vitality":         draft_data.get("vitality",         ""),
        "economy":          draft_data.get("economy",          ""),
        "material_culture": draft_data.get("material_culture", ""),
    }}


@router.get("")
async def list_portraits(
    db:  AsyncSession    = Depends(get_db),
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
):
    """Public — list all portraits that have at least one approved contribution.
    If lat/lng provided: sorted by haversine distance (nearest first), distance_km included.
    Otherwise: sorted by contributor_count descending.
    """
    result = await db.execute(
        select(BioregionPortrait)
        .where(BioregionPortrait.contributor_count > 0)
    )
    portraits = result.scalars().all()

    def _to_dict(p, dist_km=None):
        return {
            "id": p.id,
            "cluster_label": p.cluster_label,
            "center_lat": p.center_lat,
            "center_lng": p.center_lng,
            "contributor_count": p.contributor_count,
            "summary": p.summary,
            "last_generated_at": p.last_generated_at.isoformat() if p.last_generated_at else None,
            "version_number":   getattr(p, 'version_number', None),
            "vitality_snapshot": getattr(p, 'vitality_snapshot', None),
            "distance_km": round(dist_km, 1) if dist_km is not None else None,
        }

    if lat is not None and lng is not None:
        items = []
        for p in portraits:
            if p.center_lat is not None and p.center_lng is not None:
                dist = _haversine_km(lat, lng, p.center_lat, p.center_lng)
            else:
                dist = None
            items.append((p, dist))
        # Known distances first (ascending), portraits with no coords last
        items.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0))
        return {"portraits": [_to_dict(p, dist) for p, dist in items]}
    else:
        portraits_sorted = sorted(portraits, key=lambda p: -p.contributor_count)
        return {"portraits": [_to_dict(p) for p in portraits_sorted]}



@router.get("/seed-profiles")
async def get_seed_profiles(db: AsyncSession = Depends(get_db)):
    """Public — return all seed bioregion profiles for frontend use.
    Powers the 'Where I Stand' bioregion card on the dashboard.
    No auth required; data is static reference information.
    """
    result = await db.execute(
        text(
            "SELECT slug, name, colonial, archaic, min_lat, max_lat, min_lng, max_lng, "
            "climate, watershed, tectonic, species, soil, vitality, connections, resources "
            "FROM bioregion_seed_profiles ORDER BY id"
        )
    )
    rows = result.mappings().all()
    return {"profiles": [dict(r) for r in rows]}

@router.get("/{portrait_id}")
async def get_portrait(portrait_id: int, db: AsyncSession = Depends(get_db)):
    """Public — single portrait with approved contributor voices."""
    result = await db.execute(
        select(BioregionPortrait).where(BioregionPortrait.id == portrait_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Portrait not found.")

    contribs = await db.execute(
        select(BioregionContribution, Learner.display_name)
        .join(Learner, Learner.id == BioregionContribution.learner_id)
        .where(BioregionContribution.portrait_id == portrait_id)
        .where(BioregionContribution.status == "approved")
        .order_by(BioregionContribution.created_at)
    )
    voices = [
        {"display_name": row.display_name or "A learner", "statement": row.BioregionContribution.statement}
        for row in contribs
    ]
    return {
        "id": p.id,
        "cluster_label": p.cluster_label,
        "center_lat": p.center_lat,
        "center_lng": p.center_lng,
        "contributor_count": p.contributor_count,
        "summary": p.summary,
        "last_generated_at": p.last_generated_at.isoformat() if p.last_generated_at else None,
        "version_number":   getattr(p, 'version_number', None),
        "vitality_snapshot": getattr(p, 'vitality_snapshot', None),
        "voices": voices,
    }


@router.get("/{portrait_id}/versions", response_model=List[BioVersionOut])
async def list_portrait_versions(
    portrait_id: int,
    db: AsyncSession = Depends(get_db),
    learner: Learner = Depends(get_current_learner),
):
    """
    List all historical versions of a portrait, newest first.
    Includes the current live version (from bioregion_portraits) as the
    first item so the client has a complete ordered timeline.
    """
    exists = await db.execute(
        text("SELECT id FROM bioregion_portraits WHERE id = :pid"),
        {"pid": portrait_id}
    )
    if not exists.first():
        raise HTTPException(status_code=404, detail="Portrait not found")

    arch_rows = await db.execute(
        text("""
            SELECT id, version_number, contributor_count, vitality_snapshot,
                   change_notes, generated_at
            FROM bioregion_portrait_versions
            WHERE portrait_id = :pid
            ORDER BY version_number DESC
        """),
        {"pid": portrait_id}
    )
    archived = [dict(r) for r in arch_rows.mappings().all()]

    live_row = await db.execute(
        text("""
            SELECT version_number, contributor_count, vitality_snapshot,
                   change_notes, last_generated_at AS generated_at
            FROM bioregion_portraits
            WHERE id = :pid
        """),
        {"pid": portrait_id}
    )
    live = live_row.mappings().first()
    if not live:
        return archived

    current = {
        "id": 0,  # sentinel: 0 = current live version
        "version_number": live["version_number"] or 1,
        "contributor_count": live["contributor_count"] or 0,
        "vitality_snapshot": live["vitality_snapshot"],
        "change_notes": live["change_notes"],
        "generated_at": live["generated_at"],
    }
    return [current] + archived


@router.get("/{portrait_id}/versions/{version_number}", response_model=BioVersionDetailOut)
async def get_portrait_version(
    portrait_id: int,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    learner: Learner = Depends(get_current_learner),
):
    """
    Fetch the full summary text for a specific historical version.
    version_number = current live version → returns from bioregion_portraits.
    version_number < current              → returns from bioregion_portrait_versions.
    """
    live_row = await db.execute(
        text("SELECT version_number, summary, contributor_count, "
             "vitality_snapshot, change_notes, last_generated_at AS generated_at "
             "FROM bioregion_portraits WHERE id = :pid"),
        {"pid": portrait_id}
    )
    live = live_row.mappings().first()
    if not live:
        raise HTTPException(status_code=404, detail="Portrait not found")

    if version_number == (live["version_number"] or 1):
        return {
            "id": 0,
            "version_number": live["version_number"] or 1,
            "summary": live["summary"] or "",
            "contributor_count": live["contributor_count"] or 0,
            "vitality_snapshot": live["vitality_snapshot"],
            "change_notes": live["change_notes"],
            "generated_at": live["generated_at"],
        }

    arch_row = await db.execute(
        text("""
            SELECT id, version_number, summary, contributor_count,
                   vitality_snapshot, change_notes, generated_at
            FROM bioregion_portrait_versions
            WHERE portrait_id = :pid AND version_number = :vnum
        """),
        {"pid": portrait_id, "vnum": version_number}
    )
    arch = arch_row.mappings().first()
    if not arch:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

    return dict(arch)


@router.patch("/admin/portraits/{portrait_id}/versions/{version_number}/notes", dependencies=[Depends(_require_admin)])
async def patch_version_notes(
    portrait_id: int,
    version_number: int,
    body: dict,   # expects {"change_notes": "..."}
    db: AsyncSession = Depends(get_db),
):
    """
    Admin: update the change_notes on any version (current or archived).
    Useful for adding ecological context after the fact.
    Auth handled by _require_admin dependency.
    """
    notes = body.get("change_notes", "")

    live_row = await db.execute(
        text("SELECT version_number FROM bioregion_portraits WHERE id = :pid"),
        {"pid": portrait_id}
    )
    live = live_row.mappings().first()
    if not live:
        raise HTTPException(status_code=404, detail="Portrait not found")

    current_version = live["version_number"] or 1
    if version_number == current_version:
        await db.execute(
            text("UPDATE bioregion_portraits SET change_notes = :notes WHERE id = :pid"),
            {"notes": notes, "pid": portrait_id}
        )
    else:
        result = await db.execute(
            text("""
                UPDATE bioregion_portrait_versions
                SET change_notes = :notes
                WHERE portrait_id = :pid AND version_number = :vnum
            """),
            {"notes": notes, "pid": portrait_id, "vnum": version_number}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

    await db.commit()
    return {"ok": True, "portrait_id": portrait_id, "version_number": version_number}


# ── Admin auth aliases for version endpoints ──────────────────────────────
# The learner-facing versions endpoints require JWT. Admin UI has no JWT,
# only X-Admin-Key. These thin duplicates let bioShowVersionHistory() work.

@router.get("/admin/portraits/{portrait_id}/versions")
async def admin_list_portrait_versions(
    portrait_id: int,
    db: AsyncSession = Depends(get_db),
    _admin = Depends(_require_admin),
):
    """Admin: list all versions for a portrait (no JWT required)."""
    exists = await db.execute(
        text("SELECT id FROM bioregion_portraits WHERE id = :pid"),
        {"pid": portrait_id}
    )
    if not exists.first():
        raise HTTPException(status_code=404, detail="Portrait not found")

    arch_rows = await db.execute(
        text("""
            SELECT 0 AS id, version_number, contributor_count, vitality_snapshot,
                   change_notes, generated_at, summary
            FROM bioregion_portrait_versions
            WHERE portrait_id = :pid
            ORDER BY version_number DESC
        """),
        {"pid": portrait_id}
    )
    archived = [dict(r) for r in arch_rows.mappings().all()]

    live_row = await db.execute(
        text("""
            SELECT version_number, contributor_count, vitality_snapshot,
                   change_notes, last_generated_at AS generated_at, summary
            FROM bioregion_portraits
            WHERE id = :pid
        """),
        {"pid": portrait_id}
    )
    live = live_row.mappings().first()
    if not live:
        return archived

    current = {
        "id": 0,
        "version_number": live["version_number"] or 1,
        "contributor_count": live["contributor_count"] or 0,
        "vitality_snapshot": live["vitality_snapshot"],
        "change_notes": live["change_notes"],
        "generated_at": live["generated_at"],
        "summary": live["summary"],
    }
    return [current] + archived


@router.get("/admin/portraits/{portrait_id}/versions/{version_number}")
async def admin_get_portrait_version(
    portrait_id: int,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    _admin = Depends(_require_admin),
):
    """Admin: fetch one version detail (no JWT required)."""
    live_row = await db.execute(
        text("SELECT version_number, summary, contributor_count, "
             "vitality_snapshot, change_notes, last_generated_at AS generated_at "
             "FROM bioregion_portraits WHERE id = :pid"),
        {"pid": portrait_id}
    )
    live = live_row.mappings().first()
    if not live:
        raise HTTPException(status_code=404, detail="Portrait not found")

    if version_number == (live["version_number"] or 1):
        return {
            "id": 0,
            "version_number": live["version_number"] or 1,
            "summary": live["summary"] or "",
            "contributor_count": live["contributor_count"] or 0,
            "vitality_snapshot": live["vitality_snapshot"],
            "change_notes": live["change_notes"],
            "generated_at": live["generated_at"],
        }

    arch_row = await db.execute(
        text("""
            SELECT 0 AS id, version_number, summary, contributor_count,
                   vitality_snapshot, change_notes, generated_at
            FROM bioregion_portrait_versions
            WHERE portrait_id = :pid AND version_number = :vnum
        """),
        {"pid": portrait_id, "vnum": version_number}
    )
    arch = arch_row.mappings().first()
    if not arch:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")
    return dict(arch)


# ── Admin endpoints ───────────────────────────────────────────

@router.get("/admin/pending", dependencies=[Depends(_require_admin)])
async def admin_pending(db: AsyncSession = Depends(get_db)):
    """Admin — list pending contributions for moderation."""
    result = await db.execute(
        select(BioregionContribution, Learner.display_name, Learner.username)
        .join(Learner, Learner.id == BioregionContribution.learner_id)
        .where(BioregionContribution.status == "pending")
        .order_by(BioregionContribution.created_at)
    )
    rows = result.all()
    return {"pending": [
        {
            "id": row.BioregionContribution.id,
            "learner_name": row.display_name or row.username,
            "bioregion_name": row.BioregionContribution.bioregion_name,
            "statement": row.BioregionContribution.statement,
            "lat": row.BioregionContribution.lat,
            "lng": row.BioregionContribution.lng,
            "portrait_id": row.BioregionContribution.portrait_id,
            "created_at": row.BioregionContribution.created_at.isoformat(),
        }
        for row in rows
    ]}


@router.patch("/admin/contributions/{contrib_id}", dependencies=[Depends(_require_admin)])
async def admin_moderate(
    contrib_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Admin — approve or reject a pending contribution."""
    action = body.get("action")
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    result = await db.execute(
        select(BioregionContribution).where(BioregionContribution.id == contrib_id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contribution not found.")

    c.status = "approved" if action == "approve" else "rejected"

    if action == "approve" and c.portrait_id:
        portrait_result = await db.execute(
            select(BioregionPortrait).where(BioregionPortrait.id == c.portrait_id)
        )
        portrait = portrait_result.scalar_one_or_none()
        if portrait:
            portrait.contributor_count += 1

    await db.commit()
    return {"ok": True, "status": c.status}


@router.get("/admin/portraits", dependencies=[Depends(_require_admin)])
async def admin_portraits(db: AsyncSession = Depends(get_db)):
    """Admin — list all portraits (including those with 0 contributors)."""
    result = await db.execute(
        select(BioregionPortrait).order_by(BioregionPortrait.contributor_count.desc())
    )
    portraits = result.scalars().all()
    return {"portraits": [
        {
            "id": p.id,
            "cluster_label": p.cluster_label,
            "contributor_count": p.contributor_count,
            "has_summary": bool(p.summary),
            "summary": p.summary or "",
            "last_generated_at": p.last_generated_at.isoformat() if p.last_generated_at else None,
        }
        for p in portraits
    ]}


@router.post("/admin/portraits/{portrait_id}/generate", dependencies=[Depends(_require_admin)])
async def admin_generate_portrait(portrait_id: int, db: AsyncSession = Depends(get_db)):
    """Admin — trigger AI synthesis of approved contributions for a portrait cluster.
    Archives current version before overwriting, increments version_number.
    Accepts optional X-Admin-Key header. Admin key env var still required.
    """
    portrait_result = await db.execute(
        select(BioregionPortrait).where(BioregionPortrait.id == portrait_id)
    )
    portrait = portrait_result.scalar_one_or_none()
    if not portrait:
        raise HTTPException(status_code=404, detail="Portrait not found.")

    contribs_result = await db.execute(
        select(BioregionContribution)
        .where(BioregionContribution.portrait_id == portrait_id)
        .where(BioregionContribution.status == "approved")
    )
    contribs = contribs_result.scalars().all()
    if not contribs:
        raise HTTPException(status_code=400, detail="No approved contributions to synthesise.")

    # ── Snapshot current version to archive (if a summary exists) ─────────
    old_version = getattr(portrait, 'version_number', None) or 1
    if portrait.summary:
        await db.execute(
            text("""
                INSERT INTO bioregion_portrait_versions
                  (portrait_id, version_number, summary, contributor_count,
                   vitality_snapshot, change_notes, generated_at)
                VALUES
                  (:pid, :vnum, :summary, :contributor_count,
                   :vitality_snapshot, :change_notes, :generated_at)
                ON DUPLICATE KEY UPDATE
                  summary            = VALUES(summary),
                  change_notes       = VALUES(change_notes),
                  vitality_snapshot  = VALUES(vitality_snapshot)
            """),
            {
                "pid": portrait.id,
                "vnum": old_version,
                "summary": portrait.summary,
                "contributor_count": portrait.contributor_count or 0,
                "vitality_snapshot": getattr(portrait, 'vitality_snapshot', None),
                "change_notes": None,
                "generated_at": portrait.last_generated_at or datetime.now(timezone.utc),
            }
        )

    voices_text = "\n\n".join(
        f'Learner from {c.bioregion_name}: "{c.statement}"'
        for c in contribs
    )

    prompt = f"""You are a poetic-but-grounded writer helping build a living portrait of a bioregion called "{portrait.cluster_label}".

Below are personal statements from learners who live in or near this region. Each voice describes their direct experience of this place — its ecology, rhythms, textures, and meaning.

{voices_text}

Write a collective portrait of "{portrait.cluster_label}" (150–250 words) that:
- Synthesises the voices without quoting them directly
- Captures what is distinctive and alive about this place
- Honours ecological, cultural, and sensory dimensions
- Reads as an invitation to the reader, not a Wikipedia entry
- Avoids clichés; stays grounded in what the contributors actually shared

Write only the portrait itself. No title, no preamble."""

    summary = await _call_groq(prompt, max_tokens=400, temperature=0.75)

    new_version = old_version + 1
    portrait.summary = summary
    portrait.last_generated_at = datetime.now(timezone.utc)
    portrait.contributor_count = len(contribs)
    if hasattr(portrait, 'version_number'):
        portrait.version_number = new_version
    if hasattr(portrait, 'vitality_snapshot'):
        portrait.vitality_snapshot = None
    await db.commit()

    return {
        "ok": True,
        "portrait_id": portrait_id,
        "version_number": new_version,
        "vitality_snapshot": None,
        "archived_version": old_version,
    }


# ── Seed data for bioregion_seed_profiles ─────────────────────
# Run once (idempotent) to populate the DB from the hardcoded app.js profiles.
# Each record maps directly to the BIOREGION_PROFILES constant previously in app.js.

_SEED_PROFILES = [
    dict(slug='red-river-delta', name='Red River Delta',
         colonial='Hanoi / Northern Vietnam',
         archaic='Thăng Long · Đại Việt heartland',
         min_lat=20.0, max_lat=22.5, min_lng=103.0, max_lng=107.0,
         climate='Humid subtropical monsoon — hot wet summers, cool dry winters',
         watershed='Sông Hồng (Red River) — sourced in Yunnan, empties into Gulf of Tonkin',
         tectonic='Indochina Plate — relatively stable, bounded by the Ailao Shan–Red River shear zone',
         species='Asian elephant corridors (highland margins), Irrawaddy dolphin (coastal), red junglefowl, golden leaf monkey',
         soil='Deep alluvial silt — among the most fertile rice-cultivation soils on earth',
         vitality='Stressed — delta subsiding from groundwater extraction; upstream dams reducing sediment; rapid urbanisation',
         connections='Watershed connects to Yunnan plateau (north) and Gulf of Tonkin marine system (south-east)',
         resources='Anthracite coal (Quảng Ninh — among Asia\'s highest-grade deposits), titanium ilmenite (coastal dunes), natural gas (offshore Gulf of Tonkin), chromite (highland margins), kaolin and silica sand'),
    dict(slug='mekong-delta', name='Mekong Delta',
         colonial='Ho Chi Minh City / Southern Vietnam',
         archaic='Prey Nokor · Khmer delta lands',
         min_lat=9.0, max_lat=12.0, min_lng=104.0, max_lng=107.0,
         climate='Tropical monsoon — distinct wet and dry seasons; flood pulse ecology',
         watershed='Mekong River — 4,900km from Tibetan Plateau through six nations',
         tectonic='Indochina Plate — low-lying, subsidence risk',
         species='Mekong giant catfish (critically endangered), Irrawaddy dolphin, painted stork, mangrove ecosystems',
         soil='Annually replenished alluvial plain — rice bowl of Southeast Asia, now sediment-starved by upstream dams',
         vitality='At risk — saltwater intrusion, subsidence, reduced Mekong flow from Chinese dams',
         connections='Connects Tibetan water towers to South China Sea; shared with Cambodia, Laos, Thailand, Myanmar, China',
         resources='Offshore natural gas (Nam Con Son and Cửu Long basins), river sand (intensively dredged despite subsidence risk), tin and cassiterite (upstream Laos and Cambodia), richest freshwater fishery in Southeast Asia'),
    dict(slug='niger-delta', name='Niger Delta Mangrove Basin',
         colonial='Port Harcourt / Niger Delta, Nigeria',
         archaic='Ijawland · Ogoniland · Urhoboland',
         min_lat=4.0, max_lat=6.5, min_lng=5.0, max_lng=9.0,
         climate='Equatorial — high rainfall year-round, distinct flooding seasons',
         watershed="Niger River — 4,180km, third longest in Africa; delta one of world\'s largest",
         tectonic='African Plate — passive continental margin, subsiding delta',
         species='African manatee, forest elephant corridors, Niger Delta red colobus, diverse mangrove fish nurseries',
         soil='Waterlogged peat and clay — one of world\'s most biodiverse wetland systems, severely degraded by oil extraction',
         vitality='Critical — 50+ years of oil spills, gas flaring, and mangrove destruction',
         connections='Connects Sahel rainfall systems to Atlantic; shared fisheries with Cameroon and Benin coasts',
         resources='>35 billion barrels crude oil reserves — one of Africa\'s richest hydrocarbon basins; world\'s 9th largest natural gas reserves (largely flared); bitumen seeps; artisanal alluvial gold (northern delta margins)'),
    dict(slug='thames-basin', name='Thames Chalk & Clay Basin',
         colonial='London / South-East England',
         archaic='Londinium · Tamesas · Trinovantes territory',
         min_lat=51.0, max_lat=52.0, min_lng=-1.0, max_lng=1.0,
         climate='Temperate oceanic — mild, wet, rarely extreme; warming measurably since 1990s',
         watershed='River Thames — 346km through chalk aquifer and London clay',
         tectonic='Eurasian Plate — geologically stable; isostatic tilting (south-east England slowly sinking)',
         species='European eel (critically endangered), peregrine falcon (urban resurgence), water vole, black-headed gull',
         soil='London clay over chalk — heavy, poorly draining; chalk aquifer supplies much of regional water',
         vitality='Recovering — Thames declared biologically dead in 1950s, now hosts 115 fish species after clean-up',
         connections='North Sea marine system; Atlantic weather patterns; chalk aquifer connects to Chilterns and Downs',
         resources='Thames Gravel (structural aggregate — underpins London\'s built fabric), chalk aquifer (primary drinking water for 7 million people), historically iron and tin from Cornish-Welsh margins; North Sea oil and gas via coastal pipeline network'),
    dict(slug='ganges-plain', name='Indo-Gangetic Plain',
         colonial='Delhi / Uttar Pradesh / Bihar, India',
         archaic='Āryāvarta · Gangetic heartland · Magadha',
         min_lat=24.0, max_lat=28.0, min_lng=78.0, max_lng=88.0,
         climate='Subtropical semi-arid to humid — monsoon-dependent; increasingly erratic',
         watershed='Ganges-Yamuna-Brahmaputra system — Himalayan glacial melt + monsoon fed',
         tectonic='Indian Plate colliding with Eurasian — Himalayan uplift continuing; plain is foredeep basin',
         species='Ganges river dolphin (national aquatic animal of India), gharial, Bengal florican, one-horned rhinoceros (east)',
         soil="Deep alluvial — among earth\'s most intensively farmed; groundwater being extracted faster than recharged",
         vitality='Stressed — groundwater crisis, river pollution, glacier retreat threatening dry-season flows',
         connections='Himalayan water towers (Tibet); Bay of Bengal monsoon circulation; connects to Brahmaputra delta (Bangladesh)',
         resources='Coal (Jharkhand — Jharia coalfield, largest in Asia), iron ore (Singhbhum belt), uranium (Jharkhand — India\'s primary uranium source), natural gas (Upper Assam basin), monazite sands with rare earth elements (Bihar/Odisha coast)'),
    dict(slug='great-lakes', name='Laurentian Great Lakes Basin',
         colonial='Chicago / Detroit / Toronto area',
         archaic='Anishinaabe homelands · Haudenosaunee territory · Odawa',
         min_lat=41.0, max_lat=47.0, min_lng=-88.0, max_lng=-76.0,
         climate='Continental humid — cold winters, warm summers; lake-effect snow; warming 2× global average',
         watershed="Great Lakes hold 21% of world\'s surface freshwater; drain via St. Lawrence to Atlantic",
         tectonic='Laurentian Shield — ancient Precambrian bedrock; lakes carved by Pleistocene glaciation',
         species='Lake sturgeon, lake whitefish, grey wolf (northern margins), bald eagle, massasauga rattlesnake',
         soil="Thin glacial till over bedrock north; deep prairie loam south — one of world\'s great agricultural zones",
         vitality='Mixed — invasive species (zebra mussel, sea lamprey) and algal blooms stress system; water quality slowly improving',
         connections='St. Lawrence Seaway to Atlantic; Mississippi watershed to Gulf of Mexico immediately to south',
         resources='Iron ore (Mesabi Range, Minnesota — largest US deposit, foundation of American steel industry), copper and nickel (Sudbury, Ontario — world\'s largest nickel deposit), uranium (Athabasca Basin, northern Canada), freshwater (21% of global surface freshwater — most contested resource)'),
    dict(slug='amazon-basin', name='Amazon Basin Rainforest',
         colonial='Manaus / Belém / Amazonia, Brazil',
         archaic='Tupinambá · Yanomami · Kayapó territories · Pre-Columbian Amazonia',
         min_lat=-10.0, max_lat=2.0, min_lng=-75.0, max_lng=-50.0,
         climate='Equatorial — year-round heat and humidity; self-generates 50%+ of own rainfall via biotic pump',
         watershed="Amazon River — largest by discharge on earth; 20% of all freshwater entering world\'s oceans",
         tectonic='South American Plate — stable craton; river flows east since Andes uplift reversed drainage 10Ma',
         species='Jaguar, giant river otter, Amazon river dolphin (boto), harpy eagle, ~40,000 plant species',
         soil='Oxisol — ancient, nutrient-poor; fertility held in biomass not soil; forest IS the soil system',
         vitality='Critical — 17% deforested; approaching tipping point where degraded areas can no longer generate rainfall',
         connections='Andes snowmelt (west); Atlantic moisture recycling; Cerrado savanna transition (south)',
         resources='Iron ore (Carajás, Pará — world\'s largest known iron ore deposit), bauxite/aluminium (Trombetas River), gold (Serra Pelada and dispersed artisanal mining), copper and manganese (Carajás complex), cassiterite/tin; freshwater biodiversity itself a critical and irreplaceable resource'),
    dict(slug='sahel', name='Sahel Transition Zone',
         colonial="Dakar / Bamako / Niamey / N\'Djamena corridor",
         archaic='Mali Empire · Songhai · Kanem-Bornu · Fulani pastoral lands',
         min_lat=12.0, max_lat=17.0, min_lng=-15.0, max_lng=25.0,
         climate='Semi-arid — 200–600mm rainfall, highly variable; 3-month growing window; expanding aridity',
         watershed='Senegal, Niger and Lake Chad basin — all shrinking under climate pressure and extraction',
         tectonic='African Plate — stable craton; Sahel is a transition between Sahara and humid tropics',
         species='Dama gazelle, addax, African wild dog, Sudan cheetah, migratory locust, quelea bird',
         soil='Sandy and laterite — low organic matter; wind erosion severe; traditional zaï pits and half-moon earthworks restore fertility',
         vitality='Stressed but actively regenerating — Farmer-Managed Natural Regeneration (FMNR) restoring millions of hectares',
         connections='Saharan dust fertilises Amazon basin; ITCZ rainfall belt shifts north/south annually; connects to Central African rainforest',
         resources='Gold (Mali\'s Syama, Burkina Faso — West Africa holds 30%+ of continental reserves), uranium (Agadez, Niger — world\'s 7th largest producer), phosphates (Taiba, Senegal), iron ore (Mauritania — major national export), crude oil (Chad basin, Niger\'s Agadem block), emerging lithium prospecting (Mali)'),
    dict(slug='pacific-northwest', name='Pacific Northwest Temperate Rainforest',
         colonial='Portland / Seattle / Vancouver',
         archaic='Coast Salish · Chinook · Tillamook · Lummi territories',
         min_lat=45.0, max_lat=51.0, min_lng=-125.0, max_lng=-120.0,
         climate='Oceanic — mild wet winters, warm dry summers; rain shadow east of Cascades',
         watershed='Columbia-Snake and Fraser River systems — critical Pacific salmon habitat',
         tectonic='Juan de Fuca Plate subducting under North American — Cascadia subduction zone; active volcanism',
         species='Chinook salmon, orca (Southern Resident population critically endangered), Roosevelt elk, northern spotted owl, Douglas fir (ancient stands)',
         soil='Volcanic ash and glacial till under deep organic duff — among most productive temperate forest soils',
         vitality='Mixed — old-growth severely reduced; salmon populations collapsed; rewilding efforts active',
         connections='Pacific Ocean temperature drives regional climate; salmon link ocean nutrients to forest interior',
         resources='Copper and molybdenum (porphyry deposits, British Columbia interior), gold and silver (Cascades placer and hard-rock), thermal coal (BC Elk Valley — major Asia-Pacific export), second-growth timber, hydropower (Columbia-Snake system), potential lithium (Basin and Range margins)'),
    dict(slug='east-african-rift', name='East African Rift Highlands',
         colonial='Nairobi / Kampala / Kigali',
         archaic='Maasailand · Kikuyu highlands · Luo Nyanza · Buganda',
         min_lat=-3.0, max_lat=5.0, min_lng=34.0, max_lng=42.0,
         climate='Highland equatorial — altitude moderates heat; two rainy seasons; highly variable by elevation',
         watershed='Victoria basin (source of White Nile); Rift Valley lakes (Turkana, Tanganyika, Malawi)',
         tectonic='African Plate splitting — East African Rift is actively tearing the continent apart; new ocean forming in millions of years',
         species='African elephant, mountain gorilla, wildebeest (Serengeti migration), flamingo (Rift lakes), shoebill stork',
         soil='Volcanic red clay and highland loam — fertile but subject to erosion on steep slopes',
         vitality='Mixed — wildlife corridors under pressure from agriculture; Lake Victoria severely eutrophied; active conservation efforts',
         connections='Nile system to Mediterranean; Indian Ocean moisture; wildebeest migration crosses Tanzania-Kenya border',
         resources='Gold (Geita, Tanzania — one of Africa\'s largest mines; South Sudan\'s Nile belt), soda ash (Lake Magadi, Kenya — largest Kenyan mineral export), fluorite (Kerio Valley, Kenya), geothermal energy (Kenya 750+ MW — over 40% of national electricity), coltan/tantalum (eastern DRC fringe), cobalt (Zambia-DRC Copperbelt adjacency)'),
    dict(slug='iberian-mediterranean', name='Iberian Mediterranean Basin',
         colonial='Madrid / Barcelona / Lisbon / Seville',
         archaic='Al-Andalus · Iberia · Celtiberian · Visigoths · Phoenician Gades',
         min_lat=36.0, max_lat=44.0, min_lng=-9.0, max_lng=5.0,
         climate='Mediterranean — hot dry summers, mild wet winters; increasingly drought-prone',
         watershed='Tagus, Ebro, Guadalquivir — all heavily dammed; Doñana wetlands shrinking',
         tectonic='Eurasian/African plate boundary — Atlas uplift; Gibraltar Strait where two plates nearly touch',
         species='Iberian lynx (recovering), Spanish imperial eagle, Eurasian black vulture, Atlantic bluefin tuna, Posidonia seagrass',
         soil='Thin Mediterranean terra rossa and clay — millennia of erosion from deforestation; cork oak savannas (dehesa) exceptional biodiversity',
         vitality='Stressed — severe drought cycles, wildfire, soil erosion, aquifer depletion; Iberian lynx recovery is rare success story',
         connections='Atlantic and Mediterranean weather systems converge; African Saharan dust inputs; migratory flyway between Europe and Africa',
         resources='Copper and pyrite (Rio Tinto, Huelva — one of the oldest continuously mined sites on Earth, 5,000+ years), lithium (Barroso, Portugal — largest hard-rock lithium reserve in Europe), tungsten (Portugal — 2nd largest global producer), mercury (Almadén, Spain — historically world\'s largest deposit), iron ore (Bilbao region, historical industrial base)'),
    dict(slug='annamite-coast-highlands', name='Annamite Coast & Highlands',
         colonial='Hội An · Huế · Đà Nẵng · Vinh',
         archaic='Champa · Đại Việt · Nguyễn Lords · Lê Dynasty · Pathet Lao',
         min_lat=12.0, max_lat=20.0, min_lng=104.0, max_lng=109.0,
         climate='Tropical monsoon — reversed timing from rest of Vietnam; northeast monsoon drives heaviest rain Oct–Jan; the Lào foehn wind sweeps hot and dry westward off the mountains in spring–summer',
         watershed='Hương (Perfume River), Thu Bồn, Mã rivers — short, steep, draining east from the Annamite crest to the South China Sea; flash floods common; watershed divide with the Mekong basin lies just to the west',
         tectonic='Stable Indochina craton; Annamite Range (Trường Sơn) formed by ancient Indosinian orogeny — old, heavily eroded ridgeline; Pleistocene refugia here produced one of Asia\'s highest vertebrate biodiversity densities per km²',
         species='Saola (among the rarest mammals on Earth — fewer than 100 individuals confirmed), Annamite striped rabbit, giant muntjac, crested argus pheasant, Indochinese tiger (near-extinct), Sunda pangolin',
         soil='Laterite and ferralitic soils on highlands — highly leached; fertile alluvial strips along river deltas; pockets of Agent Orange dioxin contamination persist from the American War',
         vitality='Pressured — saola critically endangered; deforestation from agriculture and logging continues; unexploded ordnance across the highlands; coral reefs of the central coastal shelf declining from warming and runoff',
         connections='South China Sea to the east (typhoon exposure, fishing); Mekong basin to the west; one of the world\'s most critical bird migration corridors; Ho Chi Minh Trail left a unique war-shaped ecology across the range',
         resources='Titanium ilmenite (coastal sand from Bình Định to Quảng Trị — Vietnam holds world\'s 2nd largest TiO₂ reserves), bauxite (Central Highlands — 5.4 billion tonnes, 3rd globally), iron ore (Thạch Khê — one of Southeast Asia\'s largest deposits), coal (Quảng Bình), gold (Bồng Miêu, Quảng Nam), marble (Ngũ Hành Sơn, Đà Nẵng)'),
    dict(slug='korean-japanese-arc', name='East Asian Volcanic Arc',
         colonial='Seoul / Tokyo / Osaka',
         archaic='Joseon · Yamato · Goryeo · Baekje · Ainu Mosir (Hokkaido)',
         min_lat=33.0, max_lat=38.0, min_lng=126.0, max_lng=141.0,
         climate='Humid subtropical to temperate — monsoon summers, cold winters; typhoon season',
         watershed='Han, Nakdong, Kiso rivers — short, steep, flood-prone; no major shared international rivers',
         tectonic='Pacific Plate subducting under Eurasian — active volcanism (Fuji, Aso), frequent earthquakes, tsunamis',
         species='Amur leopard (critically endangered), red-crowned crane, Japanese macaque, Asian black bear, Pacific salmon runs',
         soil='Volcanic andisol — highly fertile, excellent water retention; paddy rice cultivation for 3,000+ years',
         vitality='Mixed — coastal marine systems stressed by overfishing; urban heat island severe; exceptional forest recovery since 1960s reforestation',
         connections='Tsushima warm current moderates climate; Yellow Sea shared with China; migratory birds link to Siberian breeding grounds',
         resources='Rare earth mineral seabed deposits (Japan\'s Pacific EEZ seamounts — potential world-scale reserves under active survey), zinc and lead (Komdok, North Korea), gold (Korea\'s Haean basin), sulfur (Japanese volcanic fields), manganese nodules (Pacific deep-sea basin); South Korea and Japan now import >90% of minerals but hold significant offshore and seabed claims'),
]


@router.post("/admin/seed-profiles", dependencies=[Depends(_require_admin)])
async def admin_seed_profiles(db: AsyncSession = Depends(get_db)):
    """Admin — seed all 13 bioregion profiles into bioregion_seed_profiles table.
    Idempotent: uses INSERT ... ON DUPLICATE KEY UPDATE so safe to run multiple times.
    Run once after DB migration to create the bioregion_seed_profiles table.
    """
    inserted = 0
    updated = 0
    for p in _SEED_PROFILES:
        existing = await db.execute(
            text("SELECT id FROM bioregion_seed_profiles WHERE slug = :slug"),
            {"slug": p["slug"]}
        )
        row = existing.fetchone()
        if row:
            await db.execute(
                text("""UPDATE bioregion_seed_profiles SET
                    name=:name, colonial=:colonial, archaic=:archaic,
                    min_lat=:min_lat, max_lat=:max_lat, min_lng=:min_lng, max_lng=:max_lng,
                    climate=:climate, watershed=:watershed, tectonic=:tectonic,
                    species=:species, soil=:soil, vitality=:vitality,
                    connections=:connections, resources=:resources
                    WHERE slug=:slug"""),
                p
            )
            updated += 1
        else:
            await db.execute(
                text("""INSERT INTO bioregion_seed_profiles
                    (slug, name, colonial, archaic, min_lat, max_lat, min_lng, max_lng,
                     climate, watershed, tectonic, species, soil, vitality, connections, resources)
                    VALUES
                    (:slug, :name, :colonial, :archaic, :min_lat, :max_lat, :min_lng, :max_lng,
                     :climate, :watershed, :tectonic, :species, :soil, :vitality, :connections, :resources)"""),
                p
            )
            inserted += 1
    await db.commit()
    return {"ok": True, "inserted": inserted, "updated": updated, "total": len(_SEED_PROFILES)}
