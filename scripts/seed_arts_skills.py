#!/usr/bin/env python3
# ============================================================
# FreqLearn — seed_arts_skills.py
# Maps all 78 skills to their primary arts (15 arts framework)
# Run AFTER seed_skills.py:
#   python3 seed_arts_skills.py
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

# ── Mapping: art_slug → [skill_slugs] ────────────────────────
# Each skill slug must match exactly what seed_skills.py inserted
ARTS_SKILLS = {
    # ── Being ─────────────────────────────────────────────────
    "move": [
        "gross_motor_skills",
        "fine_motor_skills",
        "physical_fitness_and_endurance",
        "sports_and_athletic_skills",
        "dance_and_movement_arts",
        "body_awareness_and_proprioception",
        "instrument_playing",
    ],
    "eat": [
        "nutrition_and_health_literacy",
        "cooking_and_nutrition",
        "environmental_stewardship",
    ],
    "feel": [
        "self-awareness",
        "emotional_regulation",
        "empathy",
        "resilience",
        "stress_management",
        "boundary_setting",
        "growth_mindset",
    ],
    "notice": [
        "attention_and_focus",
        "curiosity_and_wonder",
        "mindfulness_and_contemplation",
        "body_awareness_and_proprioception",
        "scientific_method",
    ],
    "express": [
        "creative_writing_and_poetry",
        "visual_art_and_drawing",
        "music_and_rhythm",
        "photography_and_film",
        "improvisation",
        "oral_communication",
        "storytelling_and_narrative",
    ],
    # ── Becoming ──────────────────────────────────────────────
    "live": [
        "financial_literacy",
        "time_and_energy_management",
        "household_and_diy_management",
        "project_management",
        "first_aid_and_safety",
        "digital_literacy",
        "ai_and_automation_literacy",
    ],
    "listen": [
        "active_listening",
        "empathy",
        "non-verbal_communication",
        "cultural_competence",
        "foreign_language_acquisition",
    ],
    "give": [
        "mentorship_and_teaching_others",
        "parenting_and_caregiving",
        "community_building",
        "environmental_stewardship",
        "craftsmanship_and_making",
    ],
    "receive": [
        "feedback_integration",
        "adaptability_and_flexibility",
        "growth_mindset",
        "self-awareness",
        "gratitude_and_appreciation",
    ],
    "collaborate": [
        "cooperation_and_teamwork",
        "conflict_resolution",
        "leadership",
        "negotiation",
        "networking_and_relationship_building",
        "motivation_and_self-drive",
    ],
    # ── Connecting ────────────────────────────────────────────
    "understand": [
        "critical_thinking",
        "systems_thinking",
        "abstract_reasoning",
        "mathematical_literacy",
        "scientific_method",
        "research_and_inquiry",
        "philosophical_inquiry",
        "data_analysis_and_statistics",
    ],
    "respect": [
        "ethical_reasoning",
        "cultural_competence",
        "gratitude_and_appreciation",
        "mindfulness_and_contemplation",
        "spiritual_practice",
        "meaning-making_and_purpose",
    ],
    "build": [
        "engineering_and_systems_design",
        "design_thinking",
        "programming_and_coding",
        "craftsmanship_and_making",
        "household_and_diy_management",
        "project_management",
    ],
    "grow": [
        "environmental_stewardship",
        "scientific_method",
        "nutrition_and_health_literacy",
        "cooking_and_nutrition",
        "systems_thinking",
        "physical_fitness_and_endurance",
    ],
    "consume": [
        "environmental_stewardship",
        "financial_literacy",
        "data_analysis_and_statistics",
        "digital_literacy",
        "cybersecurity_awareness",
        "decision_making",
    ],
}

# Meta-learning skills — secondary across all arts
META_SKILLS = [
    "learning_how_to_learn",
    "self-directed_learning",
    "habit_formation",
    "goal_setting_and_vision",
    "adaptability_and_flexibility",
    "feedback_integration",
    "curiosity_and_wonder",
]


async def seed():
    conn = await aiomysql.connect(**DB)
    async with conn.cursor() as cur:

        # Build slug → id maps
        await cur.execute("SELECT id, slug FROM arts")
        art_map = {slug: aid for aid, slug in await cur.fetchall()}

        await cur.execute("SELECT id, slug FROM skills")
        skill_map = {slug: sid for sid, slug in await cur.fetchall()}

        print(f"Found {len(art_map)} arts, {len(skill_map)} skills")

        inserted = 0
        skipped  = 0

        for art_slug, skill_slugs in ARTS_SKILLS.items():
            art_id = art_map.get(art_slug)
            if not art_id:
                print(f"  ⚠ Art not found: {art_slug}")
                continue

            for skill_slug in skill_slugs:
                # Try exact match first, then fuzzy
                skill_id = skill_map.get(skill_slug)
                if not skill_id:
                    # Try partial match — skill names sometimes differ slightly
                    matches = [v for k,v in skill_map.items() if skill_slug[:12] in k]
                    if matches:
                        skill_id = matches[0]
                    else:
                        print(f"  ⚠ Skill not found: {skill_slug} (art: {art_slug})")
                        skipped += 1
                        continue

                await cur.execute("""
                    INSERT IGNORE INTO arts_skills (art_id, skill_id, is_primary)
                    VALUES (%s, %s, TRUE)
                """, (art_id, skill_id))
                inserted += 1

        # Add meta-learning skills as secondary to ALL arts
        for art_slug, art_id in art_map.items():
            for skill_slug in META_SKILLS:
                skill_id = skill_map.get(skill_slug)
                if skill_id:
                    await cur.execute("""
                        INSERT IGNORE INTO arts_skills (art_id, skill_id, is_primary)
                        VALUES (%s, %s, FALSE)
                    """, (art_id, skill_id))

        await conn.commit()
        print(f"✓ Mapped {inserted} skills to arts ({skipped} not found)")
        print(f"✓ Meta-learning skills added as secondary to all {len(art_map)} arts")

    conn.close()

if __name__ == "__main__":
    asyncio.run(seed())
