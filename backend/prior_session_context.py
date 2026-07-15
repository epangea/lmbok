# ============================================================
# FreqLearn — prior_session_context.py
# Builds a "LEARNER CONTINUITY" block for the AI prompt so each
# session generation explicitly builds on the learner's prior work
# for the same (art, dev_phase), rather than re-inventing similar
# territory on every call.
#
# The block is a single string, appended to the existing prompt
# without altering any other section. Returns "" if no prior
# sessions exist (so the prompt is identical to the pre-change form).
# ============================================================

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Session, Session as SessionModel  # alias to keep imports clean


# Mapping of assess_score value → short label for the prompt
SCORE_LABELS = {
    40:  "Still learning",
    75:  "Getting it",
    100: "I knew this",
}


def _score_label(score: Optional[int]) -> str:
    if score is None:
        return "not rated"
    if score in SCORE_LABELS:
        return SCORE_LABELS[score]
    if score < 50:
        return "Still learning"
    if score < 90:
        return "Getting it"
    return "I knew this"


async def get_prior_session_context(
    db: AsyncSession,
    learner_id: int,
    art_id: int,
    dev_phase_id: Optional[int] = None,
    n: int = 3,
) -> str:
    """Return a LEARNER CONTINUITY string describing the learner's last
    `n` sessions for this art. Returns "" if none exist.
    """
    q = (
        select(Session)
        .where(
            Session.learner_id == learner_id,
            Session.art_id     == art_id,
            Session.warmup_prompt != None,
        )
    )
    if dev_phase_id is not None:
        q = q.where((Session.dev_phase_id == dev_phase_id) | (Session.dev_phase_id == None))
    q = q.order_by(Session.created_at.desc()).limit(n)

    result = await db.execute(q)
    sessions = result.scalars().all()

    if not sessions:
        return ""

    lines = [
        "",
        "LEARNER CONTINUITY — This learner has explored this art before. "
        "Their last sessions are below. Build on these: avoid repeating themes "
        "already explored; if a misconception surfaced in an assess, address it "
        "from a new angle; if self-rated understanding is climbing, deepen the "
        "challenge; if it's flat or dropping, try a different entry point.",
        "",
    ]
    for i, s in enumerate(sessions, 1):
        assess_q   = (s.assess_question or {}).get("question", "(no assess question)")
        assess_sel = s.assess_selected_index
        options    = (s.assess_question or {}).get("options", [])
        correct_ix = (s.assess_question or {}).get("correct_index")

        if isinstance(assess_sel, int) and isinstance(correct_ix, int) and options:
            sel_letter = chr(ord("A") + assess_sel) if assess_sel < 26 else str(assess_sel)
            cor_letter = chr(ord("A") + correct_ix)   if correct_ix < 26 else str(correct_ix)
            sel_text   = options[assess_sel] if assess_sel < len(options) else "(unknown)"
            cor_text   = options[correct_ix] if correct_ix < len(options) else "(unknown)"
            assess_summary = (
                f'"{assess_q}" → Learner chose {sel_letter} "{sel_text}". '
                f'Correct was {cor_letter} "{cor_text}".'
            )
        else:
            assess_summary = f'"{assess_q}" (selection not recorded)'

        date_str = s.created_at.strftime("%Y-%m-%d") if s.created_at else "(date unknown)"
        lines.append(
            f"  - Session {i} ({date_str}): \"{s.title or '(untitled)'}\"\n"
            f"      Assess: {assess_summary}\n"
            f"      Self-rated understanding: {s.assess_score if s.assess_score is not None else 'n/a'} "
            f"({_score_label(s.assess_score)})."
        )

    lines.append("")  # trailing blank
    return "\n".join(lines)
