# ============================================================
# FreqLearn — routes/ollama_generate.py
# Ollama status endpoint only. Actual generation calls all go through
# ai_client.ai_complete() now (P41, 2026-07-29) -- see ai_client.py's
# module docstring for the full story.
#
# Setup on the DigitalOcean server (requires >=2GB RAM droplet):
#   curl -fsSL https://ollama.ai/install.sh | sh
#   ollama pull llama3.1:8b
#   ollama serve  (runs on port 11434)
# Then set OLLAMA_URL in .env if not the default http://127.0.0.1:11434.
# Model names live in platform_settings (ai_model_ollama_large /
# ai_model_ollama_small), editable in Admin > Settings > AI generation.
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
import ai_client

router = APIRouter()


@router.get("/status")
async def ollama_status(db: AsyncSession = Depends(get_db)):
    """Check if Ollama is reachable and report the currently configured models."""
    return await ai_client.ollama_status(db)
