# FreqLearn — routes/learners.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from models import Learner, LearnerStreak, LearnerPreferences
from routes.auth import get_current_learner
import ai_client

router = APIRouter()

@router.get("/me")
async def get_me(learner: Learner = Depends(get_current_learner)):
    return {
        "id":           learner.id,
        "username":     learner.username,
        "display_name": learner.display_name,
        "birth_year":   learner.birth_year,
        "avatar_emoji": learner.avatar_emoji,
        "avatar_color": learner.avatar_color,
        "phase_id":     learner.phase_id,
        "language":     learner.language or "en",
        "created_at":   learner.created_at,
    }

@router.get("/me/streak")
async def get_streak(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LearnerStreak).where(LearnerStreak.learner_id == learner.id)
    )
    streak = result.scalar_one_or_none()
    if not streak:
        return {"current_streak": 0, "longest_streak": 0, "total_sessions": 0, "total_xp": 0}
    return streak


from pydantic import BaseModel
from typing import Optional
from sqlalchemy import update

class PreferencesUpdate(BaseModel):
    avatar_emoji:  Optional[str] = None
    avatar_color:  Optional[str] = None
    phase:         Optional[str] = None
    display_name:  Optional[str] = None
    first_art:     Optional[str] = None
    language:      Optional[str] = None

@router.patch("/me/preferences")
async def update_preferences(
    req: PreferencesUpdate,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    from models import DevPhase
    from sqlalchemy import select as sel

    # Update learner fields
    if req.avatar_emoji:  learner.avatar_emoji = req.avatar_emoji
    if req.avatar_color:  learner.avatar_color  = req.avatar_color
    if req.display_name:  learner.display_name  = req.display_name
    if req.language:      learner.language       = req.language

    # Update phase
    if req.phase:
        phase_q = await db.execute(sel(DevPhase).where(DevPhase.slug == req.phase))
        phase = phase_q.scalar_one_or_none()
        if phase:
            learner.phase_id = phase.id

    await db.commit()
    return {"ok": True}
# ============================================================
# ADD THIS BLOCK TO routes/learners.py
# Paste after the existing @router.patch("/me/preferences") block.
# Also add these imports at the top of learners.py if not present:
#   from models import ArtsGroup, Arts, ArtsSkills, LearnerSkillProgress
#   from datetime import datetime, timezone
# ============================================================

from pydantic import BaseModel as _BaseModel

from models import ArtsGroup, Arts, ArtsSkills, LearnerSkillProgress
from datetime import datetime, timezone

class SeedProgressRequest(_BaseModel):
    # Keys: "being", "becoming", "connecting"
    # Values: 0 = new, 1 = some experience, 2 = comfortable
    familiarity: dict


@router.post("/me/seed-progress")
async def seed_initial_progress(
    req: SeedProgressRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Called once after onboarding. Seeds learner_skill_progress rows
    based on self-reported familiarity per art group, so the
    recommendation engine has real signal from the very first session.

    Familiarity levels:
      0 = new        → evidence_count=1,  current_level=0
      1 = some       → evidence_count=2,  current_level=0
      2 = comfortable → evidence_count=0, current_level=1
    """
    # Load group → arts → skills mapping
    groups_q = await db.execute(select(ArtsGroup))
    groups   = {g.slug: g for g in groups_q.scalars().all()}

    arts_q = await db.execute(select(Arts))
    arts   = arts_q.scalars().all()

    mappings_q = await db.execute(select(ArtsSkills))
    mappings   = mappings_q.scalars().all()

    # Build group_slug → [skill_ids]
    art_to_group  = {a.id: a.group_id for a in arts}
    group_id_map  = {g.id: slug for slug, g in groups.items()}
    group_skills: dict[str, list[int]] = {}
    for m in mappings:
        gslug = group_id_map.get(art_to_group.get(m.art_id))
        if gslug:
            group_skills.setdefault(gslug, []).append(m.skill_id)

    # Existing progress rows (don't overwrite real progress)
    existing_q = await db.execute(
        select(LearnerSkillProgress)
        .where(LearnerSkillProgress.learner_id == learner.id)
    )
    existing_ids = {p.skill_id for p in existing_q.scalars().all()}

    seeded = 0
    now    = datetime.now(timezone.utc)

    for group_slug, fam_level in req.familiarity.items():
        fam_level = int(fam_level)
        skill_ids = group_skills.get(group_slug, [])

        if fam_level == 0:
            ev, lv = 1, 0     # new: tiny signal, no level
        elif fam_level == 1:
            ev, lv = 2, 0     # some: approaching level 1
        else:
            ev, lv = 0, 1     # comfortable: already at level 1

        for sid in skill_ids:
            if sid in existing_ids:
                continue      # never overwrite real session progress
            db.add(LearnerSkillProgress(
                learner_id=learner.id,
                skill_id=sid,
                current_level=lv,
                evidence_count=ev,
                recall_count=ev,
                last_practiced_at=None,
            ))
            seeded += 1

    await db.commit()
    return {"seeded": seeded}


# ── P8: org-verified skills, learner's own aggregate view ────────────
# Added 2026-07-25. Full spec: PROJECT_MASTER PART 22. Every VerifiedSkill
# row across every one of this learner's matches — the citable "org vouches
# for this" credentials, separate from (and not written into) their global
# learner_skill_progress.current_level.
@router.get("/me/verified-skills")
async def get_my_verified_skills(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    from models import VerifiedSkill, OpportunityMatch, OpportunityListing, Organization, Skill
    rows = (await db.execute(
        select(VerifiedSkill, OpportunityListing, Organization, Skill)
        .join(OpportunityMatch, OpportunityMatch.id == VerifiedSkill.match_id)
        .join(OpportunityListing, OpportunityListing.id == OpportunityMatch.listing_id)
        .join(Organization, Organization.id == OpportunityListing.org_id)
        .join(Skill, Skill.id == VerifiedSkill.skill_id)
        .where(OpportunityMatch.learner_id == learner.id)
        .order_by(VerifiedSkill.verified_at.desc())
    )).all()
    return [
        {
            "skill_name":    sk.name,
            "level":         v.level,
            "org_name":      org.name,
            "listing_title": listing.title,
            "verified_by":   v.verified_by,
            "verified_at":   v.verified_at.isoformat() if v.verified_at else None,
        }
        for v, listing, org, sk in rows
    ]


# ── Prosopon: seed initial skill signal from the 3-question onboarding card ──
# Added 2026-08-20. Functional replacement for the retired being/becoming/
# connecting familiarity self-assessment (which used to drive /me/seed-progress
# via ArtsGroup). This version classifies against the 8 Mouseion domains,
# matched by Skill.name against MOUSEION_DOMAIN_SKILLS below (mirrored from
# frontend/app.js's _DOMS) rather than by Skill.learning_domain — that column
# is populated with a different, legacy subject-matter taxonomy, not the 8
# Mouseion domains (see MOUSEION_DOMAIN_SKILLS comment). One small AI call,
# run once at onboarding completion. See SESSION_ARCHITECTURE.md §2.4
# (Profile Distiller) for how this feeds learner_profile downstream, and
# frontend/docs/prosopon.md for the learner-facing explanation.

class SeedProgressDomainsRequest(_BaseModel):
    curiosity:   Optional[str] = None
    cares_about: Optional[str] = None
    wants_to_do: Optional[str] = None


# The 8 Mouseion domains and their 48 skills, mirrored 1:1 from frontend/app.js's
# _DOMS (inside Mouseion()) — that array is the sole source of truth for this
# grouping and is entirely client-side/hardcoded, NOT sourced from any DB column.
# Deliberately matching by Skill.name here rather than trusting Skill.learning_domain:
# that DB column is populated with a different, older subject-matter taxonomy
# (Physiology, Physics, etc. — see backend/routes/generate.py's skill_id lookup
# path, and models.Lecko.learning_domain, which shares the same legacy values).
# Per 2026-08-20 decision, that legacy taxonomy is retired everywhere it's not
# load-bearing for real functionality; Skill.learning_domain itself is left alone
# here since generate.py's LECKO-similarity matching still depends on its current
# values — repurposing that column is a separate, bigger decision, not this one.
MOUSEION_DOMAIN_SKILLS = {
    "Cognitive & Intellectual": ["Critical Thinking","Problem Solving","Systems Thinking","Memory & Retention","Decision Making","Project Management"],
    "Creative & Artistic": ["Visual Art","Music & Rhythm","Creative Writing","Drama & Theatre","Improvisation & Public Speaking","Craftsmanship & Making"],
    "Physical & Motor": ["Gross Motor","Fine Motor","Physical Fitness","Dance & Movement","Body Awareness","First Aid & Nursing"],
    "Social & Relational": ["Collaboration","Conflict Resolution","Empathetic Leadership","Negotiation","Cultural Competence","Parenting & Caregiving"],
    "Language & Communication": ["Active Reading","Active Listening","Storytelling","Debate & Argumentation","Foreign Language Acquisition","Rhetoric & Persuasion"],
    "Emotional & Psychological": ["Self-Awareness","Emotional Regulation","Empathy and Compassion","Self-Efficacy","Contemplative Practice","Gratitude & Appreciation"],
    "Meta-Learning": ["Learning How to Learn","Self-Regulation","Personal Values","Curiosity and Exploration","Vision, Mission and Purpose","Mentorship & Teaching"],
    "Tools & Systems": ["Digital Literacy","Data Analysis & Statistics","Design Thinking","Philosophy & Ethics","Permaculture","Cooking & Nutrition"],
}
MOUSEION_DOMAINS = list(MOUSEION_DOMAIN_SKILLS.keys())


@router.post("/me/seed-progress-domains")
async def seed_progress_from_prosopon_answers(
    req: SeedProgressDomainsRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    """
    Classifies the learner's 3 onboarding answers against the 8 Mouseion
    domains and seeds light learner_skill_progress signal (evidence_count=2,
    current_level=0 — the same "some experience" tier the old familiarity
    screen used for its middle option) for every skill in each matched
    domain. Never overwrites existing real progress. No-ops silently if all
    3 answers were skipped or the AI call fails — onboarding must never
    block on this.
    """
    text = " ".join(x for x in (req.curiosity, req.cares_about, req.wants_to_do) if x).strip()
    if not text:
        return {"seeded": 0, "domains": []}

    import json
    from models import Skill

    prompt = f"""A new learner on the Surfing the Frequencies platform answered three onboarding questions:

{text}

Which of these 8 learning domains genuinely connect to what they wrote? Pick 1-4, only ones with a real connection — do not force a match for every answer.

Domains: {", ".join(MOUSEION_DOMAINS)}

Return ONLY a JSON object: {{"domains": ["Domain Name", ...]}} using the exact domain names above."""

    try:
        ai_resp = await ai_client.ai_complete(
            "learner_profile",
            db=db,
            prompt=prompt,
            tier="small",
            response_format="json_object",
            max_tokens=150,
            temperature=0.3,
        )
        picked = json.loads(ai_resp.content).get("domains", [])
        picked = [d for d in picked if d in MOUSEION_DOMAINS]
    except Exception as e:
        return {"seeded": 0, "domains": [], "error": str(e)[:120]}

    if not picked:
        return {"seeded": 0, "domains": []}

    skill_names = [name for d in picked for name in MOUSEION_DOMAIN_SKILLS.get(d, [])]
    skills_q = await db.execute(select(Skill).where(Skill.name.in_(skill_names)))
    skills = skills_q.scalars().all()

    existing_q = await db.execute(
        select(LearnerSkillProgress).where(LearnerSkillProgress.learner_id == learner.id)
    )
    existing_ids = {p.skill_id for p in existing_q.scalars().all()}

    seeded = 0
    for sk in skills:
        if sk.id in existing_ids:
            continue
        db.add(LearnerSkillProgress(
            learner_id=learner.id,
            skill_id=sk.id,
            current_level=0,
            evidence_count=2,
            recall_count=2,
            last_practiced_at=None,
        ))
        seeded += 1

    await db.commit()
    return {"seeded": seeded, "domains": picked}
