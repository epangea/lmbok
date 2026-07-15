# ============================================================
# FreqLearn — utils.py
# Shared utilities imported by multiple route modules.
# ============================================================

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from models import Learner, LearnerStreak


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
