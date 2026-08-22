# ============================================================
# FreqLearn — mouseion_domains.py
#
# Canonical backend source for the 8 Mouseion learning domains and their
# 48 skills (8x6 grid). Added 2026-08-22 to close the "no single shared
# source file for it" gap flagged in scripts/2026-08-20-mouseion-domains-
# migration.sql — this grouping previously lived as three independently-
# hardcoded copies:
#   1. frontend/app.js's _DOMS (inside Mouseion()) — presentation layer,
#      carries icon/color/primaryArt per domain, which nothing server-side
#      needs. Left as its own copy for that reason.
#   2. backend/routes/learners.py's MOUSEION_DOMAIN_SKILLS — now imports
#      from here instead of hardcoding.
#   3. frontend/contribute.html's LECKO submission form — previously a
#      freeform text box; now fetches routes/skills.py's
#      GET /skills/mouseion-domains, which serializes this dict.
#
# This is a plain mirror of the 8 domain names + 6 skills each. It is NOT
# sourced from Skill.learning_domain — that DB column was retired down to
# these exact 8 domain-family label strings by the 2026-08-20 migration,
# but this dict remains the source of truth for the grouping itself
# (which 6 skill *names* belong to which domain), since matching by name
# against skills.learning_domain would silently break if a skill's name
# and its DB learning_domain value ever drifted apart.
#
# If the 8x6 grid ever changes, update HERE first, then re-sync
# frontend/app.js's _DOMS (icons/colors) by hand — that one copy remains
# deliberately separate.
# ============================================================

MOUSEION_DOMAIN_SKILLS = {
    "Cognitive & Intellectual": [
        "Critical Thinking", "Problem Solving", "Systems Thinking",
        "Memory & Retention", "Decision Making", "Project Management",
    ],
    "Creative & Artistic": [
        "Visual Art", "Music & Rhythm", "Creative Writing",
        "Drama & Theatre", "Improvisation & Public Speaking", "Craftsmanship & Making",
    ],
    "Physical & Motor": [
        "Gross Motor", "Fine Motor", "Physical Fitness",
        "Dance & Movement", "Body Awareness", "First Aid & Nursing",
    ],
    "Social & Relational": [
        "Collaboration", "Conflict Resolution", "Empathetic Leadership",
        "Negotiation", "Cultural Competence", "Parenting & Caregiving",
    ],
    "Language & Communication": [
        "Active Reading", "Active Listening", "Storytelling",
        "Debate & Argumentation", "Foreign Language Acquisition", "Rhetoric & Persuasion",
    ],
    "Emotional & Psychological": [
        "Self-Awareness", "Emotional Regulation", "Empathy and Compassion",
        "Self-Efficacy", "Contemplative Practice", "Gratitude & Appreciation",
    ],
    "Meta-Learning": [
        "Learning How to Learn", "Self-Regulation", "Personal Values",
        "Curiosity and Exploration", "Vision, Mission and Purpose", "Mentorship & Teaching",
    ],
    "Tools & Systems": [
        "Digital Literacy", "Data Analysis & Statistics", "Design Thinking",
        "Philosophy & Ethics", "Permaculture", "Cooking & Nutrition",
    ],
}

MOUSEION_DOMAINS = list(MOUSEION_DOMAIN_SKILLS.keys())
