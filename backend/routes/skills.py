# FreqLearn — routes/skills.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from models import Skill, Arts, ArtsGroup, DevPhase
from mouseion_domains import MOUSEION_DOMAIN_SKILLS

router = APIRouter()

@router.get("/arts")
async def get_arts(db: AsyncSession = Depends(get_db)):
    """Return all 15 arts with their group, for the Mouseion."""
    result = await db.execute(select(Arts).order_by(Arts.sort_order))
    return result.scalars().all()

@router.get("/arts-groups")
async def get_arts_groups(db: AsyncSession = Depends(get_db)):
    """Return the three arts groups (Being / Becoming / Connecting)."""
    result = await db.execute(select(ArtsGroup).order_by(ArtsGroup.sort_order))
    return result.scalars().all()

@router.get("/")
async def get_skills(db: AsyncSession = Depends(get_db)):
    """Return all active skills."""
    result = await db.execute(
        select(Skill).where(Skill.is_active == True).order_by(Skill.sort_order)
    )
    return result.scalars().all()

@router.get("/mouseion-domains")
async def get_mouseion_domains():
    """
    Public: the 8 Mouseion domains and their 48 skills. Added 2026-08-22 as
    the canonical source any page can fetch instead of re-hardcoding the
    grid — first consumer is contribute.html's LECKO domain/skill selects.
    Sourced from mouseion_domains.py (see that module's header for why this
    isn't derived from Skill.learning_domain directly).
    """
    return [
        {"domain": domain, "skills": skills}
        for domain, skills in MOUSEION_DOMAIN_SKILLS.items()
    ]

@router.get("/phases")
async def get_phases(db: AsyncSession = Depends(get_db)):
    """
    Public: all developmental phases (dev_phases table), ordered for display.
    Added 2026-08-22 as the canonical source for age-range selectors —
    first consumer is contribute.html's "Who is it for?" select, which
    previously hardcoded a stale/incomplete copy (backlog 2026.125). This is
    the same table contribute.py already validates phase_slug against, and
    the same slug set frontend/app.js's PHASES array mirrors for onboarding
    and preferences.
    """
    result = await db.execute(select(DevPhase).order_by(DevPhase.sort_order))
    return result.scalars().all()
