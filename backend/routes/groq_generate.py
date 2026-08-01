# ============================================================
# FreqLearn — routes/groq_generate.py
# Groq status endpoint only. Actual generation calls all go through
# ai_client.ai_complete() now (P41, 2026-07-29) -- this file used to
# also hold a generate_with_groq() helper that routes/generate.py
# called directly, hardcoding the model and bypassing the admin
# ai_provider setting entirely. That's gone; see ai_client.py's
# module docstring for the full story.
#
# Sign up: console.groq.com — free tier, no card needed.
# Add to .env: GROQ_API_KEY=gsk_...
# Model names live in platform_settings (ai_model_groq_large /
# ai_model_groq_small), editable in Admin > Settings > AI generation.
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
import ai_client

router = APIRouter()


@router.get("/status")
async def groq_status(db: AsyncSession = Depends(get_db)):
    """Check Groq API availability and report the currently configured models."""
    return await ai_client.groq_status(db)
