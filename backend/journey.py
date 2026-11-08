# ============================================================
# LMBoK backend, journey.py  (Phase 2 patch B, 2026-11-07)
# Writes the journey log (journey_entries) when a session is completed.
# One 'session' entry per completed session, plus 'milestone' entries
# only for sessions that counted toward growth.
# Called from routes/sessions.py::complete_session. Everything runs in a
# SAVEPOINT and swallows its own errors (logged), so a journey failure can
# never block or roll back completing a session.
# ============================================================

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Arts, JourneyEntry, Skill
from utils import compute_avatar_stage

log = logging.getLogger(__name__)

TITLE_MAX   = 200   # journey_entries.title  VARCHAR(200)
EXCERPT_MAX = 160   # chapter-line excerpt; the column is VARCHAR(400)
FAMILIES    = 3     # Being, Becoming, Connecting


def _collapse(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def make_excerpt(reflect: str | None, challenge: str | None) -> str | None:
    """First 160 characters of the reflection (else the challenge response),
    whitespace collapsed, with an ellipsis when cut. None when both are empty."""
    text = _collapse(reflect) or _collapse(challenge)
    if not text:
        return None
    return text if len(text) <= EXCERPT_MAX else text[:EXCERPT_MAX].rstrip() + "\u2026"


async def record_session_journey(
    db: AsyncSession,
    *,
    learner_id: int,
    session,
    counted: bool,
    level_before: int,
    level_after: int,
    prev_art_scores: dict | None,
    new_art_scores: dict | None,
) -> bool:
    """Add this session's journey rows to `db` (the caller commits).
    `prev_art_scores` must be read BEFORE the new radar snapshot is added.
    Returns True when the rows were added, False when the savepoint failed."""
    try:
        async with db.begin_nested():
            art = (await db.execute(
                select(Arts).where(Arts.id == session.art_id)
            )).scalar_one_or_none()
            title = _collapse(session.title) or (art.name if art else "Session")
            db.add(JourneyEntry(
                learner_id=learner_id, kind="session",
                session_id=session.id, art_id=session.art_id,
                skill_id=session.primary_skill_id,
                title=title[:TITLE_MAX],
                excerpt=make_excerpt(session.reflect_response, session.challenge_response),
                payload={"counted": bool(counted)},
            ))
            if not counted:
                return True

            # first_in_art: no earlier first_in_art row for this learner and Art
            earlier_arts = set((await db.execute(
                select(JourneyEntry.art_id).where(
                    JourneyEntry.learner_id == learner_id,
                    JourneyEntry.kind == "milestone",
                    JourneyEntry.milestone == "first_in_art",
                    JourneyEntry.art_id.is_not(None),
                )
            )).scalars().all())
            if session.art_id not in earlier_arts:
                db.add(JourneyEntry(
                    learner_id=learner_id, kind="milestone", milestone="first_in_art",
                    session_id=session.id, art_id=session.art_id,
                    skill_id=session.primary_skill_id,
                    title=(art.name if art else "")[:TITLE_MAX] or "First session in an Art",
                ))
                # all_families: this first_in_art brings the distinct families to three
                have_all = (await db.execute(
                    select(JourneyEntry.id).where(
                        JourneyEntry.learner_id == learner_id,
                        JourneyEntry.milestone == "all_families",
                    ).limit(1)
                )).first()
                if not have_all:
                    groups = set((await db.execute(
                        select(Arts.group_id).where(Arts.id.in_(earlier_arts | {session.art_id}))
                    )).scalars().all())
                    if len(groups) >= FAMILIES:
                        db.add(JourneyEntry(
                            learner_id=learner_id, kind="milestone", milestone="all_families",
                            session_id=session.id, art_id=session.art_id,
                            title="All three families",
                        ))

            # level_up: the primary skill's level increased
            if level_after > level_before:
                skill = None
                if session.primary_skill_id:
                    skill = (await db.execute(
                        select(Skill).where(Skill.id == session.primary_skill_id)
                    )).scalar_one_or_none()
                db.add(JourneyEntry(
                    learner_id=learner_id, kind="milestone", milestone="level_up",
                    session_id=session.id, art_id=session.art_id,
                    skill_id=session.primary_skill_id,
                    title=(skill.name if skill else "Skill level")[:TITLE_MAX],
                    payload={"skill": skill.name if skill else None,
                             "from": level_before, "to": level_after},
                ))

            # stage_change: the avatar stage moved up since the previous snapshot
            old = compute_avatar_stage(prev_art_scores or {})
            new = compute_avatar_stage(new_art_scores or {})
            if new["level"] > old["level"]:
                db.add(JourneyEntry(
                    learner_id=learner_id, kind="milestone", milestone="stage_change",
                    session_id=session.id,
                    title=new["label"][:TITLE_MAX],
                    payload={"from": old["key"], "to": new["key"]},
                ))
        return True
    except Exception:
        log.exception("journey entry not recorded (learner %s, session %s)",
                      learner_id, getattr(session, "id", None))
        return False
