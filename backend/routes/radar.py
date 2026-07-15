# FreqLearn — routes/radar.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from db import get_db
from models import RadarSnapshot, Learner
from routes.auth import get_current_learner
from engine import RecommendationEngine

router = APIRouter()
eng = RecommendationEngine()

@router.get("/current")
async def get_current_radar(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """Live radar — recomputed from current progress."""
    return await eng.compute_radar(learner.id, db)

@router.get("/snapshots")
async def get_snapshots(
    limit: int = 10,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """Historical snapshots for the 'compare over time' feature."""
    result = await db.execute(
        select(RadarSnapshot)
        .where(RadarSnapshot.learner_id == learner.id)
        .order_by(desc(RadarSnapshot.created_at))
        .limit(limit)
    )
    return result.scalars().all()
