# ============================================================
# FreqLearn — utils.py
# Shared utilities imported by multiple route modules.
# ============================================================

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from models import Learner, DevPhase, SessionConfig


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
# 2026-09-05: replaced the old (xp, arts_touched, domain-breadth) gate
# with a pure Art-level bottleneck gate, per Charbel's direction — the
# 15 Arts are the operative pedagogical unit (PHILOSOPHY.md); Being/
# Becoming/Connecting are an organizing scheme over them, not a
# separate breadth requirement. XP and "touched" counts are gone;
# a stage now requires EVERY one of the 15 Arts to be at or above that
# stage's score threshold. The learner's weakest art is the bottleneck.
# Mirrors computeAvatarStage() in app.js exactly.
# Any change here must be reflected there too (and vice versa).

AVATAR_STAGES = [
    # (min_art_score, key, icon, label) — threshold every one of the
    # 15 Arts must reach. Front-loaded: cheap early, expensive at mastery.
    (1.00, 'ecosystem', '🌍', 'Ecosystem'),
    (0.65, 'forest',    '🌲', 'Forest'),
    (0.40, 'grove',     '🌳', 'Grove'),
    (0.20, 'sapling',   '🌿', 'Sapling'),
    (0.10, 'sprout',    '🌱', 'Sprout'),
    (0.00, 'seed',      '🫘', 'Seed'),
]

BEING_ARTS      = {'move', 'eat', 'feel', 'notice', 'express'}
BECOMING_ARTS   = {'live', 'listen', 'give', 'receive', 'collaborate'}
CONNECTING_ARTS = {'understand', 'respect', 'build', 'grow', 'consume'}
ALL_ARTS        = BEING_ARTS | BECOMING_ARTS | CONNECTING_ARTS  # 15 arts


def compute_avatar_stage(art_scores: dict[str, float]) -> dict:
    """
    Compute Avatar stage from per-art scores (0.0-1.0, keyed by art slug).
    A stage requires EVERY one of the 15 Arts to be at or above that
    stage's threshold -- an art missing from art_scores counts as 0.0.
    Returns a dict with key, icon, label, level (1-6), min_art_score,
    next_stage (None once at Ecosystem), and can_access_polis.
    """
    min_score = min((art_scores.get(art, 0.0) for art in ALL_ARTS), default=0.0)

    for level_idx, (min_level, key, icon, label) in enumerate(AVATAR_STAGES):
        if min_score >= min_level:
            level = 6 - level_idx  # Ecosystem=6, Seed=1
            next_row = AVATAR_STAGES[level_idx - 1] if level_idx > 0 else None
            return {
                'key':              key,
                'icon':             icon,
                'label':            label,
                'level':            level,
                'min_art_score':    round(min_score, 3),
                'next_stage':       {
                    'label':         next_row[3],
                    'icon':          next_row[2],
                    'min_art_score': next_row[0],
                } if next_row else None,
                'can_access_polis': key in ('grove', 'forest', 'ecosystem'),
            }

    # Unreachable (min_level=0.00 always matches) -- kept for safety.
    return {
        'key': 'seed', 'icon': '🫘', 'label': 'Seed', 'level': 1,
        'min_art_score': round(min_score, 3), 'next_stage': None,
        'can_access_polis': False,
    }


async def get_learner_stage(learner: Learner, db: AsyncSession) -> dict:
    """
    Fetch per-art scores from DB and return computed avatar stage.
    Shared by polis.py and matching.py.
    """
    arts_q = await db.execute(text("""
        SELECT a.slug, lap.score
        FROM learner_art_progress lap
        JOIN arts a ON a.id = lap.art_id
        WHERE lap.learner_id = :lid
    """), {"lid": learner.id})
    art_scores = {row[0]: float(row[1]) for row in arts_q.fetchall()}

    return compute_avatar_stage(art_scores)
