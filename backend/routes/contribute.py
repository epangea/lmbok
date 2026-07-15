# ============================================================
# FreqLearn — routes/contribute.py
# Community LECKO contribution portal (Wikipedia-style)
#
# Public endpoints (no auth required):
#   GET  /api/contribute/leckos          — browse approved LECKOs
#   POST /api/contribute/leckos          — submit a new LECKO
#
# Admin endpoints (require auth + admin flag - future):
#   GET  /api/contribute/leckos/pending  — list pending submissions
#   PATCH /api/contribute/leckos/{id}    — approve or reject
# ============================================================

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from db import get_db
from models import Lecko, Arts, DevPhase

router = APIRouter()


class LeckoSubmit(BaseModel):
    title:           str
    art_slug:        str
    phase_slug:      str
    description:     Optional[str] = None
    community_need:  Optional[str] = None
    assessment_desc: Optional[str] = None
    source_credit:   Optional[str] = None
    evidence_url:    Optional[str] = None
    learning_domain: Optional[str] = None
    submitter_name:  Optional[str] = None   # not stored in DB, kept for future contact log


class LeckoReview(BaseModel):
    approved: bool
    note:     Optional[str] = None


def _lecko_dict(lecko: Lecko, art_name: str = "", phase_name: str = "") -> dict:
    return {
        "id":              lecko.id,
        "title":           lecko.title,
        "description":     lecko.description,
        "community_need":  lecko.community_need,
        "assessment_desc": lecko.assessment_desc,
        "assessment_type": lecko.assessment_type,
        "learning_domain": lecko.learning_domain,
        "source_credit":   lecko.source_credit,
        "evidence_url":    lecko.evidence_url,
        "utility_score":   lecko.utility_score,
        "is_active":       lecko.is_active,
        "art_id":          lecko.art_id,
        "art_name":        art_name,
        "phase_id":        lecko.phase_id,
        "phase_name":      phase_name,
        "created_at":      lecko.created_at.isoformat() if lecko.created_at else None,
    }


@router.get("/leckos")
async def list_leckos(
    art_slug:   Optional[str] = None,
    phase_slug: Optional[str] = None,
    limit:      int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Browse approved (is_active=True) LECKOs, optionally filtered by art or phase."""
    q = select(Lecko).where(Lecko.is_active == True)

    if art_slug:
        art_q = await db.execute(select(Arts).where(Arts.slug == art_slug))
        art   = art_q.scalar_one_or_none()
        if art:
            q = q.where(Lecko.art_id == art.id)

    if phase_slug:
        ph_q  = await db.execute(select(DevPhase).where(DevPhase.slug == phase_slug))
        phase = ph_q.scalar_one_or_none()
        if phase:
            q = q.where(Lecko.phase_id == phase.id)

    q = q.order_by(desc(Lecko.utility_score), desc(Lecko.created_at)).limit(limit)
    result = await db.execute(q)
    leckos = result.scalars().all()

    # Fetch art and phase names for display
    arts_q  = await db.execute(select(Arts))
    art_map = {a.id: a.name for a in arts_q.scalars().all()}
    ph_q2   = await db.execute(select(DevPhase))
    ph_map  = {p.id: p.name for p in ph_q2.scalars().all()}

    return [_lecko_dict(l, art_map.get(l.art_id,""), ph_map.get(l.phase_id,"")) for l in leckos]


@router.get("/leckos/pending")
async def list_pending(
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Admin: list pending (is_active=False) community submissions."""
    result = await db.execute(
        select(Lecko)
        .where(Lecko.is_active == False)
        .order_by(desc(Lecko.created_at))
        .limit(limit)
    )
    leckos = result.scalars().all()
    arts_q = await db.execute(select(Arts))
    art_map = {a.id: a.name for a in arts_q.scalars().all()}
    ph_q   = await db.execute(select(DevPhase))
    ph_map = {p.id: p.name for p in ph_q.scalars().all()}
    return [_lecko_dict(l, art_map.get(l.art_id,""), ph_map.get(l.phase_id,"")) for l in leckos]


@router.post("/leckos")
async def submit_lecko(
    req: LeckoSubmit,
    db: AsyncSession = Depends(get_db)
):
    """Public: submit a new LECKO for review. No login required."""
    if not req.title or not req.title.strip():
        raise HTTPException(400, "Title is required")

    art_q = await db.execute(select(Arts).where(Arts.slug == req.art_slug))
    art   = art_q.scalar_one_or_none()
    if not art:
        raise HTTPException(400, f"Unknown art: {req.art_slug}")

    ph_q  = await db.execute(select(DevPhase).where(DevPhase.slug == req.phase_slug))
    phase = ph_q.scalar_one_or_none()
    if not phase:
        raise HTTPException(400, f"Unknown phase: {req.phase_slug}")

    lecko = Lecko(
        art_id          = art.id,
        phase_id        = phase.id,
        title           = req.title.strip(),
        description     = req.description,
        community_need  = req.community_need,
        assessment_desc = req.assessment_desc,
        assessment_type = "task",
        learning_domain = req.learning_domain,
        source_credit   = req.source_credit,
        evidence_url    = req.evidence_url,
        utility_score   = 0.0,
        is_active       = False,   # pending review
        created_at      = datetime.now(timezone.utc),
    )
    db.add(lecko)
    await db.commit()
    await db.refresh(lecko)
    return {"ok": True, "id": lecko.id, "message": "Thank you — your LECKO has been submitted for review."}


@router.patch("/leckos/{lecko_id}")
async def review_lecko(
    lecko_id: int,
    req: LeckoReview,
    db: AsyncSession = Depends(get_db)
):
    """Admin: approve or reject a pending LECKO."""
    result = await db.execute(select(Lecko).where(Lecko.id == lecko_id))
    lecko  = result.scalar_one_or_none()
    if not lecko:
        raise HTTPException(404, "LECKO not found")

    if req.approved:
        lecko.is_active    = True
        lecko.utility_score = 1.0
    else:
        await db.delete(lecko)

    await db.commit()
    return {"ok": True, "approved": req.approved}
