# ============================================================
# FreqLearn — ai_client.py
# THE single AI-calling module for the entire codebase.
#
# Rewritten 2026-07-29 (P41). Before this, six different files each had
# their own copy-pasted "call Groq via httpx, parse JSON defensively"
# block, with model names hardcoded or scattered across env vars with
# silently different fallback defaults (llama-3.1-8b-instant in three
# places, llama-3.3-70b-versatile in four others) -- and NONE of them
# actually consulted platform_settings.ai_provider. The admin "AI
# provider" dropdown existed and looked functional but did nothing:
# every route called Groq directly regardless of what was selected.
#
# Gemini added 2026-07-29 (same day, follow-up) as a third free provider
# -- Charbel's server is currently too small to run Ollama locally, so a
# second independent cloud provider is the practical redundancy for now.
# Uses Google's OpenAI-compatible endpoint, so it reuses the same request/
# response shape as Groq rather than needing a separate native-API client.
#
# Every AI call in the codebase now goes through ai_complete() below.
# There is no other way to call an LLM in this project.
#
# What's admin-configurable (platform_settings, no restart needed):
#   ai_provider              -- 'groq' | 'ollama' | 'gemini' | 'library'
#   ai_model_groq_large      -- Groq model for content-quality calls
#   ai_model_groq_small      -- Groq model for lightweight/classification calls
#   ai_model_ollama_large    -- same split for Ollama
#   ai_model_ollama_small
#   ai_model_gemini_large    -- same split for Gemini
#   ai_model_gemini_small
#   ai_circuit_breaker_enabled / ai_library_failure_threshold / ai_library_mode_ttl
# What's still env-var (infra, not model/engine selection):
#   GROQ_API_KEY, OLLAMA_URL, GEMINI_API_KEY -- secrets and network
#   endpoints, not provider or model choice, so these stay out of the
#   admin UI.
#
# 'library' as ai_provider means "no live AI, ever" -- ai_complete()
# raises a clear 503 immediately rather than trying to reach any provider.
# This is deliberate: an admin who has selected Library-only means it.
# Only the /session route has an actual content library to fall back to
# (see routes/generate.py's own _serve_from_library) -- that is
# app-specific business logic (it persists real Session rows), not
# something this generic module owns.
#
# Every call site gets automatic fallback across the other free providers
# (if the selected one fails, the others are tried in turn) and a
# per-purpose circuit breaker (repeated failures for one feature,
# e.g. Scavenger, don't have to keep re-timing-out on every request --
# see CircuitBreaker below). This is strictly more resilient than the
# old per-file code, most of which had zero fallback and zero breaker.
# ============================================================

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 2026-08-04: added after a live P42 e2e run surfaced a Groq 400 and a
# Gemini 404 with nothing to diagnose them by -- every provider failure
# used to collapse straight to a bare RuntimeError(f"... error: {status}"),
# throwing the actual response body away. Matches the logger naming
# pattern orgs.py/admin.py already use (freqlearn.<module>) and the same
# fix shape used for the 2026-07-28 parse_listing_needs 503 -- log the raw
# body so a future failure is diagnosable straight from
# /var/log/freqlearn/api-error.log, without needing a manual curl.
logger = logging.getLogger("freqlearn.ai_client")


# ── Infra config (env vars -- secrets/endpoints, not model selection) ──

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Google's OpenAI-compatible endpoint -- same request/response shape as
# Groq's, so _call_gemini() below is nearly identical to _call_groq().
GEMINI_URL     = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

ALL_PROVIDERS = ("groq", "ollama", "gemini")


# ── Admin-configurable settings (platform_settings table) ──────

# These defaults only apply if a row is genuinely missing from the DB
# (fresh install, migration not yet run) -- they are an emergency
# fallback, not a place model names are meant to live long-term. The
# real, current values always come from platform_settings, editable
# in Admin > Settings > AI generation with no restart required.
_AI_DEFAULTS: dict[str, str] = {
    "ai_provider":                  "groq",
    "ai_model_groq_large":          "openai/gpt-oss-120b",
    "ai_model_groq_small":          "openai/gpt-oss-20b",
    "ai_model_ollama_large":        "llama3.1:8b",
    "ai_model_ollama_small":        "llama3.1:8b",
    "ai_model_gemini_large":        "gemini-2.5-flash",
    "ai_model_gemini_small":        "gemini-2.5-flash-lite",
    "ai_circuit_breaker_enabled":   "true",
    "ai_include_prior_context":     "true",
    "ai_library_recall_limit":      "200",
    "ai_inline_reuse_enabled":      "false",
    "ai_library_failure_threshold": "3",
    "ai_library_mode_ttl":          "600",
}


async def get_ai_settings(db: AsyncSession) -> dict[str, str]:
    """The one place every route reads AI settings from. Reads fresh on
    every call (cheap, single indexed query) so an admin's change in
    Settings takes effect on the very next request, no restart.
    """
    try:
        placeholders = ", ".join(f"'{k}'" for k in _AI_DEFAULTS)
        rows = await db.execute(
            text(f"SELECT key_name, value FROM platform_settings WHERE key_name IN ({placeholders})")
        )
        out = dict(_AI_DEFAULTS)
        for k, v in rows.all():
            if v is not None and str(v).strip() != "":
                out[k] = str(v)
        return out
    except Exception:
        # platform_settings missing entirely (pre-migration DB) -- defaults.
        return dict(_AI_DEFAULTS)


def bool_setting(settings: dict[str, str], key: str) -> bool:
    return settings.get(key, _AI_DEFAULTS[key]).strip().lower() in ("true", "1", "yes", "on")


def int_setting(settings: dict[str, str], key: str) -> int:
    try:
        return int(settings.get(key, _AI_DEFAULTS[key]))
    except (TypeError, ValueError):
        return int(_AI_DEFAULTS[key])


# ── Circuit breaker, one instance per "purpose" ─────────────────
# Spec (originally 2026-06-28 for /session only, generalised here 2026-07-29):
#   - < N consecutive failures for this purpose  -> raise 503, caller retries.
#   - >= N consecutive failures                  -> "library mode" for T seconds:
#     ai_complete() fails fast (no network call) until the window elapses.
#   - A successful call resets the counter immediately.
# In-memory, per-process, per-purpose. Resets on restart -- intentional,
# a fresh process should always retry the upstream once.
class CircuitBreaker:
    def __init__(self):
        self.consecutive_failures: int = 0
        self.library_mode_until: float = 0.0
        self.last_failure_reason: str = ""
        self.failure_threshold: int = 3
        self.library_mode_ttl: int = 600

    def configure(self, failure_threshold: int, library_mode_ttl: int) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.library_mode_ttl = max(1, library_mode_ttl)

    def is_library_mode(self) -> bool:
        if self.library_mode_until == 0.0:
            return False
        if time.monotonic() >= self.library_mode_until:
            self.library_mode_until = 0.0
            self.consecutive_failures = 0
            return False
        return True

    def seconds_remaining(self) -> int:
        return max(0, int(self.library_mode_until - time.monotonic())) if self.library_mode_until else 0

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.library_mode_until = 0.0
        self.last_failure_reason = ""

    def record_failure(self, reason: str) -> None:
        self.consecutive_failures += 1
        self.last_failure_reason = reason[:200]
        if self.consecutive_failures >= self.failure_threshold:
            self.library_mode_until = time.monotonic() + self.library_mode_ttl

    def status(self) -> dict:
        return {
            "consecutive_failures":            self.consecutive_failures,
            "library_mode":                    self.is_library_mode(),
            "library_mode_seconds_remaining":  self.seconds_remaining(),
            "last_failure_reason":             self.last_failure_reason,
            "failure_threshold":               self.failure_threshold,
            "library_mode_ttl":                self.library_mode_ttl,
        }


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(purpose: str) -> CircuitBreaker:
    if purpose not in _breakers:
        _breakers[purpose] = CircuitBreaker()
    return _breakers[purpose]


def all_breaker_status() -> dict:
    """For a diagnostic endpoint -- breaker state across every purpose."""
    return {p: b.status() for p, b in _breakers.items()}


# ── Low-level provider calls ────────────────────────────────────
# Both take a provider-agnostic OpenAI-style messages list and return
# (raw_text, latency_ms). They raise plain RuntimeError on failure --
# ai_complete() is what turns that into an HTTPException, once it knows
# whether a fallback provider is still worth trying.

async def _call_groq(model: str, messages: list[dict], max_tokens: int,
                      temperature: float, response_format: str) -> tuple[str, int]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured")

    payload: dict[str, Any] = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }
    if response_format == "json_object":
        # Groq's strict JSON mode -- only valid when the model is asked for
        # a single JSON *object*. Never set this for json_array responses;
        # Groq rejects/misbehaves on array-shaped output in this mode.
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=payload)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError("Cannot reach Groq API")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise RuntimeError("Invalid GROQ_API_KEY")
        if e.response.status_code == 429:
            raise RuntimeError("Groq rate limit reached")
        if e.response.status_code == 400 and "decommission" in e.response.text.lower():
            raise RuntimeError(
                f"Groq model '{model}' has been decommissioned -- "
                f"update it in Admin > Settings > AI generation"
            )
        # Any other status (a 400 that ISN'T the decommission case -- e.g. a
        # JSON-mode schema-validation failure, a bad param, a plan/model
        # mismatch -- previously vanished into a bare status code with no
        # way to tell those apart after the fact. Log the real body.
        logger.error(
            "Groq API error for model '%s': %s -- %s",
            model, e.response.status_code, e.response.text[:1000],
        )
        raise RuntimeError(f"Groq API error: {e.response.status_code}")
    latency_ms = int((time.monotonic() - t0) * 1000)

    content = resp.json()["choices"][0]["message"]["content"].strip()
    return content, latency_ms


async def _call_ollama(model: str, messages: list[dict], max_tokens: int,
                        temperature: float, response_format: str) -> tuple[str, int]:
    payload: dict[str, Any] = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": temperature, "num_predict": max_tokens},
    }
    if response_format in ("json_object", "json_array"):
        # Ollama's format:"json" just enforces valid JSON generally (object
        # or array both qualify) -- unlike Groq it doesn't need a separate
        # array-safe mode.
        payload["format"] = "json"

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError("Local Ollama not available")
    except httpx.TimeoutException:
        raise RuntimeError("Local Ollama timed out")
    except httpx.HTTPStatusError as e:
        logger.error(
            "Ollama API error for model '%s': %s -- %s",
            model, e.response.status_code, e.response.text[:1000],
        )
        raise RuntimeError(f"Ollama API error: {e.response.status_code}")
    latency_ms = int((time.monotonic() - t0) * 1000)

    content = resp.json().get("message", {}).get("content", "").strip()
    return content, latency_ms


async def _call_gemini(model: str, messages: list[dict], max_tokens: int,
                        temperature: float, response_format: str) -> tuple[str, int]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured")

    payload: dict[str, Any] = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        # 2026-08-07 (live outage fix): Gemini 2.5/3.x models ship with
        # "thinking" (internal reasoning) enabled by default, and -- unlike
        # OpenAI's models -- Google counts those invisible reasoning tokens
        # against the SAME max_tokens budget as the visible response. With
        # no reasoning_effort set, the model was burning most/all of
        # max_tokens=1200 on reasoning before writing any real output,
        # producing a truncated, invalid-JSON response that looked like a
        # parse failure but was actually a budget-exhaustion failure --
        # confirmed live: "AI returned invalid JSON: {\"title\": ...,
        # \"warmup\": \"Char, consider how" (cut off mid-sentence,
        # finish_reason=length upstream). "none" frees the entire budget
        # for visible output on Flash/Flash-lite tiers (what this codebase
        # uses). NOTE: if a Pro-tier Gemini model is ever configured here,
        # "none" is reportedly rejected ("Thinking can't be disabled") --
        # "low" is the documented fallback for Pro if that ever applies.
        "reasoning_effort": "none",
    }
    if response_format == "json_object":
        # Google's compatibility layer advertises support for this, mirroring
        # OpenAI/Groq's strict-JSON mode. Exercised against a live key for
        # the first time 2026-08-04 (e2e_org_polis.sh Part E) -- the call
        # failed, but with a 404 "model no longer available" from Google
        # (ai_model_gemini_large was still the P41-era default, 'gemini-
        # 2.5-flash', which Google appears to be retiring ahead of its own
        # documented Oct 2026 shutdown date -- see the new migration this
        # session), not a response_format/json-mode problem. Whether
        # json_object mode itself is honoured by Gemini's compatibility
        # layer is still unconfirmed either way.
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"}
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GEMINI_URL, headers=headers, json=payload)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError("Cannot reach Gemini API")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise RuntimeError("Invalid GEMINI_API_KEY")
        if e.response.status_code == 429:
            raise RuntimeError("Gemini rate limit reached")
        if e.response.status_code == 400 and "not found" in e.response.text.lower():
            raise RuntimeError(
                f"Gemini model '{model}' not found -- "
                f"update it in Admin > Settings > AI generation"
            )
        # 2026-08-04: Google has been observed returning a plain 404 (not
        # Groq's 400-with-"not found"-text shape) for a retired/renamed
        # model -- e.g. "This model models/gemini-2.5-flash is no longer
        # available", surfaced ahead of its own documented shutdown date.
        # Handled the same way as the 400 case above: a clear, actionable
        # message instead of a bare status code.
        if e.response.status_code == 404:
            raise RuntimeError(
                f"Gemini model '{model}' not found (404) -- likely retired/"
                f"renamed ahead of its documented shutdown date; "
                f"update it in Admin > Settings > AI generation"
            )
        logger.error(
            "Gemini API error for model '%s': %s -- %s",
            model, e.response.status_code, e.response.text[:1000],
        )
        raise RuntimeError(f"Gemini API error: {e.response.status_code}")
    latency_ms = int((time.monotonic() - t0) * 1000)

    content = resp.json()["choices"][0]["message"]["content"].strip()
    return content, latency_ms


_CALLERS = {"groq": _call_groq, "ollama": _call_ollama, "gemini": _call_gemini}


# ── Response parsing ─────────────────────────────────────────────

def _parse(raw: str, response_format: str) -> Any:
    if response_format == "text":
        return raw.strip()

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    open_ch, close_ch = ("[", "]") if response_format == "json_array" else ("{", "}")
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch) + 1
        if start != -1 and end > start:
            parsed = json.loads(cleaned[start:end])
        else:
            raise RuntimeError(f"AI returned invalid JSON: {cleaned[:200]}")

    expected_type = list if response_format == "json_array" else dict
    if not isinstance(parsed, expected_type):
        raise RuntimeError(f"AI returned JSON of unexpected shape (expected {expected_type.__name__})")
    return parsed


# ── The one entry point every route uses ────────────────────────

@dataclass
class AIResponse:
    content:    Any    # dict (json_object) | list (json_array) | str (text)
    model:      str    # which model answered, e.g. "openai/gpt-oss-120b" or "ollama:llama3.1:8b"
    latency_ms: int


async def ai_complete(
    purpose: str,
    *,
    db: AsyncSession,
    system_msg: str = "",
    prompt: Optional[str] = None,
    messages: Optional[list[dict]] = None,
    tier: str = "large",
    response_format: str = "json_object",   # "json_object" | "json_array" | "text"
    max_tokens: int = 1200,
    temperature: float = 0.8,
) -> AIResponse:
    """Call whichever AI provider the admin has configured, with automatic
    fallback to the other free provider and a per-purpose circuit breaker.

    purpose: a short stable label ("session", "companion", "assess_companion",
        "guiding_star", "learner_profile", "needs_parsing", "bioregion_draft",
        "bioregion_synthesis", "scavenger", ...) -- each gets its own breaker
        so one feature misbehaving doesn't fail-fast unrelated features.
    tier: "large" (default) for content generation/quality-sensitive calls,
        "small" for lightweight/classification calls -- maps to
        ai_model_{provider}_{tier} in platform_settings.
    """
    settings = await get_ai_settings(db)
    provider = settings.get("ai_provider", "groq")
    if provider not in (*ALL_PROVIDERS, "library"):
        provider = "groq"

    breaker = get_breaker(purpose)
    breaker.configure(
        int_setting(settings, "ai_library_failure_threshold"),
        int_setting(settings, "ai_library_mode_ttl"),
    )
    breaker_enabled = bool_setting(settings, "ai_circuit_breaker_enabled")

    if provider == "library":
        raise HTTPException(
            503,
            "AI generation is turned off (admin set the platform AI provider "
            "to Library-only in Settings)."
        )

    if breaker_enabled and breaker.is_library_mode():
        raise HTTPException(
            503,
            f"AI temporarily degraded for '{purpose}' after repeated failures -- "
            f"retrying automatically in {breaker.seconds_remaining()}s."
        )

    msgs: list[dict] = []
    if system_msg:
        msgs.append({"role": "system", "content": system_msg})
    if messages:
        msgs.extend(messages)
    elif prompt is not None:
        msgs.append({"role": "user", "content": prompt})
    if not msgs:
        raise ValueError("ai_complete requires prompt or messages")

    order = [provider] + [p for p in ALL_PROVIDERS if p != provider]
    errors: list[str] = []

    for prov in order:
        model = settings.get(f"ai_model_{prov}_{tier}", _AI_DEFAULTS[f"ai_model_{prov}_{tier}"])
        try:
            raw, latency_ms = await _CALLERS[prov](model, msgs, max_tokens, temperature, response_format)
            content = _parse(raw, response_format)
            # 2026.119: a 200 response with genuinely empty content (a real,
            # observed failure mode -- provider returned successfully but
            # said nothing) was previously treated as a SUCCESS: no failover
            # to the next provider, no breaker penalty, and the empty string
            # sailed on to become a blank bubble for the learner. Text-format
            # calls are the ones this actually reaches the user raw (JSON
            # calls fail their own shape check above and are already caught).
            if response_format == "text" and not content:
                raise RuntimeError("provider returned an empty completion")
        except Exception as e:
            errors.append(f"{prov}: {str(e)[:120]}")
            continue

        breaker.record_success()
        return AIResponse(
            content=content,
            model=(model if prov == "groq" else f"{prov}:{model}"),
            latency_ms=latency_ms,
        )

    combined = " | ".join(errors)
    breaker.record_failure(combined)
    raise HTTPException(503, f"All AI providers failed for '{purpose}'. {combined}")


# ── Status helpers (back the admin AI status page) ──────────────

async def groq_status(db: AsyncSession) -> dict:
    settings = await get_ai_settings(db)
    if not GROQ_API_KEY:
        return {
            "available": False,
            "message":   "Sign up free at console.groq.com — no credit card needed",
            "setup":     "Add GROQ_API_KEY=gsk_... to your .env file",
            "active":    settings["ai_provider"] == "groq",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            )
            r.raise_for_status()
            models = [m["id"] for m in r.json().get("data", [])]
        return {
            "available":   True,
            "model":       settings["ai_model_groq_large"],
            "model_small": settings["ai_model_groq_small"],
            "models":      models,
            "active":      settings["ai_provider"] == "groq",
        }
    except Exception as e:
        return {"available": False, "error": str(e)[:200], "active": settings["ai_provider"] == "groq"}


async def ollama_status(db: AsyncSession) -> dict:
    settings = await get_ai_settings(db)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
        return {
            "available":    True,
            "url":          OLLAMA_URL,
            "model":        settings["ai_model_ollama_large"],
            "model_small":  settings["ai_model_ollama_small"],
            "all_models":   models,
            "active":       settings["ai_provider"] == "ollama",
        }
    except Exception as e:
        return {
            "available": False,
            "url":       OLLAMA_URL,
            "error":     str(e)[:200],
            "active":    settings["ai_provider"] == "ollama",
        }


async def gemini_status(db: AsyncSession) -> dict:
    settings = await get_ai_settings(db)
    if not GEMINI_API_KEY:
        return {
            "available": False,
            "message":   "Sign up free at aistudio.google.com — no credit card needed",
            "setup":     "Add GEMINI_API_KEY=... to your .env file",
            "active":    settings["ai_provider"] == "gemini",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models",
                headers={"Authorization": f"Bearer {GEMINI_API_KEY}"},
            )
            r.raise_for_status()
            models = [m["id"] for m in r.json().get("data", [])]
        return {
            "available":   True,
            "model":       settings["ai_model_gemini_large"],
            "model_small": settings["ai_model_gemini_small"],
            "models":      models,
            "active":      settings["ai_provider"] == "gemini",
        }
    except Exception as e:
        return {"available": False, "error": str(e)[:200], "active": settings["ai_provider"] == "gemini"}
