# ============================================================
# FreqLearn — utils.py
# Shared utilities imported by multiple route modules.
# ============================================================

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from models import Learner, LearnerStreak, DevPhase, SessionConfig


# ── Session config ───────────────────────────────────────────
# 2026-08-25: shared session-generation values (currently just the
# phase-guidance disclaimer) live in one DB table instead of being
# duplicated across generate.py / seed_sessions.py. Not yet exposed in
# admin -- see session_config table's own migration comment for why.

async def get_session_config(key: str, db: AsyncSession, default: str = "") -> str:
    """Fetch a session_config value by key. Returns `default` if the key
    doesn't exist, rather than raising -- a missing config value should
    degrade gracefully, not break session generation."""
    result = await db.execute(select(SessionConfig).where(SessionConfig.config_key == key))
    row = result.scalar_one_or_none()
    return row.config_value if row else default


# ── Developmental phase ──────────────────────────────────────
# 2026-08-24/25: elemental phases redesign. Phase is a DERIVED value —
# computed fresh from birth_year/is_expecting_parent rather than trusted
# from a possibly-stale stored phase_id, so a learner drifts forward to
# their next phase automatically as they age, with no cron job needed.
# Callers that want the result persisted (e.g. /me, /me/preferences)
# write it back to learner.phase_id themselves after calling this.
#
# is_expecting_parent overrides birth_year entirely and always resolves
# to "light". No birth_year and not expecting means unresolved (None) —
# deliberate: the strict phase-matching policy (2026-08-24) means an
# unresolved phase must never be used to serve a session.

async def compute_current_phase(learner: Learner, db: AsyncSession) -> DevPhase | None:
    """Resolve a learner's current developmental phase. See module note above."""
    if learner.is_expecting_parent:
        light_q = await db.execute(select(DevPhase).where(DevPhase.slug == "light"))
        return light_q.scalar_one_or_none()

    if not learner.birth_year:
        return None

    age = datetime.now(timezone.utc).year - learner.birth_year
    phases_q = await db.execute(
        select(DevPhase).where(DevPhase.age_min.isnot(None)).order_by(DevPhase.sort_order)
    )
    for phase in phases_q.scalars().all():
        if age >= phase.age_min and (phase.age_max is None or age <= phase.age_max):
            return phase
    return None


# ── Avatar stage ─────────────────────────────────────────────
# Mirrors computeAvatarStage() in app.js exactly.
# Any change here must be reflected there too (and vice versa).

AVATAR_STAGES = [
    # (min_xp, min_arts, min_domains, key, icon, label)
    (500, 12, 3, 'ecosystem', '🌍', 'Ecosystem'),
    (200,  9, 3, 'forest',    '🌲', 'Forest'),
    (100,  6, 2, 'grove',     '🌳', 'Grove'),
    ( 50,  4, 0, 'sapling',   '🌿', 'Sapling'),
    ( 18,  2, 0, 'sprout',    '🌱', 'Sprout'),
    (  0,  0, 0, 'seed',      '🫘', 'Seed'),
]

BEING_ARTS      = {'move', 'feel', 'eat', 'listen', 'notice', 'receive', 'live'}
BECOMING_ARTS   = {'understand', 'grow', 'build', 'express'}
CONNECTING_ARTS = {'give', 'collaborate', 'consume', 'respect'}


def compute_avatar_stage(xp: int, arts_touched: list[str]) -> dict:
    """
    Compute Avatar stage from XP and list of art slugs with score > 0.05.
    Returns a dict with key, icon, label, level (1–6), xp, arts_count,
    domains, and can_access_polis.
    """
    art_set = set(arts_touched)
    domains = sum([
        1 if art_set & BEING_ARTS      else 0,
        1 if art_set & BECOMING_ARTS   else 0,
        1 if art_set & CONNECTING_ARTS else 0,
    ])
    arts_count = len(art_set)

    for level_idx, (min_xp, min_arts, min_domains, key, icon, label) in enumerate(AVATAR_STAGES):
        if xp >= min_xp and arts_count >= min_arts and domains >= min_domains:
            level = 6 - level_idx  # Ecosystem=6, Seed=1
            return {
                'key':              key,
                'icon':             icon,
                'label':            label,
                'level':            level,
                'xp':               xp,
                'arts_count':       arts_count,
                'domains':          domains,
                'can_access_polis': key in ('grove', 'forest', 'ecosystem'),
            }

    # Fallback — Seed
    return {
        'key': 'seed', 'icon': '🫘', 'label': 'Seed', 'level': 1,
        'xp': xp, 'arts_count': arts_count, 'domains': domains,
        'can_access_polis': False,
    }


async def get_learner_stage(learner: Learner, db: AsyncSession) -> dict:
    """
    Fetch XP + arts progress from DB and return computed avatar stage.
    Shared by polis.py and matching.py.
    """
    streak_q = await db.execute(
        select(LearnerStreak).where(LearnerStreak.learner_id == learner.id)
    )
    streak = streak_q.scalar_one_or_none()
    xp = streak.total_xp if streak else 0

    arts_q = await db.execute(text("""
        SELECT a.slug
        FROM learner_art_progress lap
        JOIN arts a ON a.id = lap.art_id
        WHERE lap.learner_id = :lid AND lap.score > 0.05
    """), {"lid": learner.id})
    arts_touched = [row[0] for row in arts_q.fetchall()]

    return compute_avatar_stage(xp, arts_touched)
