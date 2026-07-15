# ============================================================
# FreqLearn — routes/reflections.py
# Stoa: personal reflection journal
# GET  /api/reflections       — recent entries for learner
# POST /api/reflections       — save a new entry
# DELETE /api/reflections/{id} — delete an entry
# ============================================================

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional

from db import get_db
from models import Reflection, Learner
from routes.auth import get_current_learner

router = APIRouter()


class ReflectionCreate(BaseModel):
    body:       str
    prompt:     Optional[str] = None
    session_id: Optional[int] = None
    art_id:     Optional[int] = None
    is_private: bool = True


@router.get("/")
async def list_reflections(
    limit: int = 20,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Reflection)
        .where(Reflection.learner_id == learner.id)
        .order_by(desc(Reflection.created_at))
        .limit(limit)
    )
    entries = result.scalars().all()
    return [
        {
            "id":         e.id,
            "body":       e.body,
            "prompt":     e.prompt,
            "session_id": e.session_id,
            "art_id":     e.art_id,
            "is_private": e.is_private,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


@router.post("/")
async def save_reflection(
    req: ReflectionCreate,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    if not req.body or not req.body.strip():
        raise HTTPException(400, "Reflection body cannot be empty")

    entry = Reflection(
        learner_id = learner.id,
        body       = req.body.strip(),
        prompt     = req.prompt,
        session_id = req.session_id,
        art_id     = req.art_id,
        is_private = req.is_private,
        created_at = datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {
        "ok":         True,
        "id":         entry.id,
        "created_at": entry.created_at.isoformat(),
    }


@router.delete("/{reflection_id}")
async def delete_reflection(
    reflection_id: int,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Reflection).where(
            Reflection.id == reflection_id,
            Reflection.learner_id == learner.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Reflection not found")
    await db.delete(entry)
    await db.commit()
    return {"ok": True}
