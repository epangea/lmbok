# ============================================================
# FreqLearn Backend — models.py  (v2 — matches schema v2)
# All classes derived from schema.sql v2
# ============================================================

from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Integer, SmallInteger, String, Text, Boolean, DateTime, Date,
    JSON, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db import Base


class DevPhase(Base):
    __tablename__ = "dev_phases"
    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]           = mapped_column(String(30), nullable=False)
    slug:        Mapped[str]           = mapped_column(String(30), unique=True, nullable=False)
    age_range:   Mapped[Optional[str]] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order:  Mapped[int]           = mapped_column(Integer, default=0)


class ArtsGroup(Base):
    __tablename__ = "arts_group"
    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]           = mapped_column(String(40), nullable=False)
    slug:        Mapped[str]           = mapped_column(String(40), unique=True, nullable=False)
    tagline:     Mapped[Optional[str]] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text)
    color_hex:   Mapped[Optional[str]] = mapped_column(String(7))
    sort_order:  Mapped[int]           = mapped_column(Integer, default=0)
    arts: Mapped[list["Arts"]] = relationship("Arts", back_populates="group")


class Arts(Base):
    __tablename__ = "arts"
    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    group_id:    Mapped[int]           = mapped_column(ForeignKey("arts_group.id"), nullable=False)
    name:        Mapped[str]           = mapped_column(String(40),  nullable=False)
    slug:        Mapped[str]           = mapped_column(String(40),  unique=True, nullable=False)
    tagline:     Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order:  Mapped[int]           = mapped_column(Integer, default=0)
    group: Mapped["ArtsGroup"] = relationship(back_populates="arts")


class Skill(Base):
    __tablename__ = "skills"
    id:                  Mapped[int]           = mapped_column(SmallInteger, primary_key=True)
    name:                Mapped[str]           = mapped_column(String(120), nullable=False)
    slug:                Mapped[str]           = mapped_column(String(120), unique=True, nullable=False)
    subcategory:         Mapped[Optional[str]] = mapped_column(String(80))
    description:         Mapped[Optional[str]] = mapped_column(Text)
    learning_domain:     Mapped[Optional[str]] = mapped_column(String(80))
    skill_type:          Mapped[str]           = mapped_column(String(40), default="cognitive")
    developmental_stage: Mapped[Optional[str]] = mapped_column(String(80))
    max_level:           Mapped[int]           = mapped_column(Integer, default=3)
    is_active:           Mapped[bool]          = mapped_column(Boolean, default=True)
    sort_order:          Mapped[int]           = mapped_column(SmallInteger, default=0)


class Learner(Base):
    __tablename__ = "learners"
    id:            Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    username:      Mapped[str]           = mapped_column(String(40),  unique=True, nullable=False)
    email:         Mapped[str]           = mapped_column(String(180), unique=True, nullable=False)
    password_hash: Mapped[str]           = mapped_column(String(255), nullable=False)
    display_name:  Mapped[Optional[str]] = mapped_column(String(80))
    birth_year:    Mapped[Optional[int]] = mapped_column(SmallInteger)
    phase_id:      Mapped[Optional[int]] = mapped_column(ForeignKey("dev_phases.id"))
    avatar_emoji:  Mapped[Optional[str]] = mapped_column(String(8))
    avatar_color:  Mapped[str]           = mapped_column(String(7), default="#1D9E75")
    timezone:      Mapped[str]           = mapped_column(String(50), default="UTC")
    language:      Mapped[str]           = mapped_column(String(10), default="en")
    is_active:     Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]      = mapped_column(DateTime, default=func.now())
    last_seen_at:     Mapped[Optional[datetime]] = mapped_column(DateTime)
    learner_profile:        Mapped[Optional[str]]      = mapped_column(Text)
    bioregion:              Mapped[Optional[str]]      = mapped_column(String(100))
    onboarding_complete:   Mapped[bool]               = mapped_column(SmallInteger, default=0)
    email_verified:         Mapped[bool]               = mapped_column(Boolean, default=False)
    verification_token:     Mapped[Optional[str]]      = mapped_column(String(255))
    verification_expires:   Mapped[Optional[datetime]] = mapped_column(DateTime)

    preferences:    Mapped[Optional["LearnerPreferences"]]     = relationship(back_populates="learner", uselist=False)
    skill_progress: Mapped[list["LearnerSkillProgress"]]       = relationship(back_populates="learner")
    sessions:       Mapped[list["Session"]]                    = relationship(back_populates="learner")
    streak:         Mapped[Optional["LearnerStreak"]]          = relationship(back_populates="learner", uselist=False)
    snapshots:      Mapped[list["RadarSnapshot"]]              = relationship(back_populates="learner")


class LearnerPreferences(Base):
    __tablename__ = "learner_preferences"
    learner_id:             Mapped[int]           = mapped_column(ForeignKey("learners.id"), primary_key=True)
    daily_goal_minutes:     Mapped[int]           = mapped_column(Integer, default=20)
    preferred_session_time: Mapped[Optional[str]] = mapped_column(String(20))
    notify_streak:          Mapped[bool]          = mapped_column(Boolean, default=True)
    allow_matching:         Mapped[bool]          = mapped_column(Boolean, default=True)
    profile_visible:        Mapped[bool]          = mapped_column(Boolean, default=False)
    tier:                   Mapped[int]           = mapped_column(Integer, default=1)
    updated_at:             Mapped[datetime]      = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    learner: Mapped["Learner"] = relationship(back_populates="preferences")


class LearnerArtProgress(Base):
    __tablename__ = "learner_art_progress"
    learner_id: Mapped[int]   = mapped_column(ForeignKey("learners.id"), primary_key=True)
    art_id:     Mapped[int]   = mapped_column(ForeignKey("arts.id"),     primary_key=True)
    score:      Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class LearnerSkillProgress(Base):
    __tablename__ = "learner_skill_progress"
    id:                  Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id:          Mapped[int]           = mapped_column(ForeignKey("learners.id"), nullable=False)
    skill_id:            Mapped[int]           = mapped_column(ForeignKey("skills.id"),   nullable=False)
    current_level:       Mapped[int]           = mapped_column(Integer, default=0)
    evidence_count:      Mapped[int]           = mapped_column(Integer, default=0)
    recall_count:        Mapped[int]           = mapped_column(Integer, default=0)
    transfer_count:      Mapped[int]           = mapped_column(Integer, default=0)
    self_assessed_level: Mapped[Optional[int]] = mapped_column(Integer)
    last_practiced_at:   Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_review_at:      Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at:          Mapped[datetime]      = mapped_column(DateTime, default=func.now())
    updated_at:          Mapped[datetime]      = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("learner_id", "skill_id", name="uq_learner_skill"),)
    learner: Mapped["Learner"] = relationship(back_populates="skill_progress")
    skill:   Mapped["Skill"]   = relationship()


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    id:             Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    progress_id:    Mapped[int] = mapped_column(ForeignKey("learner_skill_progress.id"), nullable=False)
    level_achieved: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type:  Mapped[str] = mapped_column(String(30), nullable=False)
    description:    Mapped[Optional[str]] = mapped_column(Text)
    content_url:    Mapped[Optional[str]] = mapped_column(String(500))
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=func.now())


class Session(Base):
    __tablename__ = "sessions"
    id:                  Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id:          Mapped[int]           = mapped_column(ForeignKey("learners.id"), nullable=False)
    art_id:              Mapped[int]           = mapped_column(ForeignKey("arts.id"),     nullable=False)
    dev_phase_id:        Mapped[Optional[int]] = mapped_column(ForeignKey("dev_phases.id"), nullable=True)
    language:            Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="en")  # UI language at generation time
    lecko_id:            Mapped[Optional[int]] = mapped_column(ForeignKey("leckos.id"))
    primary_skill_id:    Mapped[int]           = mapped_column(ForeignKey("skills.id"),  nullable=False)
    secondary_skill_ids: Mapped[Optional[dict]] = mapped_column(JSON)
    title:               Mapped[Optional[str]] = mapped_column(String(160))
    recommended_by:      Mapped[str]           = mapped_column(String(20), default="engine")
    engine_reasoning:    Mapped[Optional[dict]] = mapped_column(JSON)
    # AI-call metadata (added 2026-07-07, migration scripts/2026-06-28-session-ai-metadata.sql)
    model:               Mapped[Optional[str]]  = mapped_column(String(80), nullable=True)   # e.g. "llama-3.3-70b-versatile", "ollama:llama3.1:8b", "library"
    latency_ms:          Mapped[Optional[int]]  = mapped_column(Integer,    nullable=True)   # wall-clock ms of the AI call; 0 for library-cached
    status:              Mapped[str]           = mapped_column(String(20), default="scheduled")
    phase_reached:       Mapped[int]           = mapped_column(Integer, default=0)
    duration_seconds:    Mapped[Optional[int]] = mapped_column(SmallInteger)
    xp_earned:           Mapped[int]           = mapped_column(Integer, default=0)
    warmup_prompt:       Mapped[Optional[str]] = mapped_column(Text)
    explore_content:     Mapped[Optional[str]] = mapped_column(Text)
    challenge_prompt:    Mapped[Optional[str]] = mapped_column(Text)
    reflect_prompt:      Mapped[Optional[str]] = mapped_column(Text)
    assess_question:     Mapped[Optional[dict]] = mapped_column(JSON)
    challenge_response:  Mapped[Optional[str]] = mapped_column(Text)
    reflect_response:    Mapped[Optional[str]] = mapped_column(Text)
    assess_score:        Mapped[Optional[int]] = mapped_column(Integer)
    assess_selected_index: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)  # 0-based index of the option the learner picked; NULL if not answered
    started_at:          Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at:        Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at:          Mapped[datetime]      = mapped_column(DateTime, default=func.now())
    learner: Mapped["Learner"] = relationship(back_populates="sessions")


class LearnerStreak(Base):
    __tablename__ = "learner_streaks"
    learner_id:         Mapped[int] = mapped_column(ForeignKey("learners.id"), primary_key=True)
    current_streak:     Mapped[int] = mapped_column(SmallInteger, default=0)
    longest_streak:     Mapped[int] = mapped_column(SmallInteger, default=0)
    last_activity_date: Mapped[Optional[date]] = mapped_column(Date)
    total_sessions:     Mapped[int] = mapped_column(SmallInteger, default=0)
    total_xp:           Mapped[int] = mapped_column(Integer, default=0)
    total_minutes:      Mapped[int] = mapped_column(Integer, default=0)
    learner: Mapped["Learner"] = relationship(back_populates="streak")


class ActivityLog(Base):
    __tablename__ = "activity_log"
    learner_id:    Mapped[int]  = mapped_column(ForeignKey("learners.id"), primary_key=True)
    activity_date: Mapped[date] = mapped_column(Date, primary_key=True)
    sessions_done: Mapped[int]  = mapped_column(Integer, default=0)
    xp_earned:     Mapped[int]  = mapped_column(SmallInteger, default=0)
    minutes_spent: Mapped[int]  = mapped_column(SmallInteger, default=0)


class RadarSnapshot(Base):
    __tablename__ = "radar_snapshots"
    id:               Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id:       Mapped[int]   = mapped_column(ForeignKey("learners.id"), nullable=False)
    score_being:      Mapped[float] = mapped_column(default=0.0)
    score_becoming:   Mapped[float] = mapped_column(default=0.0)
    score_connecting: Mapped[float] = mapped_column(default=0.0)
    art_scores:       Mapped[dict]  = mapped_column(JSON, nullable=False)
    triggered_by:     Mapped[str]   = mapped_column(String(30), default="session_complete")
    created_at:       Mapped[datetime] = mapped_column(DateTime, default=func.now())
    learner: Mapped["Learner"] = relationship(back_populates="snapshots")


class Reflection(Base):
    __tablename__ = "reflections"
    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[int]           = mapped_column(ForeignKey("learners.id"), nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sessions.id"))
    art_id:     Mapped[Optional[int]] = mapped_column(ForeignKey("arts.id"))
    prompt:     Mapped[Optional[str]] = mapped_column(Text)
    body:       Mapped[str]           = mapped_column(Text, nullable=False)
    is_private: Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=func.now())


class Organization(Base):
    __tablename__ = "organizations"
    id:            Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:          Mapped[str]           = mapped_column(String(160), nullable=False)
    slug:          Mapped[str]           = mapped_column(String(160), unique=True, nullable=False)
    description:   Mapped[Optional[str]] = mapped_column(Text)
    website:       Mapped[Optional[str]] = mapped_column(String(300))
    contact_email: Mapped[Optional[str]] = mapped_column(String(180))
    org_type:      Mapped[str]           = mapped_column(String(20), default="other")
    bioregion:     Mapped[Optional[str]] = mapped_column(String(100))
    is_verified:   Mapped[bool]          = mapped_column(Boolean, default=False)
    is_active:     Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]      = mapped_column(DateTime, default=func.now())
    # 2026-07-18 fix: these two columns were added to the live DB via the
    # ALTER TABLE in orgs.py's module docstring, but never added here — so
    # every Organization(password_hash=...) construction in orgs.py's
    # register_org() raised "'password_hash' is an invalid keyword argument
    # for Organization" (a Python TypeError, before any DB call), which is
    # why POST /api/orgs/register 500'd with nothing DB-related to show for
    # it. login_org()'s org.password_hash read would have hit the same
    # missing-attribute problem for any org that *did* exist.
    password_hash:    Mapped[Optional[str]] = mapped_column(String(255))
    org_token_secret: Mapped[Optional[str]] = mapped_column(String(100))


class OpportunityListing(Base):
    __tablename__ = "opportunity_listings"
    id:              Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:          Mapped[int]            = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title:           Mapped[str]            = mapped_column(String(200), nullable=False)
    description:     Mapped[Optional[str]]  = mapped_column(Text)
    listing_type:    Mapped[str]            = mapped_column(String(30), default="project")
    required_skills: Mapped[dict]           = mapped_column(JSON, nullable=False)
    required_arts:   Mapped[Optional[dict]] = mapped_column(JSON)
    phase_min:       Mapped[Optional[int]]  = mapped_column(Integer)
    phase_max:       Mapped[Optional[int]]  = mapped_column(Integer)
    is_active:       Mapped[bool]           = mapped_column(Boolean, default=True)
    source_url:      Mapped[Optional[str]]  = mapped_column(String(500))
    scavenged:       Mapped[bool]           = mapped_column(Boolean, default=False)
    created_at:      Mapped[datetime]       = mapped_column(DateTime, default=func.now())


class OpportunityMatch(Base):
    __tablename__ = "opportunity_matches"
    id:             Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id:     Mapped[int]            = mapped_column(ForeignKey("learners.id"), nullable=False)
    listing_id:     Mapped[int]            = mapped_column(ForeignKey("opportunity_listings.id"), nullable=False)
    match_score:    Mapped[Optional[int]]  = mapped_column(Integer)
    skills_met:     Mapped[Optional[dict]] = mapped_column(JSON)
    skills_gap:     Mapped[Optional[dict]] = mapped_column(JSON)
    arts_met:       Mapped[Optional[dict]] = mapped_column(JSON)
    learner_status: Mapped[str]            = mapped_column(String(20), default="pending")
    org_status:     Mapped[str]            = mapped_column(String(20), default="pending")
    matched_at:     Mapped[datetime]       = mapped_column(DateTime, default=func.now())
    __table_args__ = (UniqueConstraint("learner_id", "listing_id", name="uq_match"),)


class Message(Base):
    __tablename__ = "messages"
    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id:    Mapped[int]           = mapped_column(ForeignKey("opportunity_matches.id"), nullable=False)
    sender_type: Mapped[str]           = mapped_column(String(10), nullable=False)
    sender_id:   Mapped[int]           = mapped_column(Integer, nullable=False)
    body:        Mapped[str]           = mapped_column(Text, nullable=False)
    read_at:     Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=func.now())


class Lecko(Base):
    __tablename__ = "leckos"
    id:              Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    art_id:          Mapped[int]           = mapped_column(ForeignKey("arts.id"), nullable=False)
    phase_id:        Mapped[int]           = mapped_column(ForeignKey("dev_phases.id"), nullable=False)
    title:           Mapped[str]           = mapped_column(String(200), nullable=False)
    description:     Mapped[Optional[str]] = mapped_column(Text)
    learning_domain: Mapped[Optional[str]] = mapped_column(String(80))
    skill_type:      Mapped[str]           = mapped_column(String(40), default="cognitive")
    assessment_type: Mapped[str]           = mapped_column(String(60), default="task")
    assessment_desc: Mapped[Optional[str]] = mapped_column(Text)
    community_need:  Mapped[Optional[str]] = mapped_column(Text)
    source_credit:   Mapped[Optional[str]] = mapped_column(String(300))
    evidence_url:    Mapped[Optional[str]] = mapped_column(String(500))
    utility_score:   Mapped[float]         = mapped_column(default=0.0)
    is_active:       Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:      Mapped[datetime]      = mapped_column(DateTime, default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[int]      = mapped_column(ForeignKey("learners.id"), nullable=False)
    token_hash: Mapped[str]      = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class ArtsSkills(Base):
    __tablename__ = "arts_skills"
    art_id:     Mapped[int] = mapped_column(ForeignKey("arts.id"),    primary_key=True)
    skill_id:   Mapped[int] = mapped_column(ForeignKey("skills.id"),  primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)


class BioregionContribution(Base):
    """Personal bioregion statement submitted by a learner."""
    __tablename__ = "bioregion_contributions"
    id:             Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id:     Mapped[int]           = mapped_column(ForeignKey("learners.id"), nullable=False)
    bioregion_name: Mapped[str]           = mapped_column(String(100), nullable=False)
    lat:            Mapped[Optional[float]] = mapped_column()
    lng:            Mapped[Optional[float]] = mapped_column()
    statement:      Mapped[str]           = mapped_column(Text, nullable=False)
    status:         Mapped[str]           = mapped_column(String(20), default="pending")  # pending | approved | rejected
    portrait_id:    Mapped[Optional[int]] = mapped_column(ForeignKey("bioregion_portraits.id"), nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=func.now())


class BioregionPortrait(Base):
    """AI-synthesised collective portrait for a geographic cluster."""
    __tablename__ = "bioregion_portraits"
    id:                Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_label:     Mapped[str]           = mapped_column(String(100), nullable=False)
    center_lat:        Mapped[Optional[float]] = mapped_column()
    center_lng:        Mapped[Optional[float]] = mapped_column()
    radius_km:         Mapped[int]           = mapped_column(Integer, default=50)
    summary:           Mapped[Optional[str]] = mapped_column(Text)
    contributor_count: Mapped[int]           = mapped_column(Integer, default=0)
    last_generated_at:   Mapped[Optional[datetime]] = mapped_column(DateTime)
    version_number:       Mapped[Optional[int]]      = mapped_column(Integer, default=1)
    vitality_snapshot:    Mapped[Optional[str]]      = mapped_column(String(120))
    change_notes:         Mapped[Optional[str]]      = mapped_column(Text)
    created_at:           Mapped[datetime]            = mapped_column(DateTime, default=func.now())
