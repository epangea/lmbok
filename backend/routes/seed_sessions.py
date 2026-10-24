#!/usr/bin/env python3
# ============================================================
# FreqLearn — seed_sessions.py  (v3)
# Pre-generates session content for all 15 arts × 13 phases,
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
#   python3 seed_sessions.py --phases humus-soil,medium-fire --per-art 3
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
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# Emergency fallback only -- real values always come from platform_settings
# (ai_provider, ai_model_groq_large, ai_model_ollama_large), read once at
# startup in main(). Same defaults as ai_client.py.
_SETTINGS_DEFAULTS = {
    "ai_provider":         "groq",
    "ai_model_groq_large":   "openai/gpt-oss-120b",
    "ai_model_ollama_large": "llama3.1:8b",
    "ai_model_gemini_large": "gemini-3.6-flash",
}
_settings = dict(_SETTINGS_DEFAULTS)

# 2026-10-14: languages the seeder can generate in (mirrors generate.py's
# lang_names; English is the default and needs no instruction). One row per
# (art, phase, language) so the library failover can serve any UI language.
LANG_NAMES = {
    'fr': 'French (français)',
    'es': 'Spanish (español)',
    'ar': 'Arabic (العربية)',
    'vi': 'Vietnamese (tiếng Việt)',
    'zh': 'Mandarin Chinese (中文)',
    'de': 'German (Deutsch)',
    'ru': 'Russian (Русский)',
}


def _lang_instruction(language: str) -> str:
    if not language or language == 'en':
        return ""
    name = LANG_NAMES.get(language, language)
    return (
        f"\n\nCRITICAL LANGUAGE REQUIREMENT: Generate ALL session content in {name}. "
        f"This means the title, warmup, explore, challenge, reflect, assess_question, "
        f"and every single assess_option must be written in {name}. "
        f"Do not mix languages. Do not include any English except proper nouns."
    )


async def _load_settings(conn) -> None:
    """Read the same admin-configurable AI settings the live app uses."""
    global _settings
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT key_name, value FROM platform_settings WHERE key_name IN "
            "('ai_provider', 'ai_model_groq_large', 'ai_model_ollama_large', 'ai_model_gemini_large')"
        )
        rows = await cur.fetchall()
    out = dict(_SETTINGS_DEFAULTS)
    for k, v in rows:
        if v is not None and str(v).strip() != "":
            out[k] = str(v)
    _settings = out


# 2026-08-26: platform identity, phase pedagogy guidance, contextual art
# lenses, and the phase_guidance_disclaimer all now live in session_config
# -- the same table and the same admin-editable content generate.py's live
# session-generation prompt pulls from (see admin panel's Prompt Anatomy
# section). This replaces what used to be a second, independently
# maintained copy of the same content baked into this file. Fallback
# strings below are intentionally short and generic -- not a duplicate of
# the full research-grounded essays -- since the migration always seeds
# every row and a missing key here should be treated as a bug to notice,
# not silently papered over with a full copy of the content again.
_PLATFORM_IDENTITY_FALLBACK = (
    'You are the learning engine for "Surfing the Frequencies" -- a free, lifelong learning '
    'platform built on the philosophy of "To Be Human" by Charbel Haddad.'
)
_PHASE_GUIDANCE_FALLBACK = (
    "Adapt tone, complexity, and challenge-type to this learner's developmental phase. "
    "This is a starting point, not a rule about this specific learner."
)
_session_config: dict = {}


async def _load_session_config(conn) -> None:
    """Bulk-fetch every session_config row once per run -- platform_identity,
    the 15 art_lens:*, the 13 phase_guide:*, and phase_guidance_disclaimer
    -- so PHASES/ARTS below can be rebuilt from the live, admin-editable
    values instead of a hardcoded independent copy."""
    global _session_config
    async with conn.cursor() as cur:
        await cur.execute("SELECT config_key, config_value FROM session_config")
        rows = await cur.fetchall()
    _session_config = {k: v for k, v in rows if v is not None and str(v).strip() != ""}

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
    # 2026-08-26: guidance text (4th field) is now a short local placeholder
    # only -- immediately overwritten by _load_session_config()'s live
    # phase_guide:<slug> values + phase_guidance_disclaimer, rebuilt into
    # this list at the start of main(). See PHASES[:] rebuild below.
    ("light",         "Light",         "expecting", _PHASE_GUIDANCE_FALLBACK),
    ("sandy-soil",    "Sandy Soil",    "0~2",       _PHASE_GUIDANCE_FALLBACK),
    ("moist-soil",    "Moist Soil",    "3~5",       _PHASE_GUIDANCE_FALLBACK),
    ("humus-soil",    "Humus Soil",    "6~8",       _PHASE_GUIDANCE_FALLBACK),
    ("low-fire",      "Low Fire",      "9~11",      _PHASE_GUIDANCE_FALLBACK),
    ("medium-fire",   "Medium Fire",   "12~14",     _PHASE_GUIDANCE_FALLBACK),
    ("high-fire",     "High Fire",     "15~17",     _PHASE_GUIDANCE_FALLBACK),
    ("low-wind",      "Low Wind",      "18~22",     _PHASE_GUIDANCE_FALLBACK),
    ("high-wind",     "High Wind",     "23~27",     _PHASE_GUIDANCE_FALLBACK),
    ("water",         "Water",         "28~38",     _PHASE_GUIDANCE_FALLBACK),
    ("metal",         "Metal",         "39~59",     _PHASE_GUIDANCE_FALLBACK),
    ("stone",         "Stone",         "60~80",     _PHASE_GUIDANCE_FALLBACK),
    ("wood",          "Wood",          "81+",       _PHASE_GUIDANCE_FALLBACK),
]



def build_prompt(art_slug, art_name, art_tagline, art_context,
                 phase_slug, phase_name, age_range, phase_guidance,
                 session_num, platform_identity, avoid_titles=None):
    # 2026-10-22: avoid_titles = {"titles": [...], "openers": [...]} from
    # fetch_titles_to_avoid(); each combo is generated alone, so without this
    # the model repeats itself across an art ("Echoes of ..." x7).
    avoid_block = ""
    if avoid_titles:
        bits = []
        if avoid_titles.get("titles"):
            bits.append("Titles already used for this art in the library -- do not reuse any of them, "
                        "and do not open the title with the same word(s) as any of them: "
                        + "; ".join(avoid_titles["titles"]))
        if avoid_titles.get("openers"):
            bits.append("Opening words already overused across the library -- do not start the "
                        "title with: " + ", ".join(avoid_titles["openers"]))
        avoid_block = "".join("\n- TITLE VARIETY: " + b for b in bits)
    # 2026-08-26: platform_identity is now passed in (sourced from
    # session_config, same as generate.py's live prompt) instead of being
    # baked into this f-string -- was an independently-worded duplicate
    # of the same block.
    return f"""{platform_identity}

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
- This is session #{session_num} for this art/phase — vary the angle and entry point{avoid_block}
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


async def generate_with_groq(prompt: str) -> dict:
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
    # 2026-10-21: gpt-oss models default to medium reasoning, which spends the
    # 1200-token budget before the JSON is finished (Groq 400
    # json_validate_failed) -- same fix as ai_client._call_groq.
    if "gpt-oss" in payload["model"]:
        payload["reasoning_effort"] = "low"
    # 2026-10-14: single attempt. The old inner 60/120/180s retry loop kept a
    # seed run alive for hours against a rate-limited Groq key (and never
    # reached the next provider). A 429 now fails straight through to the
    # next provider in generate_one()'s chain; the main loop applies ONE
    # shared backoff and gives up after --max-consecutive-failures.
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GROQ_URL, headers=headers, json=payload)
        if r.status_code == 429:
            raise RuntimeError("Groq rate limit reached (429)")
        r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"].strip())


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


_GEMINI_EFFORT_OK: dict = {}


async def generate_with_gemini(prompt: str) -> dict:
    """Same request shape as ai_client._call_gemini (OpenAI-compatible
    endpoint, strict-JSON mode, reasoning_effort none). No temperature:
    Google deprecated sampling params for 3.6+ models."""
    import httpx
    model = _settings["ai_model_gemini_large"]
    base = {
        "model":    model,
        "messages": [
            {"role": "system", "content": "You are a learning session designer. Respond with valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
        "max_tokens":      1200,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {GEMINI_KEY}", "Content-Type": "application/json"}
    # Models differ in which reasoning_effort they accept (3.5 Flash-Lite
    # rejects "none"). Same ladder as ai_client._call_gemini: "none" ->
    # "minimal" -> omitted (with a bigger token budget), advancing only on 400.
    efforts = [_GEMINI_EFFORT_OK[model]] if model in _GEMINI_EFFORT_OK else ["none", "minimal", None]
    r = None
    for i, effort in enumerate(efforts):
        payload = dict(base)
        if effort is not None:
            payload["reasoning_effort"] = effort
        else:
            payload["max_tokens"] = 3600
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(GEMINI_URL, headers=headers, json=payload)
        if r.status_code == 429:
            raise RuntimeError("Gemini rate limit reached (429)")
        if r.status_code == 400 and i < len(efforts) - 1:
            continue
        r.raise_for_status()
        _GEMINI_EFFORT_OK[model] = effort
        break
    return json.loads(r.json()["choices"][0]["message"]["content"].strip())


async def fetch_titles_to_avoid(conn, art_id, language="en", art_limit=40) -> dict:
    """2026-10-22: titles already in the seed library for this art (most recent
    first), plus first words used 4+ times library-wide. Read fresh before each
    generation so titles created earlier in the same run are included."""
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT title FROM sessions
            WHERE art_id = %s AND learner_id = 1 AND model IS NULL AND title IS NOT NULL
              AND COALESCE(language,'en') = %s
            ORDER BY id DESC LIMIT %s
        """, (art_id, language, art_limit))
        titles = [r[0] for r in await cur.fetchall()]
        await cur.execute("""
            SELECT SUBSTRING_INDEX(title, ' ', 1) AS w, COUNT(*) AS c FROM sessions
            WHERE learner_id = 1 AND model IS NULL AND title IS NOT NULL
              AND COALESCE(language,'en') = %s
            GROUP BY w HAVING c >= 4 ORDER BY c DESC LIMIT 8
        """, (language,))
        openers = [r[0] for r in await cur.fetchall() if len(r[0]) > 3]
    return {"titles": titles, "openers": openers}


async def generate_one(art, phase, session_num, dry_run=False, language="en", avoid_titles=None) -> dict:
    art_slug, art_name, art_tagline, art_context = art
    phase_slug, phase_name, age_range, phase_guidance = phase
    platform_identity = _session_config.get("platform_identity", _PLATFORM_IDENTITY_FALLBACK)

    prompt = build_prompt(
        art_slug, art_name, art_tagline, art_context,
        phase_slug, phase_name, age_range, phase_guidance,
        session_num, platform_identity, avoid_titles
    ) + _lang_instruction(language)

    if dry_run:
        print(f"\n[DRY RUN] {art_name} × {phase_name} [{language}] #{session_num} — prompt: {len(prompt)} chars")
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
    order = [provider] + [p for p in ("groq", "ollama", "gemini") if p != provider]
    errors = []
    for prov in order:
        try:
            if prov == "groq":
                if not GROQ_KEY:
                    raise RuntimeError("GROQ_API_KEY not configured")
                return await generate_with_groq(prompt)
            elif prov == "gemini":
                if not GEMINI_KEY:
                    raise RuntimeError("GEMINI_API_KEY not configured")
                return await generate_with_gemini(prompt)
            else:
                return await generate_with_ollama(prompt)
        except Exception as e:
            errors.append(f"{prov}: {str(e)[:120]}")
    raise RuntimeError(f"All AI providers failed — {' | '.join(errors)}")




async def store_session(conn, art_id, phase_id, skill_id, data, language="en") -> int:
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
               recommended_by, status, language,
               warmup_prompt, explore_content, challenge_prompt,
               reflect_prompt, assess_question, created_at)
            VALUES
              (1, %s, %s, NULL, %s, %s,
               'engine', 'scheduled', %s,
               %s, %s, %s,
               %s, %s, NOW())
        """, (
            art_id, phase_id, skill_id, data["title"], language,
            data["warmup"], data["explore"], data["challenge"],
            data["reflect"], assess_q,
        ))
        await conn.commit()
        return cur.lastrowid


async def main(args):
    conn = await aiomysql.connect(**DB)
    await _load_settings(conn)
    await _load_session_config(conn)

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

    # 2026-08-26: rebuild PHASES/ARTS from the session_config values loaded
    # by _load_session_config() above -- the same admin-editable content
    # generate.py's live prompt uses, instead of an independently
    # maintained copy. Falls back to the short generic strings already in
    # PHASES/ARTS (not a second copy of the full essays) if a key is
    # somehow missing from the DB.
    PHASES[:] = [
        (slug, name, age_range,
         f"{_session_config.get(f'phase_guide:{slug}', fallback_guidance)} "
         f"{_session_config.get('phase_guidance_disclaimer', 'This is a starting point, not a rule about this specific learner.')}")
        for slug, name, age_range, fallback_guidance in PHASES
    ]
    ARTS[:] = [
        (slug, name, tagline, _session_config.get(f'art_lens:{slug}', fallback_detail))
        for slug, name, tagline, fallback_detail in ARTS
    ]

    target_arts   = [a for a in ARTS   if not args.arts   or a[0] in args.arts.split(',')]
    target_phases = [p for p in PHASES if not args.phases or p[0] in args.phases.split(',')]

    if args.languages.strip().lower() == 'all':
        target_langs = ['en'] + sorted(LANG_NAMES)
    else:
        target_langs = [l.strip() for l in args.languages.split(',') if l.strip()]
        bad = [l for l in target_langs if l != 'en' and l not in LANG_NAMES]
        if bad:
            print(f"Unknown language code(s): {', '.join(bad)} (valid: en, {', '.join(sorted(LANG_NAMES))})")
            conn.close()
            return 1

    # Seed-origin rows already stored (learner 1, no model) per
    # (art, phase, language); a NULL language counts as English.
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT art_id, dev_phase_id, COALESCE(language, 'en'), COUNT(*)
            FROM sessions
            WHERE dev_phase_id IS NOT NULL AND warmup_prompt IS NOT NULL
              AND learner_id = 1 AND model IS NULL
            GROUP BY art_id, dev_phase_id, COALESCE(language, 'en')
        """)
        existing = {(r[0], r[1], r[2]): r[3] for r in await cur.fetchall()}

    # Flat work list of only what is still missing, so a re-run after an
    # aborted or partial run resumes where it stopped.
    work = []
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
            for lang in target_langs:
                have = existing.get((art_id, phase_id, lang), 0)
                for n in range(have + 1, args.per_art + 1):
                    work.append((art, art_id, skill_id, phase, phase_id, lang, n))
    total = len(work)

    print(f"\n{'='*60}")
    print(f"Surfing the Frequencies — Session Library Generator v3")
    print(f"{'='*60}")
    print(f"Arts:        {len(target_arts)}")
    print(f"Phases:      {len(target_phases)}")
    print(f"Languages:   {','.join(target_langs)}")
    print(f"Per combo:   {args.per_art} per art/phase/language (already-stored combos are skipped)")
    print(f"Total:       {total} sessions")
    print(f"Provider:    {_settings['ai_provider']} "
          f"({_settings.get('ai_model_' + _settings['ai_provider'] + '_large', '?')})")
    print(f"Dry run:     {args.dry_run}")
    print(f"{'='*60}\n")

    if total == 0:
        print("Nothing to do -- every requested art/phase/language combo already has its sessions.")
        conn.close()
        return 0

    if not args.dry_run and not args.yes:
        confirm = input(f"Generate {total} sessions? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            conn.close()
            return
    elif not args.dry_run and args.yes:
        print(f"--yes flag set — skipping confirmation, generating {total} sessions.")

    generated = errors = 0
    consecutive_failures = 0
    aborted = False

    for art, art_id, skill_id, phase, phase_id, lang, n in work:
        if aborted:
            break
        label = f"{art[1]} × {phase[1]} [{lang}] #{n}"
        print(f"  {label}...", end=' ', flush=True)

        try:
            avoid = None if args.dry_run else await fetch_titles_to_avoid(conn, art_id, lang)
            data = await generate_one(art, phase, n, args.dry_run, lang, avoid)
            if not args.dry_run:
                sid = await store_session(conn, art_id, phase_id, skill_id, data, lang)
                print(f"✓ id={sid} — {data['title']}")
            else:
                print("✓")
            generated += 1
            consecutive_failures = 0

            # Configurable delay — use --delay 8 or higher on free-tier Groq
            if not args.dry_run:
                time.sleep(args.delay)

        except json.JSONDecodeError as e:
            print(f"✗ JSON error: {e}")
            errors += 1
        except Exception as e:
            err = str(e)
            print(f"✗ {err[:300]}")
            errors += 1
            consecutive_failures += 1
            # 2026-10-14: one shared backoff + a hard stop. Previously an
            # all-providers-down run just kept going (and exited 0, so the
            # admin UI reported "done" with nothing generated).
            if consecutive_failures >= args.max_consecutive_failures:
                print(f"\nSTOPPING: {consecutive_failures} consecutive provider failures -- "
                      f"providers look unavailable. Re-run later; stored sessions are kept "
                      f"and already-filled combos are skipped.")
                aborted = True
            else:
                wait = min(30 * 2 ** (consecutive_failures - 1), 300)
                print(f"    backing off {wait}s "
                      f"({consecutive_failures}/{args.max_consecutive_failures} consecutive failures)")
                time.sleep(wait)

    conn.close()
    print(f"\n{'='*60}")
    print(f"Done: {generated} generated, {errors} errors")
    if not args.dry_run:
        print(f"The session library now serves {generated} new phase-aware sessions.")
    print(f"{'='*60}")
    # Non-zero exit when the run was cut short or produced nothing, so
    # admin.py's _run_seed reports a real error instead of a clean "done".
    if aborted or (not args.dry_run and total > 0 and generated == 0):
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FreqLearn session library generator")
    parser.add_argument('--arts',    default='', help='Comma-separated art slugs (default: all 15)')
    parser.add_argument('--phases',  default='', help='Comma-separated phase slugs (default: all 13)')
    parser.add_argument('--per-art', type=int, default=2, help='Target sessions per art/phase/language combo (default: 2); combos already holding that many are skipped, so re-runs resume instead of duplicating')
    parser.add_argument('--languages', default='en', help="Comma-separated language codes, or 'all' (default: en). Valid: en, fr, es, ar, vi, zh, de, ru")
    parser.add_argument('--dry-run', action='store_true', help='Print without calling API or writing DB')
    parser.add_argument('--max-consecutive-failures', type=int, default=5, help='Stop the run after this many provider failures in a row (default: 5).')
    parser.add_argument('--yes',     action='store_true', help='Skip interactive confirmation (for admin portal)')
    parser.add_argument('--delay',   type=float, default=3.0, help='Seconds between API calls (default: 3). Increase to 8-12 on free-tier Groq to avoid rate limits.')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args)) or 0)
