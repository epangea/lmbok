# FreqLearn, routes/progress.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from db import get_db
from models import LearnerSkillProgress, LearnerArtProgress, Learner, Skill, Arts, ArtsSkills
from routes.auth import get_current_learner

router = APIRouter()

@router.get("/skills")
async def get_skill_progress(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LearnerSkillProgress)
        .where(LearnerSkillProgress.learner_id == learner.id)
    )
    return result.scalars().all()

@router.get("/arts")
async def get_art_progress(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LearnerArtProgress)
        .where(LearnerArtProgress.learner_id == learner.id)
    )
    return result.scalars().all()


@router.get("/skills-by-art")
async def get_skills_by_art(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    The learner's skills with the Arts each one feeds (2026-11-13, Portfolio
    Growth and Skills tabs). One row per skill the learner has any progress on,
    with the skill's name and domain, level, evidence, and the slugs of the Arts
    it is mapped to in arts_skills, the same mapping engine.compute_radar builds
    the Art scores from (is_primary is ignored there, so it is here too).

    'practiced' is True once a completed session stamped last_practiced_at.
    False means the row only holds a starting point written at onboarding
    (evidence or a level with no practice behind it); those rows still count
    toward the Art scores, which is why they are returned.
    """
    rows = (await db.execute(
        select(LearnerSkillProgress, Skill.name, Skill.learning_domain)
        .join(Skill, Skill.id == LearnerSkillProgress.skill_id)
        .where(
            LearnerSkillProgress.learner_id == learner.id,
            or_(LearnerSkillProgress.evidence_count > 0,
                LearnerSkillProgress.current_level > 0),
        )
        .order_by(Skill.name)
    )).all()

    arts_by_skill: dict[int, list[str]] = {}
    skill_ids = [p.skill_id for p, _, _ in rows]
    if skill_ids:
        mapped = (await db.execute(
            select(ArtsSkills.skill_id, Arts.slug)
            .join(Arts, Arts.id == ArtsSkills.art_id)
            .where(ArtsSkills.skill_id.in_(skill_ids))
            .order_by(Arts.sort_order)
        )).all()
        for sid, slug in mapped:
            arts_by_skill.setdefault(sid, []).append(slug)

    return [
        {
            "skill_id":          p.skill_id,
            "name":              name,
            "domain":            domain,
            "level":             p.current_level or 0,
            "evidence":          p.evidence_count or 0,
            "practiced":         p.last_practiced_at is not None,
            "last_practiced_at": p.last_practiced_at.isoformat() if p.last_practiced_at else None,
            "arts":              arts_by_skill.get(p.skill_id, []),
        }
        for p, name, domain in rows
    ]
