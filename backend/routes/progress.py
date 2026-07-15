# FreqLearn — routes/progress.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from models import LearnerSkillProgress, LearnerArtProgress, Learner
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
