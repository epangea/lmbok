# ============================================================
# FreqLearn — routes/ollama_generate.py
# Local AI generation via Ollama — zero cost, zero dependency
#
# Setup on your DigitalOcean server:
#   curl -fsSL https://ollama.ai/install.sh | sh
#   ollama pull llama3.1:8b
#   ollama serve  (runs on port 11434)
#
# Then add to .env:
#   OLLAMA_URL=http://127.0.0.1:11434
#   OLLAMA_MODEL=llama3.1:8b
#
# The main generate.py route tries Anthropic first, then
# falls back to this if ANTHROPIC_API_KEY is not set.
# ============================================================

import os
import json
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


async def generate_with_ollama(prompt: str) -> tuple[dict, str]:
    """
    Call local Ollama instance and return (parsed_json, model_name).
    The model_name is prefixed with "ollama:" so the admin can distinguish
    Ollama-served sessions from Groq-served sessions at a glance.
    Raises HTTPException if Ollama is not available.
    """
    url = f"{OLLAMA_URL}/api/generate"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",   # tells Ollama to constrain output to JSON
                "options": {
                    "temperature": 0.8,
                    "top_p":       0.9,
                    "num_predict": 1200,
                }
            })
            response.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(
            503,
            "Local AI not available. Run: ollama serve"
        )
    except httpx.TimeoutException:
        raise HTTPException(504, "Local AI timed out — try a smaller model")

    data = response.json()
    raw  = data.get("response", "").strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw), f"ollama:{OLLAMA_MODEL}"
    except json.JSONDecodeError:
        # Ollama sometimes adds extra text — try to extract JSON object
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end]), f"ollama:{OLLAMA_MODEL}"
        raise HTTPException(500, f"Local AI returned invalid JSON: {raw[:200]}")


@router.get("/status")
async def ollama_status():
    """Check if Ollama is running and which model is loaded."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            models = r.json().get("models", [])
            return {
                "available": True,
                "url":       OLLAMA_URL,
                "model":     OLLAMA_MODEL,
                "all_models": [m["name"] for m in models],
            }
    except Exception as e:
        return {
            "available": False,
            "url":       OLLAMA_URL,
            "error":     str(e),
            "setup":     "Run: curl -fsSL https://ollama.ai/install.sh | sh && ollama pull llama3.1:8b"
        }
