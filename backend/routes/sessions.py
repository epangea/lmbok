# ============================================================
# FreqLearn Backend — routes/sessions.py  (v2)
# Session lifecycle — matches schema v2
# ============================================================

from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from db import get_db
from models import (
    Session, LearnerSkillProgress, LearnerStreak,
    ActivityLog, RadarSnapshot, Learner,
    Arts, LearnerArtProgress, Skill,
)
from routes.auth import get_current_learner
from engine import RecommendationEngine

router = APIRouter()
eng = RecommendationEngine()


class StartSessionRequest(BaseModel):
    skill_id:         int
    art_id:           int
    recommended_by:   str = "engine"
    engine_reasoning: dict | None = None
    title:            str | None = None
    language:         str | None = "en"  # UI language at generation time

class CompleteSessionRequest(BaseModel):
    duration_seconds:   int
    xp_earned:          int
    challenge_response: str | None = None
    reflect_response:   str | None = None
    assess_score:       int | None = None
    assess_selected_index: int | None = None   # 0-based index of the option the learner picked; NULL if not answered
    phase_reached:      int = 5
    # Skill-session attribution fields (sent by frontend when a Learning Domain skill was clicked)
    skill_context:      str | None = None        # display name, e.g. "Data Analysis"
    contributing_arts:  list[str] | None = None  # art slugs, e.g. ["understand","build","consume"]


# ── Skill → Art weighted mapping ───────────────────────────────────────────
# Mirrors SKILL_ART_WEIGHTS in the frontend. Used to distribute art-level
# credit when a Learning Domain skill session completes.
# art slugs must match the `arts.slug` column exactly.
SKILL_ART_WEIGHTS: dict[str, dict[str, float]] = {
    # COGNITIVE & INTELLECTUAL
    "Critical Thinking":    {"understand": 0.50, "notice": 0.30, "live": 0.20},
    "Problem Solving":      {"understand": 0.40, "build": 0.35,  "notice": 0.25},
    "Systems Thinking":     {"understand": 0.45, "live": 0.30,   "consume": 0.25},
    "Memory & Retention":   {"understand": 0.40, "notice": 0.35, "consume": 0.25},
    "Decision Making":      {"understand": 0.40, "live": 0.35,   "notice": 0.25},
    "Project Management":   {"understand": 0.35, "live": 0.35,   "collaborate": 0.20, "notice": 0.10},
    # CREATIVE & ARTISTIC
    "Visual Art":                      {"express": 0.70, "notice": 0.20, "build": 0.10},
    "Music & Rhythm":                  {"express": 0.60, "move": 0.25,   "feel": 0.15},
    "Creative Writing":                {"express": 0.55, "listen": 0.25, "notice": 0.20},
    "Drama & Theatre":                 {"express": 0.60, "collaborate": 0.25, "notice": 0.15},
    "Improvisation & Public Speaking": {"express": 0.50, "listen": 0.30, "collaborate": 0.20},
    "Craftsmanship & Making":          {"build": 0.60,   "express": 0.25, "notice": 0.15},
    # PHYSICAL & MOTOR
    "Gross Motor":         {"move": 0.70, "eat": 0.20,   "grow": 0.10},
    "Fine Motor":          {"move": 0.55, "build": 0.30, "notice": 0.15},
    "Physical Fitness":    {"move": 0.60, "eat": 0.25,   "grow": 0.15},
    "Dance & Movement":    {"move": 0.65, "express": 0.25, "feel": 0.10},
    "Body Awareness":      {"move": 0.50, "notice": 0.30, "feel": 0.20},
    "First Aid & Nursing": {"move": 0.45, "notice": 0.35, "give": 0.20},
    # SOCIAL & RELATIONAL
    "Collaboration":          {"collaborate": 0.55, "give": 0.25,    "listen": 0.20},
    "Conflict Resolution":    {"listen": 0.40,      "respect": 0.35, "collaborate": 0.25},
    "Empathetic Leadership":  {"collaborate": 0.35, "give": 0.30,    "listen": 0.25, "live": 0.10},
    "Negotiation":            {"listen": 0.40,      "collaborate": 0.35, "live": 0.25},
    "Cultural Competence":    {"respect": 0.50,     "listen": 0.30,  "understand": 0.20},
    "Parenting & Caregiving": {"give": 0.55,        "listen": 0.25,  "feel": 0.20},
    # LANGUAGE & COMMUNICATION
    "Active Reading":               {"understand": 0.50, "notice": 0.35, "consume": 0.15},
    "Active Listening":             {"listen": 0.60,     "notice": 0.25, "feel": 0.15},
    "Storytelling":                 {"express": 0.50,    "listen": 0.30, "feel": 0.20},
    "Debate & Argumentation":       {"listen": 0.40,     "understand": 0.35, "collaborate": 0.25},
    "Foreign Language Acquisition": {"listen": 0.45,     "understand": 0.30, "express": 0.25},
    "Rhetoric & Persuasion":        {"express": 0.45,    "understand": 0.35, "listen": 0.20},
    # EMOTIONAL & PSYCHOLOGICAL
    "Self-Awareness":          {"feel": 0.55, "notice": 0.30, "move": 0.15},
    "Emotional Regulation":    {"feel": 0.55, "move": 0.25,   "notice": 0.20},
    "Empathy and Compassion":  {"feel": 0.45, "listen": 0.35, "give": 0.20},
    "Self-Efficacy":           {"feel": 0.40, "live": 0.35,   "move": 0.25},
    "Contemplative Practice":  {"notice": 0.55, "feel": 0.35, "move": 0.10},
    "Gratitude & Appreciation":{"feel": 0.45, "notice": 0.35, "receive": 0.20},
    # META-LEARNING
    "Learning How to Learn":       {"notice": 0.40, "understand": 0.35, "live": 0.25},
    "Self-Regulation":             {"live": 0.40,   "move": 0.35,       "notice": 0.25},
    "Personal Values":             {"live": 0.45,   "feel": 0.30,       "notice": 0.25},
    "Curiosity and Exploration":   {"notice": 0.50, "understand": 0.30, "consume": 0.20},
    "Vision, Mission and Purpose": {"live": 0.55,   "understand": 0.25, "give": 0.20},
    "Mentorship & Teaching":       {"give": 0.40,   "understand": 0.35, "listen": 0.25},
    # TOOLS & SYSTEMS
    "Digital Literacy":           {"consume": 0.40, "understand": 0.40, "notice": 0.20},
    "Data Analysis & Statistics":  {"understand": 0.50, "notice": 0.30, "consume": 0.20},
    "Design Thinking":             {"understand": 0.35, "collaborate": 0.30, "express": 0.20, "build": 0.15},
    "Philosophy & Ethics":         {"understand": 0.35, "respect": 0.35, "live": 0.30},
    "Permaculture":                {"grow": 0.50,   "build": 0.30,      "respect": 0.20},
    "Cooking & Nutrition":         {"eat": 0.55,    "grow": 0.25,       "build": 0.20},
}


@router.get("/")
async def list_sessions(
    limit: int = 10,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Session)
        .where(Session.learner_id == learner.id)
        .order_by(desc(Session.created_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/start")
async def start_session(
    req: StartSessionRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    session = Session(
        learner_id=learner.id,
        art_id=req.art_id,
        primary_skill_id=req.skill_id,
        title=req.title,
        recommended_by=req.recommended_by,
        engine_reasoning=req.engine_reasoning,
        status="in_progress",
        language=req.language,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/{session_id}/complete")
async def complete_session(
    session_id: int,
    req: CompleteSessionRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.learner_id == learner.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    # Update session
    session.status             = "completed"
    session.duration_seconds   = req.duration_seconds
    session.xp_earned          = req.xp_earned
    session.phase_reached      = req.phase_reached
    session.challenge_response = req.challenge_response
    session.reflect_response   = req.reflect_response
    session.assess_score       = req.assess_score
    # 2026-07-07: persist which option the learner actually picked. The
    # LEARNER CONTINUITY block in generate.py uses this to show "learner
    # chose B 'X', correct was D 'Y'" so the AI can address a misconception
    # — especially useful when the wrong answer is close to the correct one.
    session.assess_selected_index = req.assess_selected_index
    session.completed_at       = datetime.now(timezone.utc)

    # Update skill progress
    prog_result = await db.execute(
        select(LearnerSkillProgress).where(
            LearnerSkillProgress.learner_id == learner.id,
            LearnerSkillProgress.skill_id   == session.primary_skill_id
        )
    )
    progress = prog_result.scalar_one_or_none()
    if not progress:
        progress = LearnerSkillProgress(
            learner_id=learner.id,
            skill_id=session.primary_skill_id
        )
        db.add(progress)

    # FIX: DB columns may be NULL for brand-new rows — guard with `or 0`
    progress.recall_count     = (progress.recall_count   or 0) + 1
    progress.evidence_count   = (progress.evidence_count or 0) + 1
    progress.current_level    = (progress.current_level  or 0)
    progress.last_practiced_at = datetime.now(timezone.utc)

    # Spaced repetition — next_review_at driven by self-rating (assess_score):
    #   Still learning (≤50) → review in 2 days
    #   Getting it    (51–85) → review in 5 days
    #   I knew this   (>85)  → review in 14 days
    score = req.assess_score or 0
    review_days = 2 if score <= 50 else (14 if score > 85 else 5)
    from datetime import timedelta
    progress.next_review_at = datetime.now(timezone.utc) + timedelta(days=review_days)

    # Level up: needs evidence_count >= 3 per level and assess_score >= 70
    if (progress.evidence_count >= (progress.current_level + 1) * 3
            and (req.assess_score or 0) >= 70
            and progress.current_level < 3):
        progress.current_level += 1
        progress.evidence_count = 0

    # Update streak
    # FIX: was silently doing nothing when no streak row existed for this learner.
    # Now creates a new streak row on first session completion.
    streak_result = await db.execute(
        select(LearnerStreak).where(LearnerStreak.learner_id == learner.id)
    )
    streak = streak_result.scalar_one_or_none()
    today = datetime.now(timezone.utc).date()

    if streak:
        if streak.last_activity_date == today:
            pass  # already logged today, just update totals below
        elif streak.last_activity_date and (today - streak.last_activity_date).days == 1:
            streak.current_streak += 1
            streak.longest_streak  = max(streak.longest_streak, streak.current_streak)
        else:
            streak.current_streak = 1
        streak.last_activity_date = today
        streak.total_sessions    += 1
        streak.total_xp          += req.xp_earned
        streak.total_minutes     += req.duration_seconds // 60
    else:
        # First session ever — create the streak row
        streak = LearnerStreak(
            learner_id=learner.id,
            current_streak=1,
            longest_streak=1,
            last_activity_date=today,
            total_sessions=1,
            total_xp=req.xp_earned,
            total_minutes=req.duration_seconds // 60,
        )
        db.add(streak)

    # Activity log
    log_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.learner_id    == learner.id,
            ActivityLog.activity_date == today
        )
    )
    log = log_result.scalar_one_or_none()
    if log:
        log.sessions_done += 1
        log.xp_earned     += req.xp_earned
        log.minutes_spent += req.duration_seconds // 60
    else:
        db.add(ActivityLog(
            learner_id=learner.id,
            activity_date=today,
            sessions_done=1,
            xp_earned=req.xp_earned,
            minutes_spent=req.duration_seconds // 60
        ))

    # ── Targeted skill attribution ────────────────────────────────────────
    # When the learner clicked a Learning Domain skill (e.g. "Data Analysis"),
    # find it by name and give it evidence credit so compute_radar flows
    # correctly through arts_skills → art scores for that skill's mapped arts.
    if req.skill_context:
        linked_q = await db.execute(
            select(Skill).where(func.lower(Skill.name) == req.skill_context.strip().lower())
        )
        linked_skill = linked_q.scalar_one_or_none()
        if linked_skill and linked_skill.id != session.primary_skill_id:
            lsp_q = await db.execute(
                select(LearnerSkillProgress).where(
                    LearnerSkillProgress.learner_id == learner.id,
                    LearnerSkillProgress.skill_id   == linked_skill.id,
                )
            )
            lsp = lsp_q.scalar_one_or_none()
            if not lsp:
                lsp = LearnerSkillProgress(learner_id=learner.id, skill_id=linked_skill.id)
                db.add(lsp)
            # Partial credit (half-session): recall + evidence, capped at tinyint max
            lsp.recall_count   = min((lsp.recall_count   or 0) + 1, 255)
            lsp.evidence_count = min((lsp.evidence_count or 0) + 1, 255)
            lsp.last_practiced_at = datetime.now(timezone.utc)

    # ── Contributing arts attribution ─────────────────────────────────────
    # Distribute a weighted score increment to every art the skill exercises.
    # compute_radar in engine.py blends this into art scores at 20% weight,
    # keeping skill-based learning the primary driver (80%).
    if req.contributing_arts and req.skill_context:
        weights  = SKILL_ART_WEIGHTS.get(req.skill_context, {})
        total_w  = sum(weights.values()) or len(req.contributing_arts)
        base_inc = (req.assess_score or 50) / 100 * 0.05  # max 0.05/session at 100%

        arts_q = await db.execute(
            select(Arts).where(Arts.slug.in_(req.contributing_arts))
        )
        arts_map = {a.slug: a for a in arts_q.scalars().all()}

        for slug in req.contributing_arts:
            art = arts_map.get(slug)
            if not art:
                continue
            w         = weights.get(slug, 1.0 / len(req.contributing_arts))
            increment = round(base_inc * (w / total_w), 4)
            ap_q = await db.execute(
                select(LearnerArtProgress).where(
                    LearnerArtProgress.learner_id == learner.id,
                    LearnerArtProgress.art_id     == art.id,
                )
            )
            ap = ap_q.scalar_one_or_none()
            if ap:
                ap.score = round(min(float(ap.score or 0) + increment, 1.0), 4)
            else:
                db.add(LearnerArtProgress(
                    learner_id=learner.id,
                    art_id=art.id,
                    score=round(min(increment, 1.0), 4),
                ))

    await db.commit()

    # Radar snapshot
    radar_data = await eng.compute_radar(learner.id, db)
    db.add(RadarSnapshot(
        learner_id=learner.id,
        score_being=radar_data["group_scores"].get("being", 0.0),
        score_becoming=radar_data["group_scores"].get("becoming", 0.0),
        score_connecting=radar_data["group_scores"].get("connecting", 0.0),
        art_scores=radar_data["art_scores"],
        triggered_by="session_complete"
    ))
    await db.commit()

    next_session = await eng.recommend_next(learner.id, db)
    return {
        "ok":           True,
        "level_up":     progress.current_level,
        "radar":        radar_data,
        "next_session": next_session,
    }


@router.get("/next-recommendation")
async def get_next_recommendation(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    import traceback
    try:
        return await eng.recommend_next(learner.id, db)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"recommend_next failed: {e}")


@router.get("/today")
async def get_today_sessions(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns today's completed sessions with art info, plus the
    activity_log summary for the day. Used by the Today's Journey
    dashboard card to show real phase completion instead of the XP proxy.

    Timezone: uses learner.timezone if set, falls back to UTC.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        tz = ZoneInfo(learner.timezone or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)
    today     = now_local.date()

    # Completed sessions today, joined with Arts for name/slug
    result = await db.execute(
        select(Session, Arts)
        .join(Arts, Session.art_id == Arts.id)
        .where(
            Session.learner_id == learner.id,
            Session.status     == "completed",
            func.date(Session.completed_at) == today,
        )
        .order_by(Session.completed_at)
    )
    rows = result.all()

    sessions = [
        {
            "id":               s.id,
            "title":            s.title or f"The Art of {a.name}",
            "art_name":         a.name,
            "art_slug":         a.slug,
            "phase_reached":    s.phase_reached or 0,
            "xp_earned":        s.xp_earned     or 0,
            "duration_seconds": s.duration_seconds or 0,
            "completed_at":     s.completed_at.isoformat() if s.completed_at else None,
        }
        for s, a in rows
    ]

    # Activity log summary for today
    log_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.learner_id    == learner.id,
            ActivityLog.activity_date == today,
        )
    )
    log = log_result.scalar_one_or_none()

    return {
        "date": today.isoformat(),
        "sessions": sessions,
        "summary": {
            "sessions_done": log.sessions_done if log else 0,
            "xp_earned":     log.xp_earned     if log else 0,
            "minutes_spent": log.minutes_spent  if log else 0,
        },
    }


@router.get("/history")
async def get_session_history(
    limit: int = 30,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the learner's last N completed sessions, joined with Arts for
    display name and slug. Used by the Progress page session history timeline.

    Default limit: 30. Max enforced at 100 to avoid heavy queries.
    Each row includes enough context for a rich history card:
      id, title, art_name, art_slug, xp_earned, duration_seconds,
      phase_reached, assess_score, completed_at
    """
    limit = min(limit, 100)

    result = await db.execute(
        select(Session, Arts)
        .join(Arts, Session.art_id == Arts.id)
        .where(
            Session.learner_id == learner.id,
            Session.status     == "completed",
        )
        .order_by(desc(Session.completed_at))
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "id":               s.id,
            "title":            s.title or f"The Art of {a.name}",
            "art_name":         a.name,
            "art_slug":         a.slug,
            "xp_earned":        s.xp_earned        or 0,
            "duration_seconds": s.duration_seconds  or 0,
            "phase_reached":    s.phase_reached      or 0,
            "assess_score":     s.assess_score       or None,
            "completed_at":     s.completed_at.isoformat() if s.completed_at else None,
        }
        for s, a in rows
    ]


@router.get("/activity")
async def get_activity_log(
    days: int = 30,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns one row per calendar day (most recent first) from activity_log
    for the last N days. Used by the Progress page XP history chart.

    Default window: 30 days. Max enforced at 90.
    Days with no activity are NOT included (sparse — frontend fills gaps).
    Each row: date (ISO string), sessions_done, xp_earned, minutes_spent.
    """
    from datetime import timedelta
    days  = min(days, 90)
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)

    result = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.learner_id    == learner.id,
            ActivityLog.activity_date >= since,
        )
        .order_by(desc(ActivityLog.activity_date))
    )
    rows = result.scalars().all()

    return [
        {
            "date":          row.activity_date.isoformat(),
            "sessions_done": row.sessions_done or 0,
            "xp_earned":     row.xp_earned     or 0,
            "minutes_spent": row.minutes_spent  or 0,
        }
        for row in rows
    ]


@router.get("/skills-touched")
async def get_skills_touched(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the count of distinct skills the learner has engaged with
    (evidence_count > 0 in learner_skill_progress). Used by the
    dashboard 'Skills touched' stat box as the authoritative backend value.
    """
    result = await db.execute(
        select(func.count()).select_from(LearnerSkillProgress).where(
            LearnerSkillProgress.learner_id    == learner.id,
            LearnerSkillProgress.evidence_count >  0,
        )
    )
    count = result.scalar() or 0
    return {"skills_touched": count}
