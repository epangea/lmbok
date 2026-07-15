# FreqLearn — routes/learners.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from models import Learner, LearnerStreak, LearnerPreferences
from routes.auth import get_current_learner

router = APIRouter()

@router.get("/me")
async def get_me(learner: Learner = Depends(get_current_learner)):
    return {
        "id":           learner.id,
        "username":     learner.username,
        "display_name": learner.display_name,
        "birth_year":   learner.birth_year,
        "avatar_emoji": learner.avatar_emoji,
        "avatar_color": learner.avatar_color,
        "phase_id":     learner.phase_id,
        "language":     learner.language or "en",
        "created_at":   learner.created_at,
    }

@router.get("/me/streak")
async def get_streak(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LearnerStreak).where(LearnerStreak.learner_id == learner.id)
    )
    streak = result.scalar_one_or_none()
    if not streak:
        return {"current_streak": 0, "longest_streak": 0, "total_sessions": 0, "total_xp": 0}
    return streak


from pydantic import BaseModel
from typing import Optional
from sqlalchemy import update

class PreferencesUpdate(BaseModel):
    avatar_emoji:  Optional[str] = None
    avatar_color:  Optional[str] = None
    phase:         Optional[str] = None
    display_name:  Optional[str] = None
    first_art:     Optional[str] = None
    language:      Optional[str] = None

@router.patch("/me/preferences")
async def update_preferences(
    req: PreferencesUpdate,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    from models import DevPhase
    from sqlalchemy import select as sel

    # Update learner fields
    if req.avatar_emoji:  learner.avatar_emoji = req.avatar_emoji
    if req.avatar_color:  learner.avatar_color  = req.avatar_color
    if req.display_name:  learner.display_name  = req.display_name
    if req.language:      learner.language       = req.language

    # Update phase
    if req.phase:
        phase_q = await db.execute(sel(DevPhase).where(DevPhase.slug == req.phase))
        phase = phase_q.scalar_one_or_none()
        if phase:
            learner.phase_id = phase.id

    await db.commit()
    return {"ok": True}
# ============================================================
# ADD THIS BLOCK TO routes/learners.py
# Paste after the existing @router.patch("/me/preferences") block.
# Also add these imports at the top of learners.py if not present:
#   from models import ArtsGroup, Arts, ArtsSkills, LearnerSkillProgress
#   from datetime import datetime, timezone
# ============================================================

from pydantic import BaseModel as _BaseModel

from models import ArtsGroup, Arts, ArtsSkills, LearnerSkillProgress
from datetime import datetime, timezone

class SeedProgressRequest(_BaseModel):
    # Keys: "being", "becoming", "connecting"
    # Values: 0 = new, 1 = some experience, 2 = comfortable
    familiarity: dict


@router.post("/me/seed-progress")
async def seed_initial_progress(
    req: SeedProgressRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Called once after onboarding. Seeds learner_skill_progress rows
    based on self-reported familiarity per art group, so the
    recommendation engine has real signal from the very first session.

    Familiarity levels:
      0 = new        → evidence_count=1,  current_level=0
      1 = some       → evidence_count=2,  current_level=0
      2 = comfortable → evidence_count=0, current_level=1
    """
    # Load group → arts → skills mapping
    groups_q = await db.execute(select(ArtsGroup))
    groups   = {g.slug: g for g in groups_q.scalars().all()}

    arts_q = await db.execute(select(Arts))
    arts   = arts_q.scalars().all()

    mappings_q = await db.execute(select(ArtsSkills))
    mappings   = mappings_q.scalars().all()

    # Build group_slug → [skill_ids]
    art_to_group  = {a.id: a.group_id for a in arts}
    group_id_map  = {g.id: slug for slug, g in groups.items()}
    group_skills: dict[str, list[int]] = {}
    for m in mappings:
        gslug = group_id_map.get(art_to_group.get(m.art_id))
        if gslug:
            group_skills.setdefault(gslug, []).append(m.skill_id)

    # Existing progress rows (don't overwrite real progress)
    existing_q = await db.execute(
        select(LearnerSkillProgress)
        .where(LearnerSkillProgress.learner_id == learner.id)
    )
    existing_ids = {p.skill_id for p in existing_q.scalars().all()}

    seeded = 0
    now    = datetime.now(timezone.utc)

    for group_slug, fam_level in req.familiarity.items():
        fam_level = int(fam_level)
        skill_ids = group_skills.get(group_slug, [])

        if fam_level == 0:
            ev, lv = 1, 0     # new: tiny signal, no level
        elif fam_level == 1:
            ev, lv = 2, 0     # some: approaching level 1
        else:
            ev, lv = 0, 1     # comfortable: already at level 1

        for sid in skill_ids:
            if sid in existing_ids:
                continue      # never overwrite real session progress
            db.add(LearnerSkillProgress(
                learner_id=learner.id,
                skill_id=sid,
                current_level=lv,
                evidence_count=ev,
                recall_count=ev,
                last_practiced_at=None,
            ))
            seeded += 1

    await db.commit()
    return {"seeded": seeded}
