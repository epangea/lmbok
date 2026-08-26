#!/usr/bin/env python3
# ============================================================
# FreqLearn — seed_sessions.py  (v3)
# Pre-generates session content for all 15 arts × 5 phases,
# storing everything in MariaDB so the platform runs at zero AI cost.
#
# P41 (2026-07-29): dropped the paid-Anthropic path (Anthropic was removed
# from the platform 2026-05-31 -- Groq/Ollama free tier only from then on,
# see BRIEFING) and stopped hardcoding the Groq model. Provider and model
# now come from platform_settings (ai_provider, ai_model_groq_large,
# ai_model_ollama_large) -- the same admin-editable settings the live app
# uses via ai_client.py. This script runs as a standalone subprocess with
# its own aiomysql connection rather than the app's SQLAlchemy session, so
# it can't literally import ai_client.ai_complete(), but it now reads the
# same settings and honours the same provider fallback logic by hand.
#
# Prerequisites:
#   - run: mysql -u freqlearn -p freqlearn < add_dev_phase_to_sessions.sql
#   - pip install aiomysql python-dotenv httpx --break-system-packages
#
# Run:
#   python3 seed_sessions.py                    # all arts, all phases, 2 per combo
#   python3 seed_sessions.py --phases child,adolescent --per-art 3
#   python3 seed_sessions.py --arts move,feel --dry-run
# ============================================================

import os, sys, json, asyncio, argparse, time, random
from pathlib import Path
import aiomysql
from dotenv import load_dotenv

# .env lives in the backend directory regardless of where this script is run from
_env_path = Path(__file__).parent.parent / ".env"          # backend/routes/ -> backend/.env
if not _env_path.exists():
    _env_path = Path(__file__).parent.parent.parent / "backend" / ".env"  # fallback: repo root layout
load_dotenv(dotenv_path=_env_path)

DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER", "freqlearn"),
    password=os.getenv("DB_PASSWORD", "changeme"),
    db=os.getenv("DB_NAME", "freqlearn"),
    charset="utf8mb4",
)

GROQ_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

# Emergency fallback only -- real values always come from platform_settings
# (ai_provider, ai_model_groq_large, ai_model_ollama_large), read once at
# startup in main(). Same defaults as ai_client.py.
_SETTINGS_DEFAULTS = {
    "ai_provider":         "groq",
    "ai_model_groq_large":   "openai/gpt-oss-120b",
    "ai_model_ollama_large": "llama3.1:8b",
}
_settings = dict(_SETTINGS_DEFAULTS)


async def _load_settings(conn) -> None:
    """Read the same admin-configurable AI settings the live app uses."""
    global _settings
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT key_name, value FROM platform_settings WHERE key_name IN "
            "('ai_provider', 'ai_model_groq_large', 'ai_model_ollama_large')"
        )
        rows = await cur.fetchall()
    out = dict(_SETTINGS_DEFAULTS)
    for k, v in rows:
        if v is not None and str(v).strip() != "":
            out[k] = str(v)
    _settings = out

# ── All 15 arts (gerund names match DB after migration) ──────
ARTS = [
    ("move",        "Moving",        "Inner-connectedness and physical growth",
     "Body awareness, coordination, dance, sport, instrument playing, breath"),
    ("eat",         "Eating",        "Outer-connectedness and bodily nourishment",
     "Food sovereignty, nutrition, microbiome, garden-to-table, seasonal eating"),
    ("feel",        "Feeling",       "Inward awareness and emotional growth",
     "Emotional literacy, self-awareness, regulation, empathy, resilience"),
    ("notice",      "Noticing",      "Outward awareness without judgement",
     "Curiosity, observation, presence, beginner's mind, childlike perception"),
    ("express",     "Expressing",    "Inward-outward clarity and creative growth",
     "Creativity, art, music, writing, storytelling, self-determination"),
    ("live",        "Living",        "Personal needs, rights and civil duties",
     "Financial literacy, time management, civic responsibility, consumption, footprint"),
    ("listen",      "Listening",     "Empathy, understanding and civil discourse",
     "Active listening, cultural competence, political dialogue, deep presence"),
    ("give",        "Giving",        "Compassion, care and selfless contribution",
     "Mentorship, caregiving, community service, generosity, teaching"),
    ("receive",     "Receiving",     "Acceptance, humility and equity",
     "Gratitude, feedback integration, humility, openness, letting go of pride"),
    ("collaborate", "Collaborating", "Shared vision and universal inclusivity",
     "Teamwork, conflict resolution, leadership, negotiation, co-creation"),
    ("understand",  "Understanding", "First principles, science and theory of knowledge",
     "Critical thinking, systems thinking, scientific method, philosophy, logic"),
    ("respect",     "Respecting",    "The golden rule extended to all living things",
     "Ethics, ecological awareness, nonviolence, extending moral circles"),
    ("build",       "Building",      "Designing and constructing things — at any scale, in any domain",
     "Construction and design thinking in its full breadth: shelter, furniture, tools, instruments, spacecraft, software systems, community spaces, infrastructure. Natural building (cob, bamboo, straw bale, rammed earth) is one valid context among many — as is mechanical engineering, electronics, instrument-making, urban design, or any act of bringing something into the world. Permaculture design principles apply where relevant but are not the default frame."),
    ("grow",        "Growing",       "Regenerative agriculture and food sovereignty",
     "Permaculture, agroforestry, composting, seed-saving, soil health"),
    ("consume",     "Consuming",     "Water, resource and energy stewardship",
     "Water management, energy literacy, circular economy, zero-waste systems"),
]

PHASES = [
    ("light",         "Light",         "expecting",
     "The learner is an adult who is pregnant or expecting a child (via any path to parenthood). "
     "This session is FOR THE EXPECTING PARENT, not for an infant or toddler. "
     "What's known: research on the transition to parenthood -- increasingly called \"matrescence\" for the "
     "birthing parent, with growing recognition that any primary caregiver's brain and identity reorganize "
     "through caregiving regardless of biological role -- describes this transition as developmentally "
     "comparable in magnitude to adolescence: significant neuroplasticity, identity reorganization, and "
     "relational change, though without adolescence's cultural scaffolding for support. "
     "Likely motivational terrain: autonomy may feel newly complicated as identity reorganizes around a role "
     "not yet begun; relatedness (to a partner, to the child-to-come, to one's own parents) and competence "
     "(\"will I be able to do this?\") both tend to be live and often anxious. "
     "Suggested register: warm, grounding, unhurried. This learner is a capable adult in transition, not a "
     "novice. Let the Art's own lens shape the actual content and format."),

    ("sandy-soil",    "Sandy Soil",    "0~2",
     "The learner is an adult caring for an infant aged 0~2. This session is FOR THE PARENT OR CAREGIVER, "
     "not written for the baby. "
     "What's known: attachment research (Bowlby, Ainsworth) and the co-regulation literature describe this "
     "period as one where the caregiver's own regulation and attunement shape the infant's developing sense "
     "of security, and where caregivers themselves are often depleted -- fragmented attention and disrupted "
     "sleep are the norm, not the exception. "
     "Likely motivational terrain: competence (am I doing this right?) and relatedness (to the infant, to a "
     "partner, to one's own support network) tend to dominate; autonomy may feel very reduced right now. "
     "Suggested register: warm and honest, never performatively cheerful. Whatever this looks like, it "
     "likely needs to survive being read in fragments. Let the Art's own lens shape the actual content and format."),

    ("moist-soil",    "Moist Soil",    "3~5",
     "The learner is a preschooler, ages 3~5. "
     "What's known: Piaget's preoperational stage (roughly 2-7, though cross-cultural research finds these "
     "boundaries shift with schooling access and culture) describes children at this age as thinking "
     "symbolically -- pretend play, drawing, and language all represent ideas -- but still reasoning from "
     "what they perceive rather than logically, and typically struggling to take another's perspective. "
     "Most children this age are pre- or early-literate. "
     "Likely motivational terrain: competence shows up as delight in doing something themselves, however "
     "small; relatedness to a caregiver reading or playing alongside them matters a great deal. "
     "Suggested register: concrete, sensory, likely caregiver-mediated given typical literacy at this age. "
     "Abstract or hypothetical framing is unlikely to land here regardless of the art. Let the Art's own lens shape the actual content and format."),

    ("humus-soil",    "Humus Soil",    "6~8",
     "The learner is a child, ages 6~8. "
     "What's known: this age sits at the boundary Piaget described between preoperational and "
     "concrete-operational thinking -- logical reasoning about concrete, tangible things is emerging, but "
     "abstract or hypothetical reasoning typically isn't yet reliable. Most children this age are becoming "
     "independent readers. "
     "Likely motivational terrain: competence and mastery become more central than at earlier ages -- this "
     "learner increasingly wants to do things well, not just explore; relatedness to peers begins to matter "
     "alongside caregivers. "
     "Suggested register: concrete and playful, grounded in things the child can see, touch, or do. Let the Art's own lens shape the actual content and format."),

    ("low-fire",      "Low Fire",      "9~11",
     "The learner is ages 9~11. "
     "What's known: puberty timing varies enormously at this age -- typical onset ranges from 8-12 in girls "
     "and 9-14 in boys, so some learners in this band are pre-pubertal and others are well into it. "
     "Cognitively, most are consolidating concrete-operational reasoning while executive function and "
     "impulse control continue developing gradually. "
     "Likely motivational terrain: autonomy begins mattering more than at earlier ages -- this is often the "
     "first age where working independently for a real stretch becomes possible; competence and relatedness "
     "to peers both remain central. "
     "Suggested register: respectful and clear, treating the learner as capable of real independence in "
     "doses, without assuming the identity questions or peer intensity that tend to arrive later. Let the Art's own lens shape the actual content and format."),

    ("medium-fire",   "Medium Fire",   "12~14",
     "The learner is an early teen, ages 12~14. "
     "What's known: developmental neuroscience describes this period as one of heightened sensitivity to "
     "social and identity-relevant information -- a capacity, not simply a vulnerability -- coinciding with "
     "identity formation becoming a central psychological task. "
     "Likely motivational terrain: relatedness (peer belonging, being seen accurately) and autonomy (having "
     "and defending one's own views) both tend to intensify here; competence still matters but is "
     "increasingly filtered through how it makes them look. "
     "Suggested register: direct and honest, never condescending -- but this age can swing between confident "
     "and self-conscious within a single session, so don't assume steadiness. Let the Art's own lens shape the actual content and format."),

    ("high-fire",     "High Fire",     "15~17",
     "The learner is a late teen, ages 15~17. "
     "What's known: the same heightened social-learning capacity from earlier adolescence continues here and, "
     "per current research, extends into the mid-20s rather than ending sharply at 18 -- there is no hard "
     "neurological cutoff at the adult boundary this platform draws for other reasons. "
     "Likely motivational terrain: autonomy tends to matter more here than at any earlier phase -- research "
     "links a felt sense of choice to deeper engagement specifically at this age; relatedness and competence "
     "remain live alongside it. "
     "Suggested register: direct and honest, treating the learner as very nearly an adult, because in most "
     "respects they are. Let the Art's own lens shape the actual content and format."),

    ("low-wind",      "Low Wind",      "18~22",
     "The learner is newly independent, ages 18~22. "
     "What's known: \"emerging adulthood\" research describes this period as one of identity exploration and "
     "instability across love, work, and worldview -- but the theory's own originator notes it's culturally "
     "constructed, drawn largely from American samples, and not claimed as universal. Treat it as one lens "
     "among others, not a settled fact about every learner in this band. "
     "Likely motivational terrain: autonomy and identity exploration tend to be central -- this is often a "
     "period with more freedom than structure; \"I don't know yet\" is common and not itself a problem to "
     "solve. "
     "Suggested register: warm and non-judgmental, comfortable with uncertainty rather than pushing toward "
     "premature resolution. Let the Art's own lens shape the actual content and format."),

    ("high-wind",     "High Wind",     "23~27",
     "The learner is building momentum, ages 23~27. "
     "What's known: still within the age range emerging-adulthood research covers, though the same research "
     "and its critics note wide individual and cultural variation in how quickly people move from "
     "exploration toward more settled commitments -- some at this age are still fully in exploration, others "
     "have already largely settled. "
     "Likely motivational terrain: competence tends to grow in weight relative to pure exploration -- early "
     "mastery in a domain becomes motivating in its own right; autonomy and relatedness (peer and partner "
     "relationships increasingly chosen rather than circumstantial) both remain active. "
     "Suggested register: warm and curious, respectful of developing competence without assuming full "
     "settledness. Let the Art's own lens shape the actual content and format."),

    ("water",         "Water",         "28~38",
     "The learner is an adult, ages 28~38. "
     "What's known: adult-learning research describes adult learners generally as self-directed, motivated "
     "by relevance and real-world application, and learning through integrating new material with lived "
     "experience -- a genuinely different starting point than pedagogy designed for children. "
     "Likely motivational terrain: competence and relatedness (to work, partnership, community, possibly "
     "parenting) tend to dominate, with autonomy expressed through wanting a say in how, not just what, is "
     "learned. "
     "Suggested register: warm, curious, and non-judgmental -- a capable adult with real stakes and limited "
     "spare time. Let the Art's own lens shape the actual content and format."),

    ("metal",         "Metal",         "39~59",
     "The learner is in the load-bearing years, ages 39~59. "
     "What's known: Erikson's generativity-vs-stagnation framing describes this period's central task as "
     "contributing something that outlasts the self -- and longitudinal research links higher midlife "
     "generativity to stronger cognitive functioning and lower depression decades later. Adult-learning "
     "research's emphasis on drawing from lived experience applies with particular force here, given the "
     "accumulated experience this learner likely has. "
     "Likely motivational terrain: relatedness through mentoring and contribution tends to matter more than "
     "at earlier adult phases; competence remains central, but often expressed as depth in an existing "
     "domain rather than breadth across new ones. "
     "Suggested register: warm, direct, and respectful of real expertise -- this learner may know more in "
     "some areas than the platform does. Let the Art's own lens shape the actual content and format."),

    ("stone",         "Stone",         "60~80",
     "The learner is ages 60~80. "
     "What's known: socioemotional selectivity theory describes a shift toward emotionally meaningful goals "
     "as time horizons narrow -- but the theory is explicit that this shift tracks perceived time horizon, "
     "not chronological age itself, and doesn't apply uniformly to everyone in a given age band. Research "
     "applying \"successful aging\" frameworks to this age range finds meaningful rates of continued high "
     "function and engagement -- this is not, on average, a winding-down phase. "
     "Likely motivational terrain: relatedness (particularly close, existing relationships) and "
     "meaning-making tend to carry more weight relative to novelty-seeking than at earlier phases -- but "
     "competence and genuine autonomy remain fully present and shouldn't be assumed away. "
     "Suggested register: respectful and wisdom-honoring, without assuming decline unless the learner has "
     "indicated it. Let the Art's own lens shape the actual content and format."),

    ("wood",          "Wood",          "81+",
     "The learner is ages 81+. "
     "What's known: this is the age range where the standard \"successful aging\" model becomes least "
     "representative on its own terms -- applying its strict physical-function criteria, essentially no "
     "centenarians and few octogenarians qualify, while subjective-wellbeing and engagement-based models find "
     "far higher rates of thriving in the same population. The research literature itself treats this as a "
     "sign the strict model under-represents this group, not that this group is uniformly declining. "
     "Socioemotional selectivity research also finds older adults often report better emotional well-being "
     "than younger adults, on average. "
     "Likely motivational terrain: highly individual at this age more than any other -- some learners here "
     "have real physical limitation, others remain remarkably active; assume neither without the learner's "
     "own signal. Relatedness and meaning-making are likely central; competence and autonomy should never be "
     "assumed absent. "
     "Suggested register: warm, dignified, and present-tense -- this learner is here now, not a memory of "
     "themselves. Favor depth and story over anything time-pressured, but without assuming physical "
     "limitation. Let the Art's own lens shape the actual content and format."),

]



def build_prompt(art_slug, art_name, art_tagline, art_context,
                 phase_slug, phase_name, age_range, phase_guidance,
                 session_num):
    return f"""You are the learning engine for "Surfing the Frequencies" — a free global platform \
helping every human develop their potential as a healthy, independent, free-thinking, self-aware, self-reliant, \
self-regulating, intrinsically motivated, reflective, environmentally-aware, and collaborative unique individual, \
capable of expressing themselves creatively, defining their own meanings, visions, and missions, and able to lead \
with love, respect, compassion, confidence and courage. Built by Charbel Haddad, rooted in Vygotsky's ZPD, \
the 15 Arts of Living, and the full breadth of human knowledge across all domains of life.

The platform draws on these works and thinkers (let their ideas breathe naturally -- never cite by name in content):
\
Alternative education: Montessori, Steiner (Waldorf), Dewey, Freire (democracy through dialogue; the word as path to freedom; learning as dialogic act between equals — never banking education), Freinet, Neill (Summerhill), Malaguzzi (Reggio Emilia), \
Rogers, Robinson, Gatto, Hecht (democratic education), Sobel (forest school). \
Developmental psychology: Piaget, Vygotsky, Erikson, Fröbel, Kohlberg, Maslow, Bruner, Pikler, Mead, Gardner, Goleman. \
Books: Pedagogy of the Oppressed (Freire), Mind in Society (Vygotsky), The Absorbent Mind (Montessori), \
Democracy and Education (Dewey), Summerhill (Neill), Freedom to Learn (Rogers), Frames of Mind (Gardner), \
Emotional Intelligence (Goleman), Beyond Ecophobia (Sobel), Productive Failure (Kapur), Peak (Ericsson & Pool), \
Uncommon Sense Teaching / Learn Like a Pro (Oakley et al.), The Developing Mind (Siegel), Self-Compassion (Neff), \
Mastery / The Education of Man (Fröbel), The Psychology of the Child (Piaget), Culture and Commitment (Mead), Motivation and Personality (Maslow), The Centenary of Loris Malaguzzi (Reggio Children Collective), Micromastery (Greene / Twigger), Beginners (Vanderbilt), Conscious (Harris), The Art of Logic (Cheng), \
The Beginning of Infinity (Deutsch), Ethics of Ambiguity (de Beauvoir), Dumbing Us Down (Gatto), \
The Hundred Languages of Children (Malaguzzi), The Pikler Collection (Pikler), Democratic Education (Hecht), \
How to Raise Successful People (Wojcicki), Brain Wash (Perlmutter et al.), Adventures in Human Being (Francis), \
Awaken Your Genius (Varol), Wisdom Takes Work (Holiday), The Genius of Empathy (Orloff), Presence (Cuddy), \
The Art of Insubordination (Kashdan), How to Listen (Trimboli), Win Every Argument (Hasan), Breath (Nestor), \
A Brief History of Thought (Ferry), Everything is Obvious (Watts), Shape (Ellenberg), \
Shared Wisdom (Pentland), Junglekeeper (Rosolie), Every Living Thing (Roberts), Salt (Kurlansky), \
Uncompete (Malhotra), The Story of Stories (Ashton), The Compass Within (Glazer), \
Process! (Paton & Gonzalez), Robin Hood Math (Giansiracusa), The Shape of Wonder (Lightman & Rees). \
Communication teaching by Vinh Giang (presence, clarity, self-expression).

Generate learning session #{session_num} for:

ART: The art of {art_name} — {art_tagline}
CONTEXT: {art_context}
PHASE: {phase_name} (ages {age_range})

PHASE-SPECIFIC GUIDANCE — apply to every part of the session:
{phase_guidance}

Session design principles:
- Enter through lived experience; exit into expanded awareness
- Ground abstract concepts in concrete, sensory, real-world practice
- The challenge must produce something real: a written piece, a design, an action, a practice
- Reflection questions must open rather than close — no yes/no answers
- This is session #{session_num} for this art/phase — vary the angle and entry point
- Follow the universal learning cycle: observe → connect → act → reflect (applies across all human arts and domains)
- CONTEXTUAL FRAME: Ground all examples, metaphors, and challenges in the specific world of {art_name} as described in CONTEXT above. Do not default to gardening, soil, seeds, or permaculture unless the art is Eating, Growing, or Consuming. A Moving session should feel like movement; a Listening session should feel like deep listening; a Building session could be about constructing anything — a shelter, an instrument, a rocket, a piece of furniture.
- CRITICAL: The assess question and all 4 options must be about {art_name} and this session's core concept. They must NOT reference permaculture, gardening, or ecological land practice unless the art is Growing, Eating, or Consuming. Violating this means the session has failed.

Return ONLY valid JSON with exactly these keys:
{{
  "title": "A poetic session title — max 8 words",
  "warmup": "2-4 sentences. Open attention. Ask learner to notice something in their environment or memory.",
  "explore": "3-5 sentences. Introduce the core insight. One concrete analogy or surprising example.",
  "challenge": "3-5 sentences. Exactly what learner will create or do. Specific but open to interpretation.",
  "reflect": "1-2 open questions connecting session to the learner's actual life.",
  "assess_question": "A single clear question testing the session's core concept",
  "assess_options": ["option A", "option B", "option C", "option D"],
  "assess_correct": 0
}}

The assess_correct field is the 0-based index of the correct answer.
The assess question must be about THIS art and THIS session's concept — never generic.
Return ONLY the JSON object. No preamble, no explanation, no markdown fences."""


async def generate_with_groq(prompt: str, retries: int = 3) -> dict:
    import httpx
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":   _settings["ai_model_groq_large"],
        "messages": [
            {"role": "system", "content": "You are a learning session designer. Respond with valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
        "temperature":    0.85,
        "max_tokens":     1200,
        "response_format": {"type": "json_object"},
    }
    for attempt in range(retries):
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(GROQ_URL, headers=headers, json=payload)
            if r.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"\n  Rate limited — waiting {wait}s...", end=' ', flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"].strip())
    raise RuntimeError(f"Groq rate limit persisted after {retries} retries")


async def generate_with_ollama(prompt: str) -> dict:
    import httpx
    payload = {
        "model":    _settings["ai_model_ollama_large"],
        "messages": [
            {"role": "system", "content": "You are a learning session designer. Respond with valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
        "stream":   False,
        "format":   "json",
        "options":  {"temperature": 0.85, "num_predict": 1200},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
    return json.loads(r.json()["message"]["content"].strip())


async def generate_one(art, phase, session_num, dry_run=False) -> dict:
    art_slug, art_name, art_tagline, art_context = art
    phase_slug, phase_name, age_range, phase_guidance = phase

    prompt = build_prompt(
        art_slug, art_name, art_tagline, art_context,
        phase_slug, phase_name, age_range, phase_guidance,
        session_num
    )

    if dry_run:
        print(f"\n[DRY RUN] {art_name} × {phase_name} #{session_num} — prompt: {len(prompt)} chars")
        return {
            "title":            f"[DRY] {art_name} × {phase_name} #{session_num}",
            "warmup":           "Dry run warmup",
            "explore":          "Dry run explore",
            "challenge":        "Dry run challenge",
            "reflect":          "Dry run reflect",
            "assess_question":  "Dry run question?",
            "assess_options":   ["A", "B (correct)", "C", "D"],
            "assess_correct":   1,
        }

    # Same free-provider-with-fallback shape as ai_client.ai_complete(): try
    # whichever provider the admin selected in Settings, fall back to the
    # other free provider on failure, error clearly if neither works.
    provider = _settings["ai_provider"]
    if provider == "library":
        raise RuntimeError(
            "AI provider is set to Library-only in Admin > Settings — "
            "seeding needs live AI. Switch it to Groq or Ollama to run this."
        )
    order = [provider] + [p for p in ("groq", "ollama") if p != provider]
    errors = []
    for prov in order:
        try:
            if prov == "groq":
                if not GROQ_KEY:
                    raise RuntimeError("GROQ_API_KEY not configured")
                return await generate_with_groq(prompt)
            else:
                return await generate_with_ollama(prompt)
        except Exception as e:
            errors.append(f"{prov}: {str(e)[:120]}")
    raise RuntimeError(f"All AI providers failed — {' | '.join(errors)}")




async def store_session(conn, art_id, phase_id, skill_id, data) -> int:
    # Shuffle options to avoid option-B bias from LLMs
    options       = list(data["assess_options"])
    correct_text  = options[int(data["assess_correct"])]
    random.shuffle(options)
    correct_index = options.index(correct_text)

    assess_q = json.dumps({
        "question":      data["assess_question"],
        "options":       options,
        "correct_index": correct_index,
    })

    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO sessions
              (learner_id, art_id, dev_phase_id, lecko_id, primary_skill_id, title,
               recommended_by, status,
               warmup_prompt, explore_content, challenge_prompt,
               reflect_prompt, assess_question, created_at)
            VALUES
              (1, %s, %s, NULL, %s, %s,
               'engine', 'scheduled',
               %s, %s, %s,
               %s, %s, NOW())
        """, (
            art_id, phase_id, skill_id, data["title"],
            data["warmup"], data["explore"], data["challenge"],
            data["reflect"], assess_q,
        ))
        await conn.commit()
        return cur.lastrowid


async def main(args):
    conn = await aiomysql.connect(**DB)
    await _load_settings(conn)

    if not args.dry_run:
        provider = _settings["ai_provider"]
        if provider == "library":
            print("\nERROR: AI provider is set to Library-only in Admin > Settings > AI generation.")
            print("  Seeding needs live AI — switch it to Groq or Ollama first.")
            conn.close()
            sys.exit(1)
        if provider == "groq" and not GROQ_KEY:
            print("\nERROR: Admin AI provider is set to Groq, but GROQ_API_KEY is not in .env.")
            print("  Sign up free at console.groq.com → add GROQ_API_KEY=gsk_... to .env")
            conn.close()
            sys.exit(1)
        # provider == "ollama": no env key required; reachability is checked
        # at generate time, with an automatic fall back to Groq if configured.

    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT a.id, a.slug, s.skill_id
            FROM arts a
            LEFT JOIN arts_skills s ON s.art_id = a.id AND s.is_primary = 1
            GROUP BY a.id
        """)
        art_map = {row[1]: (row[0], row[2] or 1) for row in await cur.fetchall()}

        await cur.execute("SELECT id, slug FROM dev_phases")
        phase_map = {row[1]: row[0] for row in await cur.fetchall()}

        # 2026-08-25: standing disclaimer lives in session_config (one row),
        # not duplicated across all 13 phase blocks. Fetch once, append to
        # every phase's guidance text below.
        await cur.execute(
            "SELECT config_value FROM session_config WHERE config_key = 'phase_guidance_disclaimer'"
        )
        _row = await cur.fetchone()
        _disclaimer = _row[0] if _row else (
            "This is a starting point, not a rule about this specific learner."
        )

    PHASES[:] = [
        (slug, name, age_range, f"{guidance} {_disclaimer}")
        for slug, name, age_range, guidance in PHASES
    ]

    target_arts   = [a for a in ARTS   if not args.arts   or a[0] in args.arts.split(',')]
    target_phases = [p for p in PHASES if not args.phases or p[0] in args.phases.split(',')]
    total         = len(target_arts) * len(target_phases) * args.per_art

    print(f"\n{'='*60}")
    print(f"Surfing the Frequencies — Session Library Generator v3")
    print(f"{'='*60}")
    print(f"Arts:        {len(target_arts)}")
    print(f"Phases:      {len(target_phases)}")
    print(f"Per combo:   {args.per_art}")
    print(f"Total:       {total} sessions")
    print(f"Provider:    {_settings['ai_provider']} "
          f"({_settings['ai_model_groq_large'] if _settings['ai_provider'] == 'groq' else _settings['ai_model_ollama_large']})")
    print(f"Dry run:     {args.dry_run}")
    print(f"{'='*60}\n")

    if not args.dry_run and not args.yes:
        confirm = input(f"Generate {total} sessions? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            conn.close()
            return
    elif not args.dry_run and args.yes:
        print(f"--yes flag set — skipping confirmation, generating {total} sessions.")

    generated = errors = 0

    for art in target_arts:
        art_id, skill_id = art_map.get(art[0], (None, 1))
        if not art_id:
            print(f"  ⚠ Art not in DB: {art[0]}")
            continue

        for phase in target_phases:
            phase_id = phase_map.get(phase[0])
            if not phase_id:
                print(f"  ⚠ Phase not in DB: {phase[0]}")
                continue

            for n in range(1, args.per_art + 1):
                label = f"{art[1]} × {phase[1]} #{n}"
                print(f"  {label}...", end=' ', flush=True)

                try:
                    data = await generate_one(art, phase, n, args.dry_run)
                    if not args.dry_run:
                        sid = await store_session(conn, art_id, phase_id, skill_id, data)
                        print(f"✓ id={sid} — {data['title']}")
                    else:
                        print("✓")
                    generated += 1

                    # Configurable delay — use --delay 8 or higher on free-tier Groq
                    if not args.dry_run:
                        time.sleep(args.delay)

                except json.JSONDecodeError as e:
                    print(f"✗ JSON error: {e}")
                    errors += 1
                except Exception as e:
                    err = str(e)
                    print(f"✗ {err[:80]}")
                    errors += 1
                    if "429" in err or "rate" in err.lower():
                        print("    Rate limited — waiting 60s...")
                        time.sleep(60)
                    else:
                        time.sleep(args.delay)

    conn.close()
    print(f"\n{'='*60}")
    print(f"Done: {generated} generated, {errors} errors")
    if not args.dry_run:
        print(f"The session library now serves {generated} new phase-aware sessions.")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FreqLearn session library generator")
    parser.add_argument('--arts',    default='', help='Comma-separated art slugs (default: all 15)')
    parser.add_argument('--phases',  default='', help='Comma-separated phase slugs (default: all 5)')
    parser.add_argument('--per-art', type=int, default=2, help='Sessions per art/phase combo (default: 2)')
    parser.add_argument('--dry-run', action='store_true', help='Print without calling API or writing DB')
    parser.add_argument('--yes',     action='store_true', help='Skip interactive confirmation (for admin portal)')
    parser.add_argument('--delay',   type=float, default=3.0, help='Seconds between API calls (default: 3). Increase to 8-12 on free-tier Groq to avoid rate limits.')
    args = parser.parse_args()
    asyncio.run(main(args))
