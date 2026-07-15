# ============================================================
# FreqLearn — circuit_breaker.py
# In-memory circuit breaker for AI provider failures.
#
# Behaviour (per PART 20 — 2026-06-28):
#   - Each (provider, learner_id) pair has a consecutive-failure counter
#   - On AI success: counter resets to 0
#   - On AI failure: counter increments
#   - When counter >= 3: that learner is in "library mode" for 10 minutes,
#     meaning the next request skips AI and goes straight to LibraryAIClient
#   - After 10 minutes, the library-mode flag expires and we try AI again
#   - This is purely a performance optimisation: it avoids 30-second
#     timeouts on every request when the AI is having a bad minute.
#     The library fallback path runs regardless after 3 failures.
#
# State is in-memory only. It resets on server restart. If we ever
# scale to multiple workers, move this dict into Redis or a DB table.
# ============================================================

from __future__ import annotations

import time
from threading import RLock
from typing import Dict, Tuple

# failure_count[(provider, learner_id)] = consecutive failure count
_failure_count: Dict[Tuple[str, int], int] = {}

# library_mode_until[(provider, learner_id)] = epoch seconds when library mode expires
_library_mode_until: Dict[Tuple[str, int], float] = {}

_lock = RLock()

FAILURE_THRESHOLD = 3       # after this many consecutive failures, flip to library mode
LIBRARY_MODE_TTL  = 600     # 10 minutes in seconds


def _key(provider: str, learner_id: int) -> Tuple[str, int]:
    return (provider, learner_id)


def record_success(provider: str, learner_id: int) -> None:
    """AI call succeeded — clear failure state for this learner."""
    with _lock:
        k = _key(provider, learner_id)
        _failure_count.pop(k, None)
        _library_mode_until.pop(k, None)


def record_failure(provider: str, learner_id: int) -> int:
    """AI call failed. Increments counter. Returns new failure count.
    If count crosses the threshold, sets the library-mode window.
    """
    with _lock:
        k = _key(provider, learner_id)
        new_count = _failure_count.get(k, 0) + 1
        _failure_count[k] = new_count
        if new_count >= FAILURE_THRESHOLD:
            _library_mode_until[k] = time.time() + LIBRARY_MODE_TTL
        return new_count


def should_use_library(provider: str, learner_id: int) -> bool:
    """True if we're in the 10-minute library-only window for this learner."""
    with _lock:
        k = _key(provider, learner_id)
        expiry = _library_mode_until.get(k)
        if expiry is None:
            return False
        if time.time() >= expiry:
            # Window expired — clear it
            _library_mode_until.pop(k, None)
            _failure_count.pop(k, None)
            return False
        return True


def current_failure_count(provider: str, learner_id: int) -> int:
    with _lock:
        return _failure_count.get(_key(provider, learner_id), 0)


def snapshot() -> dict:
    """For the admin status endpoint — current state across all learners."""
    with _lock:
        return {
            "failure_count":      {f"{p}:{lid}": c for (p, lid), c in _failure_count.items()},
            "library_mode_until": {f"{p}:{lid}": t for (p, lid), t in _library_mode_until.items()},
            "threshold":          FAILURE_THRESHOLD,
            "library_mode_ttl_s": LIBRARY_MODE_TTL,
        }
