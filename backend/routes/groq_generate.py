# ============================================================
# FreqLearn — routes/groq_generate.py
# Session generation via Groq API (free tier, no card needed)
# Sign up: console.groq.com
# Add to .env: GROQ_API_KEY=gsk_...
#
# Free tier limits (as of 2026):
#   - 6000 requests/day
#   - 14400 requests/minute  
#   - Models: llama-3.1-8b-instant, llama-3.1-70b-versatile
# ============================================================

import os, json, httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


async def generate_with_groq(prompt: str) -> tuple[dict, str]:
    """
    Call Groq API (OpenAI-compatible) and return (parsed_json, model_name).
    The model_name is the same string sent in the request payload, so the
    caller can persist it on the Session row for audit.
    Free tier — no credit card required at console.groq.com
    """
    if not GROQ_API_KEY:
        raise HTTPException(
            503,
            "Groq API key not configured. "
            "Sign up free at console.groq.com and add GROQ_API_KEY to .env"
        )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a learning session designer for a free global platform "
                    "called Surfing the Frequencies. You always respond with valid JSON only. "
                    "No preamble, no markdown, no explanation — just the JSON object."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature":  0.8,
        "max_tokens":   1200,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GROQ_URL, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(503, "Cannot reach Groq API")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(401, "Invalid Groq API key")
        if e.response.status_code == 429:
            raise HTTPException(429, "Groq rate limit reached — try again in a minute")
        raise HTTPException(500, f"Groq API error: {e.response.status_code}")

    data    = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    try:
        return json.loads(content), GROQ_MODEL
    except json.JSONDecodeError:
        # Try to extract JSON object from any surrounding text
        start = content.find("{")
        end   = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end]), GROQ_MODEL
        raise HTTPException(500, f"Groq returned invalid JSON: {content[:200]}")


@router.get("/status")
async def groq_status():
    """Check Groq API availability."""
    if not GROQ_API_KEY:
        return {
            "available": False,
            "message":   "Sign up free at console.groq.com — no credit card needed",
            "setup":     "Add GROQ_API_KEY=gsk_... to your .env file",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"}
            )
            models = [m["id"] for m in r.json().get("data", [])]
            return {
                "available": True,
                "model":     GROQ_MODEL,
                "models":    models,
            }
    except Exception as e:
        return {"available": False, "error": str(e)}
