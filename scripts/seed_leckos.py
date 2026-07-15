#!/usr/bin/env python3
# ============================================================
# FreqLearn — seed_leckos.py
# Seeds sample LECKOs (Learning Experience Knowledge Chunks)
# one per art per phase — 75 total to start
# Run AFTER seed_arts_skills.py:
#   python3 seed_leckos.py
# ============================================================

import os, asyncio
import aiomysql

DB = dict(
    host=os.getenv("DB_HOST","127.0.0.1"),
    port=int(os.getenv("DB_PORT",3306)),
    user=os.getenv("DB_USER","freqlearn"),
    password=os.getenv("DB_PASSWORD","changeme"),
    db=os.getenv("DB_NAME","freqlearn"),
    charset="utf8mb4",
)

# ── LECKO data: (art_slug, phase_slug, title, description, domain, skill_type, assessment_type, community_need) ──
LECKOS = [
    # ── MOVE ─────────────────────────────────────────────────
    ("move","child",
     "Shake, freeze, move",
     "Children explore movement through music — moving freely then freezing when the music stops. Develops body awareness, coordination and joyful relationship with physical movement.",
     "Physiology","psychomotor","task",
     "Healthy, active children need daily movement — this addresses sedentary school environments"),

    ("move","adolescent",
     "Design your morning ritual",
     "Learner designs and practices a personal morning movement routine combining stretch, breath and body awareness. Commits to 7 days and reflects on the effect.",
     "Physiology","psychomotor","portfolio",
     "Adolescent physical and mental health — daily movement reduces anxiety and improves focus"),

    ("move","adult",
     "Teach someone your movement practice",
     "Adult learner teaches their chosen movement practice (yoga, dance, martial art, sport) to a less experienced person, observing and adapting their instruction.",
     "Physiology","psychomotor","peer",
     "Community health — peer-led movement reduces healthcare burden and builds social bonds"),

    # ── EAT ──────────────────────────────────────────────────
    ("eat","child",
     "Grow one thing and eat it",
     "Child grows a single edible plant from seed to table — bean sprouts, radishes or herbs work well. Observes, waters, harvests and tastes.",
     "Environmental Biology","psychomotor","task",
     "Food sovereignty — understanding where food comes from builds self-reliance from the earliest age"),

    ("eat","adolescent",
     "Cook a meal from scratch for others",
     "Adolescent plans, shops for and prepares a complete meal for family or peers using whole ingredients. Discusses nutrition choices made.",
     "Medicine & Healthcare","psychomotor","community",
     "Household self-sufficiency — young people who can cook are less dependent on processed food systems"),

    ("eat","adult",
     "Map your food system",
     "Adult maps where their weekly food comes from — origin, distance, processing, packaging. Identifies three changes toward local, seasonal eating and implements one.",
     "Environmental Biology","cognitive","portfolio",
     "Community food resilience — local food systems reduce vulnerability to supply chain disruption"),

    # ── FEEL ─────────────────────────────────────────────────
    ("feel","child",
     "The feelings weather report",
     "Child identifies their emotional state as weather — sunny, stormy, foggy, windy. Draws it and shares with a trusted adult. Builds emotional vocabulary without judgement.",
     "Psychology","affective","communication",
     "Early emotional literacy prevents long-term mental health issues and improves classroom learning"),

    ("feel","adolescent",
     "Mapping my triggers",
     "Adolescent keeps a 7-day emotion journal noting triggers, physical sensations and responses. Identifies one pattern and explores its origin with a trusted person.",
     "Psychology","affective","portfolio",
     "Adolescent mental health — self-awareness reduces reactive behaviour and builds agency"),

    ("feel","adult",
     "Sit with discomfort",
     "Adult identifies one recurring emotional discomfort they habitually avoid. Practices sitting with it for five minutes daily for one week using breath as anchor. Reflects on what it reveals.",
     "Psychology","affective","mindset",
     "Emotional resilience in communities — adults who regulate well model this for children and de-escalate conflict"),

    # ── NOTICE ───────────────────────────────────────────────
    ("notice","child",
     "Sit spot",
     "Child finds one outdoor spot and sits silently for five minutes, noticing everything — sounds, smells, movement, light. Returns to the same spot for three days and compares observations.",
     "Environmental Biology","affective","task",
     "Ecological awareness begins with direct sensory experience of the living world"),

    ("notice","adolescent",
     "Contradiction hunt",
     "Adolescent identifies three contradictions in their daily environment — things that claim one thing but demonstrate another. Documents with notes or photos. Discusses without judgement.",
     "Literature & Language","cognitive","communication",
     "Critical thinking and media literacy — noticing contradiction is the first step toward independent thought"),

    ("notice","adult",
     "What is fading, what is arising",
     "Adult observes their community over one week noticing what is disappearing and what is emerging — skills, relationships, species, practices, stories. Writes a one-page reflection.",
     "History & Journalism","cognitive","portfolio",
     "Community memory and foresight — what communities notice they can act on"),

    # ── EXPRESS ──────────────────────────────────────────────
    ("express","child",
     "Make something that shows how you feel",
     "Child creates any artifact — drawing, song, dance, clay shape, story — that expresses a current feeling or experience. No wrong answers. Shares with one trusted person if they choose.",
     "Visual Art & Expression","affective","task",
     "Creative expression is a fundamental human need and a protective factor for mental health"),

    ("express","adolescent",
     "Perform your story",
     "Adolescent takes a personal experience and transforms it into a short performed piece — spoken word, music, movement, or combination. Performs for a small audience and receives structured feedback.",
     "Visual Art & Expression","affective","peer",
     "Youth voice and self-determination — performing builds confidence and civic presence"),

    ("express","adult",
     "Teach your craft",
     "Adult who has developed any expressive skill leads a one-hour session sharing it with beginners. Reflects on what teaching reveals about their own mastery.",
     "Visual Art & Expression","psychomotor","community",
     "Cultural transmission — communities that share expressive skills maintain identity and cohesion"),

    # ── LIVE ─────────────────────────────────────────────────
    ("live","child",
     "My needs and wants",
     "Child distinguishes between needs (food, shelter, safety, love) and wants (toys, screen time). Creates a visual map of their own needs being met and one need they could help meet for someone else.",
     "Public Policy & Law","cognitive","task",
     "Civic foundation — understanding needs vs wants builds basis for economic and political literacy"),

    ("live","adolescent",
     "Budget your month",
     "Adolescent tracks all spending for one month, categorises it and identifies where money aligns or conflicts with their stated values. Proposes one change.",
     "Happiness & Finance","cognitive","portfolio",
     "Financial self-reliance — young people who understand money are harder to exploit"),

    ("live","adult",
     "Map your rights and duties",
     "Adult maps their legal rights and civic duties in their local context — what they are entitled to, what they owe, and where the gaps are. Identifies one area to act on.",
     "Public Policy & Law","cognitive","community",
     "Civic participation — informed citizens engage with and improve local governance"),

    # ── LISTEN ───────────────────────────────────────────────
    ("listen","child",
     "Echo and ask",
     "In pairs, one child speaks about something that matters to them for two minutes. The other echoes back what they heard without adding opinion, then asks one curious question.",
     "Literature & Language","affective","peer",
     "Conflict prevention — children who feel heard are less likely to resort to aggression"),

    ("listen","adolescent",
     "Interview someone unlike you",
     "Adolescent interviews an elder, a recent immigrant, or someone from a different background about their life experience. Listens without interrupting. Shares one thing that surprised them.",
     "History & Journalism","affective","community",
     "Social cohesion — cross-cultural listening reduces polarisation and builds empathy"),

    ("listen","adult",
     "Deep listening circle",
     "Group of 4-8 adults sits in a circle. One person speaks uninterrupted for three minutes on what matters most to them right now. Others listen without devices. Round continues. No debate.",
     "Psychology","affective","community",
     "Community health — spaces for deep listening reduce isolation and build collective intelligence"),

    # ── GIVE ─────────────────────────────────────────────────
    ("give","child",
     "Teach a younger child one thing",
     "Child identifies something they know how to do and teaches it to a younger child or sibling — tying shoes, drawing a bird, counting in another language. Reflects on the experience.",
     "Psychology","affective","peer",
     "Intergenerational learning — children as teachers builds confidence and community bonds"),

    ("give","adolescent",
     "Community service project",
     "Adolescent identifies a genuine community need and designs a small project to address it — garden maintenance, elder visit, neighbourhood clean-up. Documents impact.",
     "Public Policy & Law","affective","community",
     "Civic agency — young people who contribute feel ownership of their community"),

    ("give","adult",
     "Mentor someone for 30 days",
     "Adult commits to meeting with a less experienced person weekly for one month, focused on a specific skill or challenge the mentee has identified. Documents the relationship.",
     "Psychology","affective","peer",
     "Knowledge transfer — mentorship is the most efficient way to transmit tacit knowledge"),

    # ── RECEIVE ──────────────────────────────────────────────
    ("receive","child",
     "Thank you, and here is why",
     "Child practices specific gratitude — not just 'thank you' but 'thank you because...'. Writes or draws three specific thank-yous to people who helped them this week.",
     "Psychology","affective","communication",
     "Social fabric — specific gratitude strengthens relationships and models generosity"),

    ("receive","adolescent",
     "Ask for feedback and use it",
     "Adolescent shares a piece of work with three people and asks for specific feedback using a structured format. Writes a reflection on what they will change and why.",
     "Psychology","cognitive","portfolio",
     "Learning culture — people who can receive feedback grow faster and collaborate better"),

    ("receive","adult",
     "Accept help gracefully",
     "Adult identifies one area where they habitually refuse help due to pride or self-sufficiency. Deliberately asks for and accepts help once. Reflects on what made it hard.",
     "Psychology","affective","mindset",
     "Community interdependence — self-reliance and accepting help are not opposites"),

    # ── COLLABORATE ──────────────────────────────────────────
    ("collaborate","child",
     "Build something together",
     "Small group of children is given materials and a challenge — build the tallest tower, make a garden bed, cook a simple dish — with no adult directing. Reflects on how decisions were made.",
     "Engineering","psychomotor","task",
     "Cooperative problem-solving is the foundational civic skill"),

    ("collaborate","adolescent",
     "Resolve a real conflict",
     "Adolescent identifies a current real conflict in their life and applies a structured resolution process — identify needs, listen, propose options, agree. Documents the process.",
     "Public Policy & Law","affective","communication",
     "Conflict resolution reduces violence and builds the social trust communities need to function"),

    ("collaborate","adult",
     "Co-design a community solution",
     "Group of adults identifies a shared community problem and runs a structured co-design session — problem framing, idea generation, prototype, feedback. Presents to community.",
     "Public Policy & Law","cognitive","community",
     "Participatory governance — communities that co-design solutions have higher implementation success"),

    # ── UNDERSTAND ───────────────────────────────────────────
    ("understand","child",
     "How does it work?",
     "Child chooses any object or phenomenon that puzzles them and investigates how it works using observation, experiment and asking questions. Documents findings in any format.",
     "Physics","cognitive","task",
     "Scientific curiosity is the foundation of innovation and informed citizenship"),

    ("understand","adolescent",
     "First principles breakdown",
     "Adolescent takes a commonly held belief in their community and breaks it down to its first principles — what is it actually based on? What evidence supports or undermines it?",
     "Literature & Language","cognitive","communication",
     "Independent thinking — first principles reasoning is the antidote to propaganda"),

    ("understand","adult",
     "Map a system you live inside",
     "Adult chooses one system that governs their life — food, water, energy, governance, economy — and maps its components, flows, feedback loops and failure points.",
     "Public Policy & Law","cognitive","portfolio",
     "Systems literacy — people who understand the systems they inhabit can change them"),

    # ── RESPECT ──────────────────────────────────────────────
    ("respect","child",
     "The golden rule in action",
     "Child identifies one situation where they did not treat someone the way they would want to be treated. Without blame, reflects on what they would do differently and practices it.",
     "Psychology","affective","mindset",
     "Ethical foundation — the golden rule is the simplest and most universal basis for social contract"),

    ("respect","adolescent",
     "Extend the circle",
     "Adolescent reflects on who their ethical circle currently includes — who they naturally consider when making decisions. Practices extending it: to strangers, other species, future generations.",
     "Public Policy & Law","affective","portfolio",
     "Ecological and social ethics — expanding moral circles is the basis for environmental and human rights"),

    ("respect","adult",
     "Sit with a worldview you reject",
     "Adult spends one week genuinely trying to understand a worldview they find wrong or repellent — reading primary sources, not critiques. Writes what they found true in it.",
     "Literature & Language","affective","mindset",
     "Civil discourse — societies where people can steelman opposing views are more resilient to polarisation"),

    # ── BUILD ────────────────────────────────────────────────
    ("build","child",
     "Fix something broken",
     "Child finds something broken in their home or environment and attempts to repair it — with guidance if needed. Documents what they tried, what worked, what they learned.",
     "Engineering","psychomotor","task",
     "Repair culture reduces waste and builds practical self-reliance from an early age"),

    ("build","adolescent",
     "Design for a real need",
     "Adolescent identifies a genuine unmet need in their community and designs a simple solution — a tool, a system, a structure, a service. Builds a prototype and tests it with real users.",
     "Engineering","cognitive","portfolio",
     "Human-centred design — communities that can build solutions to their own problems are resilient"),

    ("build","adult",
     "Build with natural materials",
     "Adult learns and practices one natural building technique — cob, bamboo joinery, earthbag, wattle and daub — and applies it to a small real project.",
     "Engineering","psychomotor","community",
     "Bioconstruction literacy — natural building reduces carbon footprint and builds local material sovereignty"),

    # ── GROW ─────────────────────────────────────────────────
    ("grow","child",
     "Compost experiment",
     "Child starts a small compost container and feeds it kitchen scraps for one month, observing decomposition. Compares composted soil to garden soil. Discusses the cycle.",
     "Environmental Biology","psychomotor","task",
     "Soil literacy is the foundation of food sovereignty and ecological understanding"),

    ("grow","adolescent",
     "Design a permaculture bed",
     "Adolescent designs a small permaculture garden bed using companion planting, water retention and soil health principles. Implements and observes for one growing season.",
     "Environmental Biology","cognitive","portfolio",
     "Regenerative agriculture — young people who can grow food are genuinely self-reliant"),

    ("grow","adult",
     "Save seeds and share them",
     "Adult learns to identify, harvest, dry and store seeds from one plant variety. Shares seeds with three other growers and documents the exchange.",
     "Environmental Biology","psychomotor","community",
     "Seed sovereignty — communities that maintain seed libraries are independent of corporate agricultural systems"),

    # ── CONSUME ──────────────────────────────────────────────
    ("consume","child",
     "Water audit",
     "Child tracks water use in their home for one day — drinking, washing, flushing, cooking. Estimates total litres. Identifies one change the family could make.",
     "Environmental Biology","cognitive","task",
     "Water literacy — communities that understand water use can manage it sustainably"),

    ("consume","adolescent",
     "My footprint, honestly",
     "Adolescent calculates their personal carbon and material footprint using a structured tool. Identifies the three highest-impact areas and researches realistic alternatives.",
     "Environmental Biology","cognitive","portfolio",
     "Environmental citizenship — informed consumers make better collective choices"),

    ("consume","adult",
     "Design a closed loop",
     "Adult maps one waste stream in their home or community and designs a closed loop — how could this output become an input for something else? Implements one change.",
     "Environmental Biology","cognitive","community",
     "Circular economy — communities that close resource loops reduce dependence on external supply chains"),
]


async def seed():
    conn = await aiomysql.connect(**DB)
    async with conn.cursor() as cur:

        # Build lookup maps
        await cur.execute("SELECT id, slug FROM arts")
        art_map = {slug: aid for aid, slug in await cur.fetchall()}

        await cur.execute("SELECT id, slug FROM dev_phases")
        phase_map = {slug: pid for pid, slug in await cur.fetchall()}

        print(f"Arts: {list(art_map.keys())}")
        print(f"Phases: {list(phase_map.keys())}")

        inserted = 0
        for (art_slug, phase_slug, title, desc, domain,
             skill_type, assessment_type, community_need) in LECKOS:

            art_id   = art_map.get(art_slug)
            phase_id = phase_map.get(phase_slug)

            if not art_id:
                print(f"  ⚠ Art not found: {art_slug}")
                continue
            if not phase_id:
                print(f"  ⚠ Phase not found: {phase_slug}")
                continue

            await cur.execute("""
                INSERT INTO leckos
                  (art_id, phase_id, title, description, learning_domain,
                   skill_type, assessment_type, community_need, utility_score)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0.75)
            """, (art_id, phase_id, title, desc, domain,
                  skill_type, assessment_type, community_need))
            inserted += 1

        await conn.commit()
        print(f"✓ Seeded {inserted} LECKOs across {len(art_map)} arts")

    conn.close()

if __name__ == "__main__":
    asyncio.run(seed())
