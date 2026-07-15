# FreqLearn — routes/skills.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from models import Skill, Arts, ArtsGroup

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
