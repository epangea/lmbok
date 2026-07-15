# ============================================================
# FreqLearn — routes/generate.py
# AI-powered session content generation
# Provider priority: Groq (free) → Ollama (local) → HTTPException
# Every generated session is stored in the DB before serving.
# ============================================================

import os
import json
import random
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as sql_text
from pydantic import BaseModel
from db import get_db
# FIX: ArtsSkills added here — it was missing from this import,
# causing NameError in the reuse branch before the inline import was reached.
from models import Session, Arts, DevPhase, Skill, Learner, Lecko, ArtsSkills
from routes.auth import get_current_learner
from prior_session_context import get_prior_session_context

# Default values for the AI platform settings.
# If the platform_settings table is empty (fresh DB, migration not run),
# we fall back to these so the route still works.
#
# 2026-07-15: added ai_inline_reuse_enabled (default "false"),
# ai_library_failure_threshold, and ai_library_mode_ttl. These back out the
# 2026-06-27 regression where the old "serve a stored session if >=3 exist"
# inline-reuse branch (below) was silently shadowing the AI-first path for
# every art that already had a handful of stored sessions -- see BRIEFING
# 2026-07-09. AI is now tried first unconditionally; inline reuse only runs
# if an admin explicitly re-enables it via ai_inline_reuse_enabled=true.
_AI_SETTINGS_DEFAULTS = {
    "ai_circuit_breaker_enabled":    "true",
    "ai_include_prior_context":      "true",
    "ai_library_recall_limit":       "200",
    "ai_inline_reuse_enabled":       "false",
    "ai_library_failure_threshold":  "3",
    "ai_library_mode_ttl":           "600",
}

_AI_SETTINGS_KEYS = tuple(_AI_SETTINGS_DEFAULTS.keys())


async def _load_ai_settings(db: AsyncSession) -> dict[str, str]:
    """Read the AI platform settings from the DB. Read on every /session call
    so admin can flip the flags without a process restart. Falls back to
    _AI_SETTINGS_DEFAULTS for any missing key (covers pre-migration DBs).
    """
    try:
        placeholders = ", ".join(f"'{k}'" for k in _AI_SETTINGS_KEYS)
        rows = await db.execute(
            sql_text(
                f"SELECT key_name, value FROM platform_settings "
                f"WHERE key_name IN ({placeholders})"
            )
        )
        out = dict(_AI_SETTINGS_DEFAULTS)
        for k, v in rows.all():
            if v is not None:
                out[k] = str(v)
        return out
    except Exception:
        # If platform_settings doesn't exist (pre-migration), return defaults.
        return dict(_AI_SETTINGS_DEFAULTS)


def _bool_setting(ai_settings: dict[str, str], key: str) -> bool:
    return ai_settings.get(key, _AI_SETTINGS_DEFAULTS[key]).strip().lower() in ("true", "1", "yes", "on")


def _int_setting(ai_settings: dict[str, str], key: str) -> int:
    try:
        return int(ai_settings.get(key, _AI_SETTINGS_DEFAULTS[key]))
    except (TypeError, ValueError):
        return int(_AI_SETTINGS_DEFAULTS[key])

router = APIRouter()


# ============================================================
# Circuit breaker (in-process)
# Spec (2026-06-28, reconfirmed 2026-07-01):
#   - Track consecutive AI failures on the /session route.
#   - < 3 consecutive failures  -> return 503 (caller sees "AI is sick").
#   - >= 3 consecutive failures -> enter LIBRARY MODE for 10 minutes:
#       serve from the stored session library; do not attempt AI.
#   - After 10 minutes in library mode, reset the counter and try AI again.
#   - A successful AI call resets the counter.
# In-process state is intentional: a process restart clears the breaker,
# which is the right behavior (a fresh process should retry the upstream).
# ============================================================
class CircuitBreaker:
    """Tiny in-memory breaker for the /session AI chain.

    2026-07-15: threshold/TTL are now configurable per-call via configure()
    (backed by platform_settings ai_library_failure_threshold /
    ai_library_mode_ttl) instead of being fixed class constants. Defaults
    below match the original spec (3 failures / 10 minutes) and are used
    whenever the settings table doesn't override them.
    """

    # Trips after this many consecutive AI failures.
    FAILURE_THRESHOLD = 3
    # How long library mode lasts once tripped (seconds).
    LIBRARY_MODE_TTL = 600   # 10 minutes

    def __init__(self):
        self.consecutive_failures: int = 0
        self.library_mode_until: float = 0.0   # epoch seconds; 0 = not in library mode
        self.last_failure_at: float = 0.0
        self.last_failure_reason: str = ""
        # Runtime-configurable (see configure()); start at class defaults.
        self.failure_threshold: int = self.FAILURE_THRESHOLD
        self.library_mode_ttl: int = self.LIBRARY_MODE_TTL

    def configure(self, failure_threshold: int, library_mode_ttl: int) -> None:
        """Apply the latest platform_settings values. Cheap -- call every request."""
        self.failure_threshold = max(1, failure_threshold)
        self.library_mode_ttl = max(1, library_mode_ttl)

    def is_library_mode(self) -> bool:
        if self.library_mode_until == 0.0:
            return False
        if time.monotonic() >= self.library_mode_until:
            # TTL elapsed -- exit library mode, reset counter, next call will
            # try the AI again.
            self.library_mode_until = 0.0
            self.consecutive_failures = 0
            return False
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.library_mode_until = 0.0
        self.last_failure_reason = ""

    def record_failure(self, reason: str) -> None:
        self.consecutive_failures += 1
        self.last_failure_at = time.monotonic()
        self.last_failure_reason = reason[:200]
        if self.consecutive_failures >= self.failure_threshold:
            self.library_mode_until = time.monotonic() + self.library_mode_ttl

    def status(self) -> dict:
        return {
            "consecutive_failures": self.consecutive_failures,
            "library_mode":         self.is_library_mode(),
            "library_mode_seconds_remaining": (
                max(0, int(self.library_mode_until - time.monotonic()))
                if self.library_mode_until else 0
            ),
            "last_failure_reason":  self.last_failure_reason,
            "failure_threshold":    self.failure_threshold,
            "library_mode_ttl":     self.library_mode_ttl,
        }


session_breaker = CircuitBreaker()


class GenerateRequest(BaseModel):
    art_slug:          str
    phase_slug:        str | None = "adult"
    skill_id:          int | None = None
    skill_context:     str | None = None   # display name when launched from a Learning Domain skill
    learner_interests: str | None = None
    language:          str | None = "en"


class GeneratedSession(BaseModel):
    warmup_prompt:    str
    explore_content:  str
    challenge_prompt: str
    reflect_prompt:   str
    assess_question:  dict   # {question, options: [], correct_index: int}
    title:            str
    art_name:         str
    art_slug:         str
    art_id:           int | None = None
    skill_id:         int | None = None
    session_id:       int | None = None


@router.post("/session", response_model=GeneratedSession)
async def generate_session(
    req: GenerateRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    # ── Fetch art and phase context ───────────────────────────
    art_q = await db.execute(select(Arts).where(Arts.slug == req.art_slug))
    art   = art_q.scalar_one_or_none()
    if not art:
        raise HTTPException(404, f"Art not found: {req.art_slug}")

    phase_slug = req.phase_slug or "adult"
    phase_q = await db.execute(select(DevPhase).where(DevPhase.slug == phase_slug))
    phase   = phase_q.scalar_one_or_none()
    phase_name = phase.name if phase else "Adult"
    age_range  = phase.age_range if phase else "18-60"

    # ── Fetch skill context if provided ──────────────────────
    skill_name   = None
    skill_domain = None
    skill_type   = None
    if req.skill_id:
        skill_q = await db.execute(select(Skill).where(Skill.id == req.skill_id))
        skill = skill_q.scalar_one_or_none()
        if skill:
            skill_name   = skill.name
            skill_domain = skill.learning_domain   # e.g. "Physiology", "Visual Art & Expression"
            skill_type   = skill.skill_type         # e.g. "cognitive", "psychomotor", "affective"
    # Use explicit skill_context when no skill_id (e.g. Learning Domain skill click)
    if not skill_name and req.skill_context:
        skill_name = req.skill_context

    # ── Load AI platform settings + build LEARNER CONTINUITY block ─────────
    # 2026-07-07: the continuity block (built by prior_session_context.py)
    # is appended just before the generation request when the feature flag
    # `ai_include_prior_context` is true. The block lists the learner's
    # last 3 sessions for this (art, phase) so each generation builds on
    # prior work rather than repeating themes.
    ai_settings = await _load_ai_settings(db)
    include_prior = _bool_setting(ai_settings, "ai_include_prior_context")
    breaker_enabled = _bool_setting(ai_settings, "ai_circuit_breaker_enabled")
    session_breaker.configure(
        failure_threshold=_int_setting(ai_settings, "ai_library_failure_threshold"),
        library_mode_ttl=_int_setting(ai_settings, "ai_library_mode_ttl"),
    )
    continuity_block = ""
    if include_prior:
        continuity_block = await get_prior_session_context(
            db=db,
            learner_id=learner.id,
            art_id=art.id,
            dev_phase_id=phase.id if phase else None,
            n=3,
        )

    # ── Circuit-breaker pre-check ────────────────────────────
    # If the breaker has already tripped (>= N consecutive AI failures,
    # N = ai_library_failure_threshold), we are in LIBRARY MODE: serve from
    # the stored session library for the configured TTL without ever
    # calling the AI. is_library_mode() also auto-resets once the TTL
    # elapses. Gated on ai_circuit_breaker_enabled -- if an admin disables
    # the breaker, every request always tries AI first and a run of
    # failures just returns 503 repeatedly rather than auto-switching to
    # library mode.
    if breaker_enabled and session_breaker.is_library_mode():
        library_served = await _serve_from_library(
            db=db, learner=learner, art=art,
            phase=phase, phase_id=phase.id if phase else None,
            phase_slug=phase_slug, phase_name=phase_name,
            req=req,
        )
        if library_served is not None:
            return library_served
        # Library had nothing usable for this art/phase -- surface 503
        # rather than fall through to the AI (we are in library mode on
        # purpose; the AI is the thing that is sick).
        raise HTTPException(
            503,
            "AI generation is paused and no library session matched this "
            "art/phase/language. Please try again in a few minutes."
        )

    # ── Check if a recent stored session exists for this art/phase ──
    # Phase filtering done in Python (dev_phase_id added to models.py separately)
    existing_q = await db.execute(
        select(Session)
        .where(
            Session.art_id == art.id,
            Session.warmup_prompt != None,
            Session.status.in_(["completed", "scheduled"])
        )
        .order_by(Session.created_at.desc())
        .limit(200)
    )
    all_stored = existing_q.scalars().all()

    # Prefer phase-matched sessions; fall back to untagged (legacy/adult content)
    phase_id = phase.id if phase else None
    if phase_id:
        existing = [s for s in all_stored
                    if getattr(s, 'dev_phase_id', None) in (None, phase_id)]
        # If no phase matches at all, fall back to untagged only
        if not existing:
            existing = [s for s in all_stored
                        if getattr(s, 'dev_phase_id', None) is None]
    else:
        existing = all_stored

    # Filter to sessions NOT recently seen by this learner
    seen_q = await db.execute(
        select(Session.warmup_prompt)
        .where(Session.learner_id == learner.id, Session.art_id == art.id)
        .order_by(Session.created_at.desc())
        .limit(30)
    )
    recently_seen = {row[0] for row in seen_q.all()}

    reusable = [s for s in existing if s.warmup_prompt not in recently_seen]

    # ── Inline reuse (OFF by default — see BRIEFING 2026-07-09) ─────
    # This branch used to fire unconditionally whenever >=3 stored sessions
    # existed for the art, which meant it silently pre-empted the AI-first
    # path for almost every request (2,623 stored sessions means nearly
    # every art clears the >=3 bar). AI is now the default path; this only
    # runs if an admin explicitly flips ai_inline_reuse_enabled=true in
    # Settings (e.g. to cut AI spend during a traffic spike). The circuit
    # breaker below remains the sole automatic AI→library fallback.
    inline_reuse_enabled = _bool_setting(ai_settings, "ai_inline_reuse_enabled")
    if inline_reuse_enabled and not req.skill_context and len(reusable) >= 3:
        stored = random.choice(reusable[:30])  # wider random pool

        skill_q2 = await db.execute(
            select(ArtsSkills).where(ArtsSkills.art_id == art.id).limit(1)
        )
        reuse_arts_skill = skill_q2.scalar_one_or_none()
        reuse_skill_id   = reuse_arts_skill.skill_id if reuse_arts_skill else 1

        # FIX 2 (option B bias): shuffle stored assess options on every serve
        # so the correct answer isn't always at the same index.
        stored_aq    = dict(stored.assess_question)
        opts         = list(stored_aq["options"])
        correct_text = opts[stored_aq["correct_index"]]
        random.shuffle(opts)
        stored_aq["options"]        = opts
        stored_aq["correct_index"]  = opts.index(correct_text)

        # FIX 1b: create a session record under this learner so it appears
        # in recently_seen next time, and gives a real session_id for /complete.
        served = Session(
            learner_id=learner.id,
            art_id=art.id,
            primary_skill_id=reuse_skill_id,
            title=stored.title or f"The Art of {art.name}",
            recommended_by="engine",
            # Inline-reuse sessions are pre-existing content served as-is
            # (not from library mode and not via AI). Tag them as "library"
            # for consistency with the circuit-breaker library path, so the
            # admin can see which sessions were AI-generated vs. reused.
            model="library",
            latency_ms=0,
            status="scheduled",
            warmup_prompt=stored.warmup_prompt,
            explore_content=stored.explore_content,
            challenge_prompt=stored.challenge_prompt,
            reflect_prompt=stored.reflect_prompt,
            assess_question=stored_aq,
            created_at=datetime.now(timezone.utc),
        )
        db.add(served)
        await db.commit()
        await db.refresh(served)

        return GeneratedSession(
            warmup_prompt=stored.warmup_prompt,
            explore_content=stored.explore_content,
            challenge_prompt=stored.challenge_prompt,
            reflect_prompt=stored.reflect_prompt,
            assess_question=stored_aq,
            title=stored.title or f"The Art of {art.name}",
            art_name=art.name,
            art_slug=art.slug,
            art_id=art.id,
            skill_id=reuse_skill_id,
            session_id=served.id,
        )

    # ── Generate fresh content via Claude ────────────────────
    interests_line = ""
    if req.learner_interests:
        interests_line = f"\nThe learner's known interests include: {req.learner_interests}. Weave these in where natural."

    skill_line = ""
    if skill_name:
        skill_line = f"\nThe primary skill being developed is: {skill_name}."

    # ── Domain line: situates the session in the skill's academic/practical domain ──
    # learning_domain is a rich string (e.g. "Physiology", "Visual Art & Expression")
    # skill_type is a Bloom-style flag: cognitive | affective | psychomotor (may be combined)
    DOMAIN_GUIDANCE = {
        "cognitive":             "Engage the learner's reasoning, analysis, and understanding. Build conceptual clarity through comparison, questioning, and structured inquiry.",
        "affective":             "Engage the learner's emotions, values, and relational awareness. Surface inner experience, perspective-taking, and what matters to them personally.",
        "psychomotor":           "Ground the session in the body — physical sensation, movement, coordination, and hands-on practice. Theory should serve the doing, not replace it.",
        "cognitive,affective":   "Engage both intellectual understanding and emotional resonance. Help the learner think clearly about something they also feel deeply.",
        "affective,psychomotor": "Connect inner emotional experience with physical expression — how the body carries feeling, and how movement shapes mood and meaning.",
        "cognitive,psychomotor": "Link conceptual understanding with skilled physical action — the knowledge that only becomes real when practiced in the body.",
    }
    domain_line = ""
    if skill_domain or skill_type:
        domain_parts = []
        if skill_domain:
            domain_parts.append(f'"{skill_domain}"')
        if skill_type:
            domain_parts.append(f"({skill_type})")
        guidance = DOMAIN_GUIDANCE.get(skill_type or "", "")
        guidance_str = f" {guidance}" if guidance else ""
        domain_line = (
            f"\nThe learner approaches this session from a background in {' '.join(domain_parts)}.{guidance_str} "
            f"Let this inform their starting point and comfort zone — "
            f"but follow the art's own frame for direction and examples, never reducing the session to domain content."
        )

    # Language instruction — added before prompt so Claude sees it first
    lang_names = {
        'fr': 'French (français)',
        'es': 'Spanish (español)',
        'ar': 'Arabic (العربية)',
        'vi': 'Vietnamese (tiếng Việt)',
        'zh': 'Mandarin Chinese (中文)',
    }
    lang_instruction = ""
    if req.language and req.language != 'en':
        lang_name = lang_names.get(req.language, req.language)
        lang_instruction = (
            f"\n\nCRITICAL LANGUAGE REQUIREMENT: Generate ALL session content in {lang_name}. "
            f"This means the title, warmup, explore, challenge, reflect, assess_question, "
            f"and every single assess_option must be written in {lang_name}. "
            f"Do not mix languages. Do not include any English except proper nouns."
        )

    # Phase-specific language and pedagogy guidance
    phase_guides = {
        "nascent": (
            "CRITICAL: The learner is an ADULT caring for a newborn or infant aged 0–2. "
            "This session is FOR THE PARENT OR CAREGIVER, not written for the baby. "
            "The adult is navigating sleep deprivation, identity upheaval, relational strain, and the overwhelming "
            "newness of a tiny dependent life. They may have 10 minutes of fractured attention. "
            "Language: warm, honest, non-performative — never cheerful in a hollow way. "
            "Acknowledge the exhaustion and the wonder as inseparable. "
            "Frame skill practice around attunement: reading the infant's cues, co-regulation, "
            "the parent's own nervous system, and the slow rebuilding of self amid caregiving. "
            "The warmup should invite the adult to pause and notice something about this moment — "
            "their body, their breath, the weight of the baby, the sound in the room. "
            "The challenge should be a micro-practice: brief, doable in fragments, requiring no materials — "
            "a 60-second body scan, a whispered intention, a single observation recorded, a small act of self-kindness. "
            "The reflection should open toward the parent's inner experience — not infant-care technique. "
            "The assess question should be about self-awareness, attunement, or the parent's emotional landscape — "
            "not infant development milestones or pediatric theory."
        ),
        "prenascent": (
            "CRITICAL: The learner is an ADULT who is pregnant or expecting a child. "
            "This session is FOR THE EXPECTING PARENT, not for an infant or toddler. "
            "Do NOT write about playing with babies, sensory infant activities, or caregiver-infant interactions. "
            "The learner is a thinking, feeling adult in a major life transition. "
            "Frame skill practice as quiet inner preparation — emotional, relational, and practical. "
            "Honour the enormity of the transition without dramatising it. "
            "Language: warm, grounding, and unhurried — no urgency or performance pressure. "
            "Connect to the adult's own body, sleep, overwhelm, identity shift from individual to parent, and partnership. "
            "The warmup should invite the adult to gently notice something about themselves — their body, their fears, their hopes, their relationship. "
            "The challenge should be a reflective adult practice: a journal entry, a conversation with a partner, a quiet observation, a personal decision. "
            "The reflection should open into questions about the adult's own readiness, values, and vision of parenthood. "
            "The assess question should test the adult's self-understanding or emotional literacy — grounded in lived experience, not infant-care theory."
        ),
        "child": (
            "The learner is a child, ages 3–11. Default your language and complexity to a curious 8–10 year old "
            "— younger children will follow along, and older ones won't feel talked down to. "
            "Language: warm, concrete, and playful. Short sentences. Ground every idea in something the child "
            "can see, touch, taste, hear, or do right now — never abstract theory or adult concerns. "
            "Use analogies from animals, games, school, family, and nature. Never use jargon. "
            "WARMUP: Must be 2–3 sentences. Ask the child to notice or remember something specific and sensory "
            "— a smell, a sound, a texture, a memory of doing something with their hands. "
            "CHALLENGE: This is the most important rule — DO NOT default to 'draw a picture'. "
            "Rotate through: doing a real experiment (mixing, growing, building, measuring), "
            "writing or telling a short story, making something physical, playing a simple game with rules, "
            "going outside to observe and record, or interviewing a family member. "
            "Drawing is allowed occasionally but must not be the default. The challenge must feel like play, "
            "never homework. It should be completable in 10–20 minutes with things found at home. "
            "REFLECT: Ask one question the child might lie awake wondering about — genuine curiosity, "
            "not a consequence question ('what would happen if'). Aim for something that opens the world: "
            "'Why do you think...', 'Have you ever noticed...', 'What does it feel like when...'. "
            "ASSESS: Simple enough for a curious 8–10 year old without adult help. "
            "Everyday words, relatable scenarios, no technical terms. Options must be short and clearly different."
        ),
        "adolescent": (
            "Language: direct, honest, and peer-respecting — never condescending. "
            "Connect to identity, social belonging, fairness, and real-world stakes. "
            "The challenge should feel worth doing because it matters, not because it was assigned. "
            "The reflection should invite genuine self-inquiry, not performative answers. "
            "Assess options can handle moderate complexity but stay concrete and grounded in lived experience."
        ),
        "adult": (
            "Language: warm, curious, and non-judgmental. Treat the learner as a capable, thoughtful adult. "
            "Connect concepts to work, relationships, creative practice, and personal meaning. "
            "The challenge should produce something immediately useful, beautiful, or worth sharing."
        ),
        "elder": (
            "Language: respectful, reflective, and wisdom-honoring. Acknowledge that this learner has lived. "
            "Connect to legacy, community contribution, and accumulated insight. "
            "Avoid tech-heavy or pop-culture examples. "
            "The challenge should connect learning to passing wisdom forward or deepening an existing practice. "
            "Assess options should honor depth of experience rather than testing rote recall."
        ),
    }
    phase_guidance = phase_guides.get(phase_slug, phase_guides["adult"])

    # ── Contextual lens: frame each art in its own domain ──────────────
    # Source of truth: "To Be Human" by Charbel Haddad (Feb 2026).
    # Each art has a precise definition from the document. The generator
    # must enter through that definition, not collapse everything into
    # the permaculture/land/ecology frame that dominated the seed content.
    # Note: permaculture principles legitimately appear in Build (bioconstruction),
    # Grow (regenerative agriculture), Consume (water/resource/energy management),
    # and Live (footprint/waste) — but NOT in Move, Feel, Listen, Give, etc.
    ART_LENS = {
        # ── Being: developing the self through inward awareness ──
        "move":      ("inner-connectedness and physical growth — embodied movement in all its forms: "
                      "walking, breath work, tai chi, yoga, dance, sport, swimming, daily physical "
                      "labour, working the land, helping a neighbour; movement as thinking, as "
                      "regulation, as presence; the body as the first home"),
        "eat":       ("outer-connectedness, microbiome and bodily nourishment — holistic eating "
                      "from garden to table, food as relationship with living systems, urban and "
                      "vertical growing, fermentation, food culture, the gut-brain connection, "
                      "mindful consumption, traditional food knowledge"),
        "feel":      ("inward awareness and personal/emotional growth — identifying and mediating "
                      "bodily sensations, emotional literacy, naming feelings, Erikson's psychosocial "
                      "stages, the nervous system, grief and joy as equally valid, self-compassion, "
                      "somatic experiencing, the difference between reaction and response"),
        "notice":    ("outward-awareness-openness — childlike perception free of prejudice and "
                      "preconceived notions; noticing textures, colours, animals, moods, patterns "
                      "in self and society; curiosity as play; contradiction and paradox; "
                      "social fields; what is fading, arising, enduring; personal journey of "
                      "exploration and discovery without judgement"),
        "express":   ("inward-outward clarity, creative growth, arts, self-determination — "
                      "self-expression in solitude, with others, and with land/space/field; "
                      "journaling, voice notes, self-inquiry; breathwork, movement, physical "
                      "presence; structured conversation, mirroring, council circle; drawing, "
                      "collage, music, improvisation; time in nature, wandering, pilgrimage; "
                      "finding and using one's voice"),
        # ── Becoming: developing the self through outward awareness ──
        "live":      ("personal needs and rights, civil duties, consumption, footprint and "
                      "waste byproducts — living lightly and intentionally; understanding one's "
                      "ecological and civic footprint; circular economies; waste repurposing; "
                      "resource awareness; the rights and responsibilities of being a citizen "
                      "of both a community and a planet"),
        "listen":    ("empathy, civil and political discourse, understanding — deep listening "
                      "as a practice; audio diary; active listening exchange; listening to "
                      "soundscapes; the difference between hearing and listening; listening in "
                      "conflict, in friendship, in public life; Vinh Giang on presence and "
                      "clarity; Oscar Trimboli on listening as gift"),
        "give":      ("compassion, care, kindness, scaffolding, selflessness — the practice "
                      "of giving without expectation; generosity as a skill; mentoring and "
                      "scaffolding others; community contribution; the MKO who loves the learner; "
                      "service as meaning-making"),
        "receive":   ("acceptance, humility, equity — the art of receiving gracefully; "
                      "asking for help; acknowledging others' gifts; equity as mutual recognition; "
                      "the relationship between giving and receiving; interdependence as strength"),
        "collaborate": ("shared vision, mission and values — universal inclusivity, cherished "
                        "diversity, greater good valuing every unique member, synergy; "
                        "co-creation, conflict resolution, trust, shared decision-making; "
                        "team dynamics; the distinction between cooperation and collaboration; "
                        "community organising; supercollaboration"),
        # ── Connecting: developing together with our environments ──
        "understand": ("elements, fractals, class-category, first principles, sciences, theory "
                       "of knowledge — how do we know what we know; epistemology as lived "
                       "practice; systems thinking; pattern recognition; scientific method "
                       "as curiosity tool; chemistry, physics, biology, mathematics as lenses "
                       "on the world; sense-making in complexity"),
        "respect":   ("the golden rule extended to all living things — treating all things "
                      "the way we wish to be treated; mindful pragmatic utilitarianism; "
                      "respect for biodiversity, other species, elders, children, strangers; "
                      "boundaries and consent; the ethics of care; anti-bullying as respect "
                      "in practice"),
        "build":     ("bioconstruction, green architecture and design, accessibility — "
                      "designing and constructing shelter, tools, infrastructure with and "
                      "from the land; natural building techniques (cob, rammed earth, bamboo, "
                      "straw bale); permaculture design principles as they apply to structure; "
                      "accessible and inclusive design; the build as a community act; "
                      "proof of concept to delivery and back to drawing board"),
        "grow":      ("regenerative agriculture, harvesting, conserving — working with living "
                      "systems; permaculture ethics and principles; soil health, composting, "
                      "seed saving; agroforestry, aquaculture, hydroponics, chinampas, "
                      "hugelkultur; seasonal rhythms; the do-nothing farming approach; "
                      "tending to plant and animal needs; food forest design"),
        "consume":   ("water and resource management, energy creation and distribution — "
                      "circular economies; waste as resource; water harvesting and filtration; "
                      "renewable energy systems; reducing footprint; repair culture; "
                      "the politics of consumption; local vs global supply chains; "
                      "permaculture's waste-is-a-resource ethic applied to energy and materials"),
    }
    art_lens = ART_LENS.get(req.art_slug, "the full range of human experience relevant to this art")
    lens_line = (
        f"\nCONTEXTUAL FRAME — this art is defined as: {art_lens}. "
        f"Ground every example, metaphor, and challenge in THIS domain. "
        f"Permaculture principles may appear where the art explicitly includes them "
        f"(build, grow, consume, live, eat) — but must NOT be the default frame for "
        f"arts like move, feel, notice, listen, give, receive, understand, respect, "
        f"express, or collaborate."
    )

    prompt = f"""You are the learning engine for "Surfing the Frequencies" — a free, lifelong learning platform built on the philosophy of "To Be Human" by Charbel Haddad.

The platform draws on these works and thinkers (let their ideas breathe naturally into sessions — never cite by name in learner-facing content):

Alternative education thinkers: Maria Montessori, Rudolf Steiner (Waldorf), John Dewey (experiential reflection), Paulo Freire (democracy begins in the classroom through dialogue; the word — communicating, expressing, listening — as the path to freedom; learning as a dialogic act between equals, never banking education), Célestin Freinet (cooperative work), A.S. Neill (Summerhill), Loris Malaguzzi (Reggio Emilia), Carl Rogers (student-centred learning), Ken Robinson (authentic curriculum), John Taylor Gatto (homeschooling), Yaacov Hecht (democratic education/IDEC), David Sobel (forest school).

Developmental psychology: Jean Piaget, Lev Vygotsky, Erik Erikson, Friedrich Fröbel, Lawrence Kohlberg, Abraham Maslow, Jerome Bruner, Emmi Pikler, Margaret Mead, Howard Gardner, Daniel Goleman.

Books: Pedagogy of the Oppressed (Freire), Mind in Society (Vygotsky), The Absorbent Mind (Montessori), Democracy and Education (Dewey), Summerhill (Neill), Freedom to Learn (Rogers), Frames of Mind (Gardner), Emotional Intelligence (Goleman), Beyond Ecophobia (Sobel), Productive Failure (Kapur), Peak (Ericsson & Pool), Uncommon Sense Teaching / Learn Like a Pro (Oakley et al.), The Developing Mind (Siegel), Self-Compassion (Neff), Mastery / The Education of Man (Fröbel), The Psychology of the Child (Piaget), Culture and Commitment (Mead), Motivation and Personality (Maslow), The Centenary of Loris Malaguzzi (Reggio Children Collective), Micromastery (Greene / Twigger), Beginners (Vanderbilt), Conscious (Harris), The Art of Logic (Cheng), Thinking 101 (Ahn), The Beginning of Infinity (Deutsch), Ethics of Ambiguity (de Beauvoir), Dumbing Us Down (Gatto), The Hundred Languages of Children (Malaguzzi), The Pikler Collection (Pikler), Democratic Education (Hecht), Everything is Obvious (Watts), Artificial Intelligence for Learning (Clark), Shared Wisdom (Pentland), Shape (Ellenberg), How to Raise Successful People (Wojcicki), Adventures in Human Being, Wisdom Takes Work (Holiday), A Brief History of Thought (Ferry), The Art of Insubordination (Kashdan), Presence (Cuddy), Brain Wash (Perlmutter et al.), Win Every Argument (Hasan), Breath (Nestor), Awaken Your Genius (Varol), The Genius of Empathy (Orloff), How to Listen (Trimboli), Principles / How Countries Go Broke (Dalio), Uncompete (Malhotra), Aware (Csorba), The Shape of Wonder (Lightman & Rees), When AI Tutors Fake Critical Thinking (Purdy & Cook), Process! (Paton & Gonzalez), Salt (Kurlansky), Junglekeeper (Rosolie), Every Living Thing (Roberts), The Story of Stories (Ashton), The Compass Within (Glazer), Robin Hood Math (Giansiracusa). Communication teaching by Vinh Giang (presence, clarity, self-expression).

Core philosophy (from "To Be Human" by Charbel Haddad):
- Every human has the right to tools that develop their potential as a healthy, independent, free-thinking, self-aware, self-reliant, self-regulating, intrinsically motivated, reflective, environmentally-aware, and collaborative unique individual — capable of expressing themselves creatively, defining their own meanings, visions, and missions, and leading with love, respect, compassion, confidence and courage
- Learning should be enjoyable even when it demands hard work; a little struggle is fun, especially when those around you assist and support
- The 15 Arts span three domains: Being (inward awareness) · Becoming (outward awareness) · Connecting (with environments) — these are fractal: every age can practice every art, at different depth
- Assessment is formative, not competitive — Developing, Proficient, Master (never shame, never ranking)
- The MKO (More Knowledgeable Other) guides without dominating — a slightly-more-knowledgeable-other-but-not-always; a fellow learner, not an authority
- Errors are the learning path, not failures to be ashamed of; the challenge is travelled together
- Intrinsic motivation over extrinsic: curiosity, ambition and admiration — not envy, jealousy or greed
- Self-reliance and community interdependence are inseparable: individual empowerment enriches the collective
- Learning domains (cognitive · affective · psychomotor) and arts intersect — sessions may develop any combination
- The platform draws on the LECKO framework: each session is a chunked learning experience that can be assessed, mapped to community needs, and justified by evidence
{continuity_block}
Generate a complete 5-phase learning session for the following context:

ART: The art of {art.name} — {art.tagline}
ART DESCRIPTION: {art.description or art.tagline}
DEVELOPMENT PHASE: {phase_name} (ages {age_range})
{skill_line}{domain_line}{interests_line}{lens_line}

PHASE-SPECIFIC GUIDANCE — this is critical, apply it to every part of the session:
{phase_guidance}

Session design rules:
- Enter through the learner's existing experience; exit into the target art
- Use real-world, grounded challenges — never abstract theory
- Follow the universal learning cycle: observe → connect → act → reflect (this applies to all human arts, not any single domain)
- The challenge must produce something real: a written piece, a design, a decision, a practice
- The reflection must open rather than close — genuine questions, not leading ones
- The assess question must test the core concept of THIS session, not generic trivia
- CRITICAL: The assess question and all 4 options must be about the art being taught ({art.name}). They must NOT reference gardening, soil, seeds, composting, permaculture, or any ecological/land practice unless the art slug is "grow". Violating this rule means the session has failed.

Return ONLY a valid JSON object with exactly these keys:
{{
  "title": "A poetic session title (max 8 words)",
  "warmup": "2-4 sentences opening the learner's attention and connecting to their existing experience. Ask them to notice something.",
  "explore": "3-5 sentences explaining the core concept in a fresh, concrete, surprising way. Include one vivid analogy or example.",
  "challenge": "3-5 sentences describing exactly what the learner will create or do. Be specific. No single right answer.",
  "reflect": "1-2 open questions inviting genuine introspection. Connect the session to the learner's life.",
  "assess_question": "A single clear question testing understanding of the core concept explored in THIS session",
  "assess_options": ["option A", "option B", "option C", "option D"],
  "assess_correct": 0
}}

The assess_correct field is the 0-based index of the correct answer in assess_options.
Return only the JSON. No preamble, no explanation, no markdown code blocks.{lang_instruction}"""

    # ── Provider chain: Groq → Ollama → fail ────────────────
    # Decision 2026-05-31: Anthropic removed. Groq free tier is primary.
    # Ollama reactivates automatically if reinstalled (see MAINTENANCE.md).
    # Circuit breaker (added 2026-07-01):
    #   - config errors (HTTPException from Groq) are NOT counted -- they are
    #     caller-actionable, not transient, and would mask the real problem.
    #   - any other failure (network, timeout, parse) is counted.
    #   - on the first 1-2 failures, we return 503 to the client (so they
    #     know to back off and retry) and DO NOT fall through to a quiet
    #     library serve.
    #   - on the 3rd consecutive failure the route-level pre-check above
    #     will engage library mode for 10 minutes.
    try:
        from routes.groq_generate import generate_with_groq
        ai_t0 = time.monotonic()
        data, ai_model = await generate_with_groq(prompt)
        ai_latency_ms = int((time.monotonic() - ai_t0) * 1000)
        session_breaker.record_success()
    except HTTPException:
        # Config error (missing key, rate-limited) -- surface directly, do
        # not let the breaker hide it.
        raise
    except Exception as groq_err:
        # Groq failed (network, timeout, parse) -- try local Ollama
        try:
            from routes.ollama_generate import generate_with_ollama
            ai_t0 = time.monotonic()
            data, ai_model = await generate_with_ollama(prompt)
            ai_latency_ms = int((time.monotonic() - ai_t0) * 1000)
            session_breaker.record_success()
        except Exception as ollama_err:
            # Both providers failed this round. Record it; the next request
            # will see the counter and either return 503 (if still under
            # threshold) or flip into library mode (once threshold is hit).
            session_breaker.record_failure(
                f"groq: {str(groq_err)[:80]} | ollama: {str(ollama_err)[:80]}"
            )
            raise HTTPException(
                503,
                f"All AI providers failed. "
                f"Groq: {str(groq_err)[:120]}. "
                f"Ollama: {str(ollama_err)[:120]}. "
                f"(Consecutive failures: {session_breaker.consecutive_failures})"
            )

    # ── Validate required fields ──────────────────────────────
    required = ["title","warmup","explore","challenge","reflect",
                "assess_question","assess_options","assess_correct"]
    for field in required:
        if field not in data:
            raise HTTPException(500, f"AI response missing field: {field}")

    # FIX 2 (option B bias): shuffle options so the correct answer isn't
    # always at index 1 (LLMs strongly favour position B).
    options      = list(data["assess_options"])
    correct_text = options[int(data["assess_correct"])]
    random.shuffle(options)

    assess_q = {
        "question":      data["assess_question"],
        "options":       options,
        "correct_index": options.index(correct_text),
    }

    # ── Store in DB immediately ───────────────────────────────
    # Find the first skill for this art to satisfy the FK constraint
    # FIX: removed inline "from models import ArtsSkills" — it's now at the top.
    skill_q2 = await db.execute(
        select(ArtsSkills).where(ArtsSkills.art_id == art.id).limit(1)
    )
    arts_skill = skill_q2.scalar_one_or_none()
    fallback_skill_id = req.skill_id or (arts_skill.skill_id if arts_skill else 1)

    new_session = Session(
        learner_id=learner.id,
        art_id=art.id,
        primary_skill_id=fallback_skill_id,
        title=data["title"],
        recommended_by="engine",
        # AI-call metadata (2026-07-07): which model answered, how long it took.
        model=ai_model,
        latency_ms=ai_latency_ms,
        status="scheduled",
        warmup_prompt=data["warmup"],
        explore_content=data["explore"],
        challenge_prompt=data["challenge"],
        reflect_prompt=data["reflect"],
        assess_question=assess_q,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return GeneratedSession(
        warmup_prompt=data["warmup"],
        explore_content=data["explore"],
        challenge_prompt=data["challenge"],
        reflect_prompt=data["reflect"],
        assess_question=assess_q,
        title=data["title"],
        art_name=art.name,
        art_slug=art.slug,
        art_id=art.id,
        skill_id=fallback_skill_id,
        session_id=new_session.id,
    )


# ============================================================
# POST /api/generate/scaffold
# Socratic companion — one reply per call, stateless on server.
# The full message history is sent by the client each time.
# ============================================================

class ScaffoldMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str

class ScaffoldContext(BaseModel):
    art_name:        str | None = None
    art_slug:        str | None = None
    skill_name:      str | None = None
    learning_domain: str | None = None   # e.g. "Physiology", "Visual Art & Expression"
    skill_type:      str | None = None   # "cognitive" | "affective" | "psychomotor" | combined
    phase_label:     str | None = None   # "Mouseion" | "Challenge" | "Reflect" | "Portfolio"
    challenge_text:  str | None = None   # learner's challenge response so far
    learner_name:    str | None = None
    learner_profile: str | None = None   # accumulated life-CV
    mouseion_intent: str | None = None   # free-text from Mouseion textarea
    avatar_stage:    str | None = None   # "Seed"|"Sprout"|"Sapling"|"Grove"|"Forest"|"Ecosystem"
    bioregion_name:  str | None = None   # matched bioregion e.g. "Red River Delta"

class ScaffoldRequest(BaseModel):
    messages: list[ScaffoldMessage]
    context:  ScaffoldContext

class ScaffoldResponse(BaseModel):
    reply: str


# ============================================================
# Library fallback helper (used by the /session circuit breaker)
# Spec (2026-06-28): when library mode is active, serve the best-matching
# stored session for the requested (art, phase, language, skill) tuple,
# excluding sessions the learner has already seen. Returns None if no
# suitable session exists, which the caller should treat as 503.
#
# 2026-07-01 (this session): the helper does the simple version -- match on
# (art, phase, language), filter seen prompts, pick random from the top 30.
# Tomorrow's work will refine this with the full (art_id, primary_skill_id,
# dev_phase_id, language) tuple + already-seen exclusion.
# ============================================================
async def _serve_from_library(
    db: AsyncSession,
    learner: Learner,
    art: Arts,
    phase: DevPhase | None,
    phase_id: int | None,
    phase_slug: str,
    phase_name: str,
    req: GenerateRequest,
) -> GeneratedSession | None:
    # Candidate pool: stored sessions for this art with content.
    existing_q = await db.execute(
        select(Session)
        .where(
            Session.art_id == art.id,
            Session.warmup_prompt != None,
            Session.status.in_(["completed", "scheduled"]),
        )
        .order_by(Session.created_at.desc())
        .limit(200)
    )
    all_stored = existing_q.scalars().all()

    # Prefer phase-matched; fall back to untagged/legacy.
    if phase_id:
        existing = [s for s in all_stored
                    if getattr(s, 'dev_phase_id', None) in (None, phase_id)]
        if not existing:
            existing = [s for s in all_stored
                        if getattr(s, 'dev_phase_id', None) is None]
    else:
        existing = all_stored

    if not existing:
        return None

    # Exclude sessions this learner has already been served recently.
    seen_q = await db.execute(
        select(Session.warmup_prompt)
        .where(Session.learner_id == learner.id, Session.art_id == art.id)
        .order_by(Session.created_at.desc())
        .limit(30)
    )
    recently_seen = {row[0] for row in seen_q.all()}

    reusable = [s for s in existing if s.warmup_prompt not in recently_seen]
    if not reusable:
        return None

    stored = random.choice(reusable[:30])

    # Resolve a skill_id (FK requirement on the new Session row).
    skill_q2 = await db.execute(
        select(ArtsSkills).where(ArtsSkills.art_id == art.id).limit(1)
    )
    reuse_arts_skill = skill_q2.scalar_one_or_none()
    reuse_skill_id   = reuse_arts_skill.skill_id if reuse_arts_skill else 1

    # Shuffle the stored assess options so the correct answer isn't always
    # at the same index.
    stored_aq    = dict(stored.assess_question)
    opts         = list(stored_aq["options"])
    correct_text = opts[stored_aq["correct_index"]]
    random.shuffle(opts)
    stored_aq["options"]       = opts
    stored_aq["correct_index"] = opts.index(correct_text)

    # Persist a Session row for this learner so /complete has a real id
    # and the session appears in their history.
    served = Session(
        learner_id=learner.id,
        art_id=art.id,
        primary_skill_id=reuse_skill_id,
        title=stored.title or f"The Art of {art.name}",
        recommended_by="library",
        # AI-call metadata (2026-07-07): library-served sessions get model="library"
        # and latency_ms=0 since no AI call was made. This lets the admin
        # session library distinguish AI-served from library-served rows at a glance.
        model="library",
        latency_ms=0,
        status="scheduled",
        warmup_prompt=stored.warmup_prompt,
        explore_content=stored.explore_content,
        challenge_prompt=stored.challenge_prompt,
        reflect_prompt=stored.reflect_prompt,
        assess_question=stored_aq,
        created_at=datetime.now(timezone.utc),
    )
    db.add(served)
    await db.commit()
    await db.refresh(served)

    return GeneratedSession(
        warmup_prompt=stored.warmup_prompt,
        explore_content=stored.explore_content,
        challenge_prompt=stored.challenge_prompt,
        reflect_prompt=stored.reflect_prompt,
        assess_question=stored_aq,
        title=stored.title or f"The Art of {art.name}",
        art_name=art.name,
        art_slug=art.slug,
        art_id=art.id,
        skill_id=reuse_skill_id,
        session_id=served.id,
    )


@router.get("/breaker-status")
async def get_breaker_status():
    """Diagnostic endpoint for the /session circuit breaker state."""
    return session_breaker.status()


@router.post("/scaffold", response_model=ScaffoldResponse)
async def scaffold_companion(
    req: ScaffoldRequest,
    learner: Learner = Depends(get_current_learner),
):
    # ── Build system prompt ───────────────────────────────────
    ctx = req.context
    art_line      = f"Art being explored: {ctx.art_name}" if ctx.art_name else ""
    skill_line    = f"Skill focus: {ctx.skill_name}" if ctx.skill_name else ""
    # Build domain line for scaffold — same intent as session generation
    if ctx.learning_domain or ctx.skill_type:
        _d_parts = []
        if ctx.learning_domain:
            _d_parts.append(f'"{ctx.learning_domain}"')
        if ctx.skill_type:
            _d_parts.append(f"({ctx.skill_type})")
        domain_line = f"The learner brings a background in {' '.join(_d_parts)} — let this inform their starting point, always following the art's own frame."
    else:
        domain_line = ""
    phase_line    = f"Current phase: {ctx.phase_label}" if ctx.phase_label else ""
    name_line     = f"Learner's name: {ctx.learner_name}" if ctx.learner_name else ""
    intent_line   = f"What the learner wrote they want to explore: \"{ctx.mouseion_intent}\"" if ctx.mouseion_intent else ""
    profile_line  = f"\nLEARNER PROFILE (accumulated from past conversations):\n{ctx.learner_profile}" if ctx.learner_profile else ""
    work_line     = f"\nThe learner's challenge response so far:\n\"{ctx.challenge_text}\"" if ctx.challenge_text else ""
    avatar_line   = f"Learner's avatar stage: {ctx.avatar_stage} — a point on the path Seed→Sprout→Sapling→Grove→Forest→Ecosystem, reflecting their breadth across the 15 Arts." if ctx.avatar_stage else ""
    bioregion_line = f"Learner's bioregion: {ctx.bioregion_name}." if ctx.bioregion_name else ""

    if ctx.phase_label == "Portfolio":
        # ── Portfolio companion — reflective mirror, speaks directly from the life-CV ──
        profile_block = ctx.learner_profile.strip() if ctx.learner_profile else "(No profile accumulated yet — the learner is just starting out.)"
        name_str = ctx.learner_name or "the learner"
        avatar_str = f" They are at the {ctx.avatar_stage} stage of their journey across the 15 Arts." if ctx.avatar_stage else ""
        bioregion_str = f" They are rooted in the {ctx.bioregion_name} bioregion." if ctx.bioregion_name else ""
        system_prompt = f"""You are the Portfolio companion inside "Surfing the Frequencies" — a lifelong learning platform built around 15 Arts of Living: Being (Move · Eat · Feel · Notice · Express), Becoming (Live · Listen · Give · Receive · Collaborate), Connecting (Understand · Respect · Build · Grow · Consume).

Your role here is different from elsewhere in the platform. You are not a Socratic guide — you are a reflective mirror. The learner has come to their Portfolio to understand themselves. You speak directly, warmly, and honestly. You answer questions. You help them see patterns they might have missed. You affirm what is real and gently name what is unresolved.

You have been given {name_str}'s accumulated life profile — everything the platform has learned about them through their learning conversations.{avatar_str}{bioregion_str}

THEIR PROFILE:
{profile_block}

YOUR ROLE:
- Speak directly and warmly — this is not a place for Socratic questioning
- Answer questions about what the profile reveals: patterns, strengths, blind spots, recurring themes
- Help the learner articulate what they already sense about themselves
- If the profile is thin or empty, be honest: "Your story is just beginning here — the more you explore, the more I'll have to reflect back to you."
- Never invent things not grounded in the profile
- Never be clinical or list-heavy — speak as a thoughtful companion who has read their story carefully
- Short-to-medium responses: 3–5 sentences, conversational, no bullet points
- Do not mention the platform mechanics (XP, levels, sessions) unless the learner brings them up

Respond only with your reply. No preamble, no meta-commentary."""

    else:
        # ── Default Socratic companion — for Mouseion, Challenge, Reflect ──
        system_prompt = f"""You are the Socratic companion inside "Surfing the Frequencies" — a free lifelong learning platform built on the philosophy of "To Be Human" by Charbel Haddad. The platform is built around 15 Arts of Living: Being (Move · Eat · Feel · Notice · Express), Becoming (Live · Listen · Give · Receive · Collaborate), Connecting (Understand · Respect · Build · Grow · Consume).

Your role is that of a More Knowledgeable Other (MKO) — not a teacher who delivers answers, but a companion who helps the learner find their own way through. You ask questions, not give answers. You surface what the learner already knows. You guide without leading. You are Socratic: you help the learner think, not think for them.

{name_line}
{art_line}
{skill_line}
{domain_line}
{phase_line}
{avatar_line}
{bioregion_line}
{intent_line}
{profile_line}
{work_line}

TONE AND STYLE:
- Warm, curious, never condescending
- Short responses: 2–4 sentences maximum, usually ending in one open question
- Never lecture. Never summarise the learner's own words back at them flatly.
- If the learner is in the Mouseion (free exploration), help them discover what they truly want to explore — their real curiosity beneath the surface question
- If the learner is in Challenge phase, help them go deeper into their own work — what did they notice? what surprised them? what would they change?
- If the learner is in Reflect phase, help them connect the session to their life — not the "lesson" but the living of it
- Never mention permaculture, ecology, or land unless the art slug is "grow" or "consume"
- Never say "great question" or hollow affirmations
- Draw on the full breadth of human knowledge — science, art, philosophy, daily life, community — wherever it serves the learner's curiosity
- The platform's philosophy: learning should feel like surfing, not drowning. You are the wave, not the shore.

Respond only with your reply to the learner. No preamble, no meta-commentary."""

    # ── Build message list for Groq ───────────────────────────
    groq_messages = [{"role": m.role, "content": m.content} for m in req.messages]

    # ── Call Groq directly (chat/completions) ─────────────────
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(503, "GROQ_API_KEY not configured")
    import httpx
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system_prompt}] + groq_messages,
        "max_tokens": 300,
        "temperature": 0.75,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json=payload,
            )
        resp.raise_for_status()
        reply_text = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise HTTPException(503, f"Scaffold companion unavailable: {str(e)[:120]}")

    return ScaffoldResponse(reply=reply_text)


# ============================================================
# POST /api/generate/profile-update
# Distils a sandbox conversation into the learner's life-CV.
# Fire-and-forget from client — returns quickly.
# ============================================================

class ProfileUpdateRequest(BaseModel):
    messages:        list[ScaffoldMessage]   # the sandbox conversation to distil
    existing_profile: str | None = None      # current learner_profile text
    bioregion_note:   str | None = None      # optional — direct bioregion line to upsert, no AI call needed


@router.post("/profile-update")
async def update_learner_profile(
    req: ProfileUpdateRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text as sql_text

    # ── Bioregion-only update — no AI call, direct upsert into profile ──
    if req.bioregion_note and (not req.messages or len(req.messages) < 2):
        existing = (req.existing_profile or "").strip()
        note_line = f"BIOREGION: {req.bioregion_note}"
        # Replace existing BIOREGION line if present, otherwise prepend
        import re
        if re.search(r'^BIOREGION:.*$', existing, re.MULTILINE):
            new_profile = re.sub(r'^BIOREGION:.*$', note_line, existing, flags=re.MULTILINE)
        else:
            new_profile = note_line + ("\n" + existing if existing and existing != "(no profile yet)" else "")
        new_profile = new_profile.strip()
        await db.execute(
            sql_text("UPDATE learners SET learner_profile = :profile WHERE id = :id"),
            {"profile": new_profile, "id": learner.id},
        )
        await db.commit()
        return {"status": "ok", "profile_length": len(new_profile)}

    if not req.messages or len(req.messages) < 2:
        return {"status": "skipped", "reason": "too few messages"}

    # Build conversation transcript for the AI
    transcript = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in req.messages
    )
    existing = req.existing_profile or "(no profile yet)"

    prompt = f"""You maintain a compact learner profile — a living 1–2 page "life CV" — for a learner on the Surfing the Frequencies platform. The profile captures who this person is as a learner and a human: their curiosities, interests, loves, fears, desires, recurring themes, what energises or drains them, how they think and express themselves.

EXISTING PROFILE:
{existing}

NEW CONVERSATION TO DISTIL:
{transcript}

Your task:
1. Read the new conversation carefully.
2. Extract any meaningful new signals: new interests mentioned, questions they asked, emotions surfaced, themes that recurred, ways they engaged, things they avoided or resisted.
3. Merge these signals into the existing profile — updating, enriching, or correcting it. Do not simply append; distil.
4. Keep the profile under 1500 characters total.
5. Format it as plain text with short labelled sections. Example structure (adapt as needed):

NAME / CONTEXT: [name, location, life phase if known]
CURIOSITIES: [what draws their attention, questions they keep returning to]
PRACTICES: [things they do, create, build, move through]
LOVES: [what lights them up]
FEARS / AVOIDS: [what they shy away from, what drains them]
DESIRES: [what they're working toward, what they want from learning]
RECURRING THEMES: [patterns across conversations]
TONE: [how they communicate — poetic, direct, playful, careful...]
RECENT THREADS: [last 2–3 topics/arts explored]

Return ONLY the updated profile text. No preamble, no explanation."""

    try:
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            return {"status": "error", "reason": "GROQ_API_KEY not configured"}
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            presp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 600,
                    "temperature": 0.4,
                },
            )
        presp.raise_for_status()
        new_profile = presp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return {"status": "error", "reason": str(e)[:120]}

    # ── Save to learners table ────────────────────────────────
    # Uses raw SQL update to avoid needing the full ORM model definition here.
    await db.execute(
        sql_text("UPDATE learners SET learner_profile = :profile WHERE id = :id"),
        {"profile": new_profile.strip(), "id": learner.id},
    )
    await db.commit()

    return {"status": "ok", "profile_length": len(new_profile.strip())}


# ============================================================
# POST /api/generate/guiding-star
# Distils the learner's life-CV into a single short motivation phrase
# ("Guiding Star") for display in the Where I Stand card.
# Fire-and-forget friendly — fast, cached by client.
# ============================================================

class GuidingStarRequest(BaseModel):
    learner_profile: str   # the current learner_profile text


class GuidingStarResponse(BaseModel):
    guiding_star: str      # e.g. "To understand before being understood"


@router.post("/guiding-star", response_model=GuidingStarResponse)
async def generate_guiding_star(
    req: GuidingStarRequest,
    learner: Learner = Depends(get_current_learner),
):
    if not req.learner_profile or len(req.learner_profile.strip()) < 20:
        raise HTTPException(400, "learner_profile too short to distil")

    prompt = f"""You read a learner's accumulated life profile from the "Surfing the Frequencies" platform — a lifelong learning platform built around 15 Arts of Living. From this profile, distil a single short phrase that captures the learner's deepest motivation or guiding orientation as a learner and a human.

Call it their "Guiding Star."

Rules:
- 4–9 words maximum
- Must feel like something the learner themselves would recognise and claim — not a description of them, but a phrase that could belong to them
- Poetic, grounded, and specific — not generic ("keep learning", "grow every day") but genuinely drawn from their profile
- No quotation marks, no labels, no preamble — return only the phrase itself
- Examples of the right register: "To understand before being understood" / "Finding stillness at the edge of things" / "Making meaning from what others pass over" / "To build what lasts with what is already here"

LEARNER PROFILE:
{req.learner_profile}

Return ONLY the guiding star phrase. Nothing else."""

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(503, "GROQ_API_KEY not configured")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 40,
                    "temperature": 0.7,
                },
            )
        resp.raise_for_status()
        star = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'").strip()
    except Exception as e:
        raise HTTPException(503, f"Guiding star generation failed: {str(e)[:120]}")

    return GuidingStarResponse(guiding_star=star)


@router.get("/library")
async def get_session_library(
    art_slug: str | None = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the stored session content library.
    Admin use — shows all generated sessions for a given art.
    """
    q = select(Session).where(Session.warmup_prompt != None)
    if art_slug:
        art_q = await db.execute(select(Arts).where(Arts.slug == art_slug))
        art = art_q.scalar_one_or_none()
        if art:
            q = q.where(Session.art_id == art.id)
    q = q.order_by(Session.created_at.desc()).limit(limit)
    result = await db.execute(q)
    sessions = result.scalars().all()
    return [
        {
            "id":    s.id,
            "title": s.title,
            "art_id": s.art_id,
            "warmup": s.warmup_prompt,
            "explore": s.explore_content,
            "challenge": s.challenge_prompt,
            "reflect": s.reflect_prompt,
            "assess": s.assess_question,
            "created_at": s.created_at,
        }
        for s in sessions
    ]
