# ============================================================
# FreqLearn — ai_client.py
# Provider-agnostic AI client abstraction.
#
# Design (per PART 20 — 2026-06-28):
#   - AI is the source of truth for session generation
#   - DB sessions are a fallback library, not the default
#   - Library fallback filters on (art_id, primary_skill_id, dev_phase_id, language)
#     and excludes sessions the learner has already experienced
#   - Library recall respects the "ai_library_recall_limit" platform setting
#     when scanning the learner's history for deduplication
#   - No token counts, no costs, no financial metrics logged (per project philosophy)
#
# Provider chain is configurable via platform_settings.ai_provider:
#   - 'groq'      → GroqAIClient (primary, free tier)
#   - 'ollama'    → OllamaAIClient (local, zero cost)
#   - 'library'   → LibraryAIClient (no AI, only DB) — used for tests/fallback-only mode
# ============================================================

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AIResponse:
    """Standardised result from any AIClient.complete_json call."""
    content: dict                        # parsed JSON the AI returned
    model: str                           # which model answered, or 'library'
    latency_ms: int                      # wall-clock time in ms (0 for library)
    served_from_cache: bool = False      # True if LibraryAIClient served this


class AIClient(ABC):
    """Abstract base — every provider implements complete_json()."""

    @abstractmethod
    async def complete_json(
        self,
        prompt: str,
        system_msg: str,
        *,
        db: Optional[AsyncSession] = None,
        learner_id: Optional[int] = None,
        art_id: Optional[int] = None,
        primary_skill_id: Optional[int] = None,
        dev_phase_id: Optional[int] = None,
        language: Optional[str] = None,
    ) -> AIResponse:
        """Call the AI, return parsed JSON + metadata. Raise HTTPException on failure."""
        raise NotImplementedError


# ── Groq ─────────────────────────────────────────────────────

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


class GroqAIClient(AIClient):
    """Free-tier Groq API (OpenAI-compatible chat completions)."""

    async def complete_json(
        self,
        prompt: str,
        system_msg: str,
        *,
        db: Optional[AsyncSession] = None,
        learner_id: Optional[int] = None,
        art_id: Optional[int] = None,
        primary_skill_id: Optional[int] = None,
        dev_phase_id: Optional[int] = None,
        language: Optional[str] = None,
    ) -> AIResponse:
        if not GROQ_API_KEY:
            raise HTTPException(503, "GROQ_API_KEY not configured")

        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": prompt},
            ],
            "temperature":     0.8,
            "max_tokens":      1200,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type":  "application/json",
        }

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=payload)
                resp.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(503, "Cannot reach Groq API")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise HTTPException(401, "Invalid Groq API key")
            if e.response.status_code == 429:
                raise HTTPException(429, "Groq rate limit reached")
            raise HTTPException(500, f"Groq API error: {e.response.status_code}")
        latency_ms = int((time.monotonic() - t0) * 1000)

        data    = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from surrounding text
            start = content.find("{")
            end   = content.rfind("}") + 1
            if start != -1 and end > start:
                parsed = json.loads(content[start:end])
            else:
                raise HTTPException(500, f"Groq returned invalid JSON: {content[:200]}")

        return AIResponse(content=parsed, model=GROQ_MODEL, latency_ms=latency_ms)


# ── Ollama ───────────────────────────────────────────────────

OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


class OllamaAIClient(AIClient):
    """Local Ollama instance — zero cost, no external dependency."""

    async def complete_json(
        self,
        prompt: str,
        system_msg: str,
        **kwargs,
    ) -> AIResponse:
        url = f"{OLLAMA_URL}/api/generate"
        full_prompt = f"{system_msg}\n\n{prompt}"

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json={
                    "model":  OLLAMA_MODEL,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.8,
                        "top_p":       0.9,
                        "num_predict": 1200,
                    },
                })
                resp.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(503, "Local Ollama not available")
        except httpx.TimeoutException:
            raise HTTPException(504, "Local Ollama timed out")
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = resp.json().get("response", "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                parsed = json.loads(raw[start:end])
            else:
                raise HTTPException(500, f"Ollama returned invalid JSON: {raw[:200]}")

        return AIResponse(content=parsed, model=f"ollama:{OLLAMA_MODEL}", latency_ms=latency_ms)


# ── Library (DB cache fallback) ─────────────────────────────

class LibraryAIClient(AIClient):
    """Serves a session from the local DB based on the same filters
    the original AI generation used: art, primary skill, dev phase,
    language, and excluding sessions the learner has already seen.
    """

    def __init__(self, recall_limit: int = 200):
        self.recall_limit = recall_limit

    async def complete_json(
        self,
        prompt: str,
        system_msg: str,
        *,
        db: AsyncSession,
        learner_id: int,
        art_id: int,
        primary_skill_id: Optional[int] = None,
        dev_phase_id: Optional[int] = None,
        language: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        from models import Session  # local import to avoid circular

        # Build the dedup set: warmup_prompts the learner has seen
        # in their last `recall_limit` sessions for this art.
        seen_q = await db.execute(
            select(Session.warmup_prompt)
            .where(Session.learner_id == learner_id, Session.art_id == art_id)
            .order_by(Session.created_at.desc())
            .limit(self.recall_limit)
        )
        recently_seen = {row[0] for row in seen_q.all() if row[0]}

        # Query the library for matching sessions
        lib_q = select(Session).where(
            Session.art_id == art_id,
            Session.warmup_prompt != None,
        )
        if primary_skill_id is not None:
            lib_q = lib_q.where(Session.primary_skill_id == primary_skill_id)
        if dev_phase_id is not None:
            lib_q = lib_q.where(Session.dev_phase_id.in_([dev_phase_id, None]))
        if language is not None:
            lib_q = lib_q.where((Session.language == language) | (Session.language == None))

        lib_q = lib_q.order_by(Session.created_at.desc()).limit(50)
        result = await db.execute(lib_q)
        candidates = result.scalars().all()

        # Filter to ones the learner hasn't seen
        unseen = [s for s in candidates if s.warmup_prompt not in recently_seen]
        if not unseen:
            # No fresh content available — caller will turn this into a 503
            raise HTTPException(
                503,
                "AI assistant currently unavailable - try again later. "
                "No matching library session for this learner either."
            )

        import random
        chosen = random.choice(unseen)

        content = {
            "title":            chosen.title,
            "warmup":           chosen.warmup_prompt,
            "explore":          chosen.explore_content,
            "challenge":        chosen.challenge_prompt,
            "reflect":          chosen.reflect_prompt,
            "assess_question":  chosen.assess_question.get("question") if chosen.assess_question else "",
            "assess_options":   chosen.assess_question.get("options", []) if chosen.assess_question else [],
            "assess_correct":   chosen.assess_question.get("correct_index") if chosen.assess_question else 0,
        }
        return AIResponse(
            content=content,
            model="library",
            latency_ms=0,
            served_from_cache=True,
        )


# ── Factory ─────────────────────────────────────────────────

async def get_primary_ai_client(db: AsyncSession) -> AIClient:
    """Read platform_settings.ai_provider and return the matching client.
    Falls back to Groq if the setting is missing or unrecognised.
    """
    from sqlalchemy import text
    try:
        row = (await db.execute(
            text("SELECT value FROM platform_settings WHERE key_name = 'ai_provider'")
        )).first()
        provider = (row[0] if row else "groq") or "groq"
    except Exception:
        provider = "groq"

    if provider == "ollama":
        return OllamaAIClient()
    if provider == "library":
        return LibraryAIClient()
    # Default and explicit 'groq'
    return GroqAIClient()


async def get_secondary_ai_client(db: AsyncSession) -> Optional[AIClient]:
    """The fallback provider if the primary fails. Currently Ollama is the
    only secondary — Groq doesn't have a meaningful secondary of its own.
    """
    return OllamaAIClient()


async def read_breaker_enabled(db: AsyncSession) -> bool:
    """Read platform_settings.ai_circuit_breaker_enabled. Default True."""
    from sqlalchemy import text
    try:
        row = (await db.execute(
            text("SELECT value FROM platform_settings WHERE key_name = 'ai_circuit_breaker_enabled'")
        )).first()
        if not row:
            return True
        v = (row[0] or "true").strip().lower()
        return v in ("true", "1", "yes", "on")
    except Exception:
        return True


async def read_library_recall_limit(db: AsyncSession) -> int:
    """Read platform_settings.ai_library_recall_limit. Default 200."""
    from sqlalchemy import text
    try:
        row = (await db.execute(
            text("SELECT value FROM platform_settings WHERE key_name = 'ai_library_recall_limit'")
        )).first()
        if not row or not row[0]:
            return 200
        return max(1, int(row[0]))
    except Exception:
        return 200


async def read_include_prior_context(db: AsyncSession) -> bool:
    """Read platform_settings.ai_include_prior_context. Default True."""
    from sqlalchemy import text
    try:
        row = (await db.execute(
            text("SELECT value FROM platform_settings WHERE key_name = 'ai_include_prior_context'")
        )).first()
        if not row:
            return True
        v = (row[0] or "true").strip().lower()
        return v in ("true", "1", "yes", "on")
    except Exception:
        return True
