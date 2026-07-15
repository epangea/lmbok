#!/usr/bin/env python3
# ============================================================
# FreqLearn — seed_sessions.py  (v2)
# Pre-generates session content for all 15 arts × 5 phases
# using the Anthropic API (or Groq free fallback), storing
# everything in MariaDB so the platform runs at zero AI cost.
#
# Prerequisites:
#   - run: mysql -u freqlearn -p freqlearn < add_dev_phase_to_sessions.sql
#   - pip install anthropic aiomysql python-dotenv httpx --break-system-packages
#
# Run:
#   python3 seed_sessions.py                    # all arts, all phases, 2 per combo
#   python3 seed_sessions.py --phases child,adolescent --per-art 3
#   python3 seed_sessions.py --arts move,feel --dry-run
#
# Cost estimate (Anthropic): ~$0.003–0.008 per session
#   75 sessions (all arts × all phases × 1): ~$0.25–$0.60
#   150 sessions (× 2): ~$0.50–$1.20
# ============================================================

import os, sys, json, asyncio, argparse, time, random
from pathlib import Path
import aiomysql
import anthropic
from dotenv import load_dotenv

# .env lives in the backend directory regardless of where this script is run from
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent / ".env"  # fallback: same dir
load_dotenv(dotenv_path=_env_path)

DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER", "freqlearn"),
    password=os.getenv("DB_PASSWORD", "changeme"),
    db=os.getenv("DB_NAME", "freqlearn"),
    charset="utf8mb4",
)

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"

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
    ("nascent",     "Nascent",     "0-2",
     "CRITICAL: The learner is an ADULT caring for a newborn or infant aged 0-2. "
     "This session is FOR THE PARENT OR CAREGIVER, not written for the baby. "
     "The adult is navigating sleep deprivation, identity upheaval, relational strain, and the overwhelming "
     "newness of a tiny dependent life. They may have 10 minutes of fractured attention. "
     "Language: warm, honest, non-performative -- never cheerful in a hollow way. "
     "Acknowledge the exhaustion and the wonder as inseparable. "
     "Frame skill practice around attunement: reading the infant's cues, co-regulation, "
     "the parent's own nervous system, and the slow rebuilding of self amid caregiving. "
     "The warmup should invite the adult to pause and notice something about this moment -- "
     "their body, their breath, the weight of the baby, the sound in the room. "
     "The challenge should be a micro-practice: brief, doable in fragments, requiring no materials -- "
     "a 60-second body scan, a whispered intention, a single observation recorded, a small act of self-kindness. "
     "The reflection should open toward the parent's inner experience -- not infant-care technique. "
     "The assess question should be about self-awareness, attunement, or the parent's emotional landscape -- "
     "not infant development milestones or pediatric theory."),

    ("child",       "Child",       "3-11",
     "The learner is a child, ages 3-11. Default your language and complexity to a curious 8-10 year old "
     "-- younger children will follow along, and older ones won't feel talked down to. "
     "Language: warm, concrete, and playful. Short sentences. Ground every idea in something the child "
     "can see, touch, taste, hear, or do right now -- never abstract theory or adult concerns. "
     "Use analogies from animals, games, school, family, and nature. Never use jargon. "
     "WARMUP: Must be 2-3 sentences. Ask the child to notice or remember something specific and sensory "
     "-- a smell, a sound, a texture, a memory of doing something with their hands. "
     "CHALLENGE: This is the most important rule -- DO NOT default to 'draw a picture'. "
     "Rotate through: doing a real experiment (mixing, growing, building, measuring), "
     "writing or telling a short story, making something physical, playing a simple game with rules, "
     "going outside to observe and record, or interviewing a family member. "
     "Drawing is allowed occasionally but must not be the default. The challenge must feel like play, "
     "never homework. It should be completable in 10-20 minutes with things found at home. "
     "REFLECT: Ask one question the child might lie awake wondering about -- genuine curiosity, "
     "not a consequence question ('what would happen if'). Aim for something that opens the world: "
     "'Why do you think...', 'Have you ever noticed...', 'What does it feel like when...'. "
     "ASSESS: Simple enough for a curious 8-10 year old without adult help. "
     "Everyday words, relatable scenarios, no technical terms. Options must be short and clearly different."),

    ("adolescent",  "Adolescent",  "12-17",
     "Language: direct, honest, and peer-respecting — never condescending. "
     "Connect to identity, social belonging, fairness, and real-world stakes. "
     "The challenge should feel worth doing because it matters, not because it was assigned. "
     "The reflection should invite genuine self-inquiry, not performative answers. "
     "Assess options can handle moderate complexity but stay concrete and grounded in lived experience."),

    ("adult",       "Adult",       "18-60",
     "Language: warm, curious, and non-judgmental. Treat the learner as a capable, thoughtful adult. "
     "Connect concepts to work, relationships, creative practice, and personal meaning. "
     "The challenge should produce something immediately useful, beautiful, or worth sharing."),

    ("elder",       "Elder",       "61+",
     "Language: respectful, reflective, and wisdom-honoring. Acknowledge that this learner has lived. "
     "Connect to legacy, community contribution, and accumulated insight. "
     "Avoid tech-heavy or pop-culture examples. "
     "The challenge should connect learning to passing wisdom forward or deepening an existing practice. "
     "Assess options should honor depth of experience rather than testing rote recall."),

    ("prenascent",  "Prenascent",  "expecting",
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
     "The assess question should test the adult's self-understanding or emotional literacy — grounded in lived experience, not infant-care theory."),
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
        "model":   GROQ_MODEL,
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


async def generate_one(client, art, phase, session_num, dry_run=False) -> dict:
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

    if client:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    elif GROQ_KEY:
        return await generate_with_groq(prompt)
    else:
        raise RuntimeError("No AI provider configured — add ANTHROPIC_API_KEY or GROQ_API_KEY to .env")


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
    if not args.dry_run and not ANTHROPIC_KEY and not GROQ_KEY:
        print("\nERROR: No AI provider configured.")
        print("  Groq (FREE): sign up at console.groq.com → add GROQ_API_KEY=gsk_... to .env")
        print("  Anthropic:   add ANTHROPIC_API_KEY=sk-ant-... to .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if (not args.dry_run and ANTHROPIC_KEY) else None
    conn   = await aiomysql.connect(**DB)

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

    target_arts   = [a for a in ARTS   if not args.arts   or a[0] in args.arts.split(',')]
    target_phases = [p for p in PHASES if not args.phases or p[0] in args.phases.split(',')]
    total         = len(target_arts) * len(target_phases) * args.per_art

    print(f"\n{'='*60}")
    print(f"Surfing the Frequencies — Session Library Generator v2")
    print(f"{'='*60}")
    print(f"Arts:        {len(target_arts)}")
    print(f"Phases:      {len(target_phases)}")
    print(f"Per combo:   {args.per_art}")
    print(f"Total:       {total} sessions")
    print(f"Provider:    Groq")
    print(f"Dry run:     {args.dry_run}")
    if not args.dry_run:
        print(f"Est. cost:   ${total*0.003:.2f} – ${total*0.008:.2f}")
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
                    data = await generate_one(client, art, phase, n, args.dry_run)
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
