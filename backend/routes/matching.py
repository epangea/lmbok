# ============================================================
# FreqLearn — routes/matching.py
# ============================================================

from datetime import datetime, timezone
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel

from db import get_db
from models import (
    Organization, OpportunityListing, OpportunityMatch, Message,
    LearnerSkillProgress, ArtsSkills, Arts, Learner,
)
from routes.auth import get_current_learner
from utils import get_learner_stage

router = APIRouter()

# ── Avatar stage → match bonus ────────────────────────────────
# Grove+ learners have demonstrated breadth across arts and domains.
# Their matches get a small bonus to surface opportunities that fit
# their growth pattern — not to reward gamification, but to surface
# the signal that they're genuinely multi-dimensional learners.
AVATAR_BONUS = {
    'seed':      0,
    'sprout':    0,
    'sapling':   0,
    'grove':     5,
    'forest':    8,
    'ecosystem': 12,
}

# Bioregion match bonus: local alignment matters.
BIOREGION_BONUS = 10


async def _score_listing(
    listing,
    art_scores: dict,
    avatar_key: str,
    learner_bioregion: Optional[str],
    org_bioregion: Optional[str],
) -> dict:
    required = listing.required_arts or []
    if isinstance(required, dict):
        required = list(required.keys())

    # Base score: art overlap
    if not required:
        base = 50
        met, gap = [], []
    else:
        met = [a for a in required if art_scores.get(a, 0) > 0]
        gap = [a for a in required if art_scores.get(a, 0) == 0]
        base = round(len(met) / len(required) * 100)

    # Avatar bonus
    bonus = AVATAR_BONUS.get(avatar_key, 0)

    # Bioregion bonus
    if (learner_bioregion and org_bioregion and
            learner_bioregion.strip().lower() == org_bioregion.strip().lower()):
        bonus += BIOREGION_BONUS

    score = min(base + bonus, 100)
    return {"match_score": score, "arts_met": met, "arts_gap": gap}


async def _learner_art_scores(learner_id: int, db: AsyncSession) -> dict:
    arts     = (await db.execute(select(Arts))).scalars().all()
    mappings = (await db.execute(select(ArtsSkills))).scalars().all()
    prog     = {p.skill_id: p for p in (await db.execute(
        select(LearnerSkillProgress).where(LearnerSkillProgress.learner_id == learner_id)
    )).scalars().all()}

    art_skill_ids: dict[int, list[int]] = {}
    for m in mappings:
        art_skill_ids.setdefault(m.art_id, []).append(m.skill_id)

    scores = {}
    for art in arts:
        sids = art_skill_ids.get(art.id, [])
        if not sids:
            scores[art.slug] = 0.0
            continue
        earned = sum(
            (prog[s].current_level or 0) +
            (min((prog[s].evidence_count or 0) / (((prog[s].current_level or 0)+1)*3), 1.0)
             if (prog[s].current_level or 0) < 3 else 0)
            for s in sids if s in prog
        )
        scores[art.slug] = round(min(earned / (len(sids)*3), 1.0), 3)
    return scores


async def _org_map(db: AsyncSession) -> dict:
    return {o.id: o for o in (await db.execute(
        select(Organization).where(Organization.is_active == True)
    )).scalars().all()}


def _listing_out(listing, scored: dict, org: Optional[Organization] = None) -> dict:
    required = listing.required_arts or []
    if isinstance(required, dict):
        required = list(required.keys())
    return {
        "id":           listing.id,
        "title":        listing.title,
        "description":  listing.description or "",
        "listing_type": listing.listing_type,
        "required_arts":required,
        "arts_met":     scored["arts_met"],
        "arts_gap":     scored["arts_gap"],
        "match_score":  scored["match_score"],
        "source_url":   listing.source_url,
        "org_id":       listing.org_id,
        "org_name":     org.name        if org else "Organization",
        "org_slug":     org.slug        if org else None,
        "org_website":  org.website     if org else None,
        "org_type":     org.org_type    if org else None,
        "org_verified": org.is_verified if org else False,
        "org_bioregion":org.bioregion   if org else None,
    }


# ── Routes ────────────────────────────────────────────────────

@router.get("/listings/top")
async def get_top_listing(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(OpportunityListing).where(OpportunityListing.is_active == True)
    )).scalars().all()
    if not rows:
        return None
    orgs   = await _org_map(db)
    scores = await _learner_art_scores(learner.id, db)
    stage  = await get_learner_stage(learner, db)
    avatar_key        = stage['key']
    learner_bioregion = learner.bioregion

    scored_list = await asyncio.gather(*[
        _score_listing(
            l, scores, avatar_key, learner_bioregion,
            orgs[l.org_id].bioregion if l.org_id in orgs else None
        )
        for l in rows
    ])
    ranked = sorted(
        zip(scored_list, rows),
        key=lambda x: (-x[0]["match_score"], x[1].id)
    )
    scored, best = ranked[0]
    return _listing_out(best, scored, orgs.get(best.org_id))


@router.get("/listings")
async def get_all_listings(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(OpportunityListing).where(OpportunityListing.is_active == True)
    )).scalars().all()
    if not rows:
        return []
    orgs   = await _org_map(db)
    scores = await _learner_art_scores(learner.id, db)
    stage  = await get_learner_stage(learner, db)
    avatar_key        = stage['key']
    learner_bioregion = learner.bioregion

    scored_list = await asyncio.gather(*[
        _score_listing(
            l, scores, avatar_key, learner_bioregion,
            orgs[l.org_id].bioregion if l.org_id in orgs else None
        )
        for l in rows
    ])
    out = [_listing_out(l, s, orgs.get(l.org_id)) for l, s in zip(rows, scored_list)]
    return sorted(out, key=lambda x: -x["match_score"])


@router.get("/")
async def get_my_matches(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(OpportunityMatch)
        .where(OpportunityMatch.learner_id == learner.id)
        .order_by(OpportunityMatch.matched_at.desc())
    )).scalars().all()
    return [
        {
            "id":             m.id,
            "listing_id":     m.listing_id,
            "match_score":    m.match_score,
            "learner_status": m.learner_status,
            "org_status":     m.org_status,
            "matched_at":     m.matched_at.isoformat() if m.matched_at else None,
        }
        for m in rows
    ]


@router.post("/")
async def express_interest(
    data: dict,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    listing_id = data.get("listing_id")
    if not listing_id:
        raise HTTPException(400, "listing_id required")
    existing = (await db.execute(
        select(OpportunityMatch).where(
            OpportunityMatch.learner_id == learner.id,
            OpportunityMatch.listing_id == listing_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"ok": True, "id": existing.id, "already_exists": True}
    match = OpportunityMatch(learner_id=learner.id, listing_id=listing_id,
                             learner_status="pending", org_status="pending")
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return {"ok": True, "id": match.id}


@router.delete("/{match_id}")
async def withdraw_interest(
    match_id: int,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    match = (await db.execute(
        select(OpportunityMatch).where(
            OpportunityMatch.id == match_id,
            OpportunityMatch.learner_id == learner.id,
        )
    )).scalar_one_or_none()
    if not match:
        raise HTTPException(404, "Match not found")
    await db.delete(match)
    await db.commit()
    return {"ok": True}


# ── Pnyx ─────────────────────────────────────────────────────

class MessageIn(BaseModel):
    body: str


@router.get("/{match_id}/messages")
async def get_messages(
    match_id: int,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    if not (await db.execute(
        select(OpportunityMatch).where(
            OpportunityMatch.id == match_id,
            OpportunityMatch.learner_id == learner.id,
        )
    )).scalar_one_or_none():
        raise HTTPException(404, "Match not found")
    rows = (await db.execute(
        select(Message).where(Message.match_id == match_id).order_by(Message.created_at.asc())
    )).scalars().all()
    return [{"id":m.id,"sender_type":m.sender_type,"body":m.body,
             "read_at":m.read_at.isoformat() if m.read_at else None,
             "created_at":m.created_at.isoformat() if m.created_at else None} for m in rows]


@router.post("/{match_id}/messages")
async def send_message(
    match_id: int,
    req: MessageIn,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    if not req.body.strip():
        raise HTTPException(400, "Body cannot be empty")
    if not (await db.execute(
        select(OpportunityMatch).where(
            OpportunityMatch.id == match_id,
            OpportunityMatch.learner_id == learner.id,
        )
    )).scalar_one_or_none():
        raise HTTPException(404, "Match not found")
    msg = Message(match_id=match_id, sender_type="learner", sender_id=learner.id,
                  body=req.body.strip(), created_at=datetime.now(timezone.utc))
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return {"ok":True,"id":msg.id,"sender_type":"learner","body":msg.body,
            "created_at":msg.created_at.isoformat()}
