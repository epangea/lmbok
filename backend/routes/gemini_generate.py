# ============================================================
# FreqLearn — routes/gemini_generate.py
# Gemini status endpoint only. Actual generation calls all go through
# ai_client.ai_complete() (see its module docstring) -- added 2026-07-29
# as a third free provider, since the server is currently too small to
# run Ollama locally and a second independent cloud provider is the
# practical redundancy in the meantime.
#
# Sign up: aistudio.google.com — free tier, no card needed.
# Add to .env: GEMINI_API_KEY=...
# Model names live in platform_settings (ai_model_gemini_large /
# ai_model_gemini_small), editable in Admin > Settings > AI generation.
# Uses Google's OpenAI-compatible endpoint, not the native Gemini SDK.
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
import ai_client

router = APIRouter()


@router.get("/status")
async def gemini_status(db: AsyncSession = Depends(get_db)):
    """Check Gemini API availability and report the currently configured models."""
    return await ai_client.gemini_status(db)
