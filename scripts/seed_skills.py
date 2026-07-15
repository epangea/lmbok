#!/usr/bin/env python3
# ============================================================
# FreqLearn — seed_skills.py  (v2 — matches schema v2)
# Populates the skills table — no skill_categories dependency
# Run as: python3 seed_skills.py
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

# ── Skills: (name, slug, subcategory, description, learning_domain, skill_type, stage) ──
SKILLS = [
    # Cognitive & Intellectual
    ("Critical Thinking",              "critical_thinking",              "Reasoning",              "Analyzing, evaluating and forming reasoned judgments",                          "Literature & Language",    "cognitive",             "Middle Childhood → Lifelong"),
    ("Problem Solving",                "problem_solving",                "Reasoning",              "Identifying, framing and resolving complex challenges",                         "Engineering",              "cognitive",             "Early Childhood → Lifelong"),
    ("Systems Thinking",               "systems_thinking",               "Reasoning",              "Understanding interconnections and emergent behaviors in complex systems",        "Public Policy & Law",      "cognitive",             "Adolescence → Lifelong"),
    ("Abstract Reasoning",             "abstract_reasoning",             "Reasoning",              "Manipulating concepts not anchored to concrete objects",                         "Literature & Language",    "cognitive",             "Middle Childhood → Lifelong"),
    ("Memory & Retention",             "memory_and_retention",           "Information Processing", "Encoding, storing and retrieving information effectively",                       "Psychology",               "cognitive",             "Infancy → Lifelong"),
    ("Attention & Focus",              "attention_and_focus",            "Information Processing", "Sustaining directed awareness on a task or stimulus",                            "Psychology",               "cognitive",             "Early Childhood → Lifelong"),
    ("Research & Inquiry",             "research_and_inquiry",           "Knowledge Building",     "Systematically investigating questions using evidence",                           "Literature & Language",    "cognitive",             "Middle Childhood → Lifelong"),
    ("Mathematical Literacy",          "mathematical_literacy",          "Quantitative",           "Understanding and applying numerical and logical structures",                     "Mathematics",              "cognitive",             "Early Childhood → Lifelong"),
    ("Scientific Method",              "scientific_method",              "Knowledge Building",     "Hypothesizing, experimenting and drawing data-based conclusions",                 "Biology",                  "cognitive",             "Middle Childhood → Lifelong"),
    ("Decision Making",                "decision_making",                "Reasoning",              "Choosing among alternatives using judgment and values",                           "Psychology",               "cognitive",             "Middle Childhood → Lifelong"),
    ("Imagination & Conceptual Thinking","imagination_and_conceptual_thinking","Knowledge Building","Generating novel ideas and mental models",                                      "Visual Art & Expression",  "cognitive",             "Infancy → Lifelong"),
    # Language & Communication
    ("Oral Communication",             "oral_communication",             "Speaking",               "Expressing ideas clearly and persuasively through speech",                       "Literature & Language",    "cognitive,affective",   "Infancy → Lifelong"),
    ("Reading Literacy",               "reading_literacy",               "Written Language",       "Decoding, comprehending and interpreting written text",                           "Literature & Language",    "cognitive",             "Early Childhood → Lifelong"),
    ("Writing",                        "writing",                        "Written Language",       "Composing clear, structured and purposeful written content",                      "Literature & Language",    "cognitive",             "Early Childhood → Lifelong"),
    ("Active Listening",               "active_listening",               "Reception",              "Fully concentrating, understanding and responding to speech",                    "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Non-Verbal Communication",       "non-verbal_communication",       "Reception",              "Reading and expressing meaning through body, face and space",                    "Psychology",               "affective,psychomotor", "Infancy → Lifelong"),
    ("Storytelling & Narrative",       "storytelling_and_narrative",     "Speaking",               "Structuring and conveying experience in engaging narrative form",                "Literature & Language",    "cognitive,affective",   "Early Childhood → Lifelong"),
    ("Foreign Language Acquisition",   "foreign_language_acquisition",   "Multilingualism",        "Learning to communicate in one or more additional languages",                    "Literature & Language",    "cognitive",             "Early Childhood → Lifelong"),
    ("Rhetoric & Persuasion",          "rhetoric_and_persuasion",        "Speaking",               "Constructing and delivering arguments that move an audience",                    "Literature & Language",    "cognitive,affective",   "Adolescence → Lifelong"),
    ("Digital Communication",          "digital_communication",          "Written Language",       "Crafting effective messages across digital media and platforms",                  "Literature & Language",    "cognitive",             "Middle Childhood → Lifelong"),
    # Emotional & Psychological
    ("Self-Awareness",                 "self-awareness",                 "Intrapersonal",          "Recognizing one's own emotions, patterns and values",                            "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Emotional Regulation",           "emotional_regulation",           "Intrapersonal",          "Managing emotional responses to maintain well-being and function",               "Psychology",               "affective",             "Infancy → Lifelong"),
    ("Empathy",                        "empathy",                        "Interpersonal",          "Understanding and sharing the feelings of others",                               "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Resilience",                     "resilience",                     "Intrapersonal",          "Recovering and adapting effectively in the face of adversity",                   "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Stress Management",              "stress_management",              "Intrapersonal",          "Applying strategies to reduce and cope with psychological stress",               "Medicine & Healthcare",    "affective",             "Middle Childhood → Lifelong"),
    ("Motivation & Self-Drive",        "motivation_and_self-drive",      "Intrapersonal",          "Initiating and sustaining purposeful action toward goals",                       "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Growth Mindset",                 "growth_mindset",                 "Intrapersonal",          "Believing abilities can be developed through effort and learning",               "Psychology",               "affective",             "Middle Childhood → Lifelong"),
    ("Boundary Setting",               "boundary_setting",               "Intrapersonal",          "Asserting and maintaining healthy psychological limits",                         "Psychology",               "affective",             "Adolescence → Lifelong"),
    # Physical & Motor
    ("Gross Motor Skills",             "gross_motor_skills",             "Movement",               "Coordinating large-muscle movements for locomotion and balance",                 "Physiology",               "psychomotor",           "Infancy → Middle Childhood"),
    ("Fine Motor Skills",              "fine_motor_skills",              "Dexterity",              "Precise hand-eye coordination for manipulation of small objects",                "Physiology",               "psychomotor",           "Infancy → Middle Childhood"),
    ("Physical Fitness & Endurance",   "physical_fitness_and_endurance", "Health",                 "Maintaining cardiovascular capacity and muscular strength",                      "Medicine & Healthcare",    "psychomotor",           "Early Childhood → Lifelong"),
    ("Sports & Athletic Skills",       "sports_and_athletic_skills",     "Performance",            "Sport-specific techniques and competitive physical performance",                 "Physiology",               "psychomotor",           "Early Childhood → Adult"),
    ("Instrument Playing",             "instrument_playing",             "Performance",            "Coordinating body mechanics to produce music on an instrument",                  "Visual Art & Expression",  "psychomotor",           "Early Childhood → Lifelong"),
    ("Dance & Movement Arts",          "dance_and_movement_arts",        "Performance",            "Expressing rhythm and form through choreographed body movement",                 "Visual Art & Expression",  "psychomotor",           "Early Childhood → Lifelong"),
    ("Body Awareness & Proprioception","body_awareness_and_proprioception","Health",               "Sensing the position and movement of one's own body in space",                  "Physiology",               "psychomotor",           "Infancy → Lifelong"),
    ("Nutrition & Health Literacy",    "nutrition_and_health_literacy",  "Health",                 "Understanding and applying evidence-based health and dietary knowledge",         "Medicine & Healthcare",    "cognitive",             "Middle Childhood → Lifelong"),
    # Social & Relational
    ("Cooperation & Teamwork",         "cooperation_and_teamwork",       "Collaboration",          "Working effectively with others toward shared goals",                            "Public Policy & Law",      "affective",             "Early Childhood → Lifelong"),
    ("Conflict Resolution",            "conflict_resolution",            "Collaboration",          "Navigating disagreements to mutually satisfying outcomes",                       "Public Policy & Law",      "affective,cognitive",   "Early Childhood → Lifelong"),
    ("Leadership",                     "leadership",                     "Influence",              "Inspiring, guiding and enabling others toward a shared vision",                  "Public Policy & Law",      "affective,cognitive",   "Adolescence → Lifelong"),
    ("Negotiation",                    "negotiation",                    "Influence",              "Reaching mutually beneficial agreements through dialogue",                        "Public Policy & Law",      "cognitive,affective",   "Adolescence → Lifelong"),
    ("Cultural Competence",            "cultural_competence",            "Diversity",              "Understanding and effectively engaging with different cultures",                  "History & Journalism",     "affective,cognitive",   "Middle Childhood → Lifelong"),
    ("Community Building",             "community_building",             "Collaboration",          "Cultivating trust and belonging within a group or place",                        "Public Policy & Law",      "affective",             "Young Adult → Lifelong"),
    ("Mentorship & Teaching Others",   "mentorship_and_teaching_others", "Influence",              "Guiding another's growth through sharing knowledge and experience",              "Psychology",               "affective,cognitive",   "Young Adult → Lifelong"),
    ("Networking & Relationship Building","networking_and_relationship_building","Collaboration",  "Initiating and sustaining meaningful professional and personal connections",     "Public Policy & Law",      "affective",             "Adolescence → Lifelong"),
    # Creative & Artistic
    ("Visual Art & Drawing",           "visual_art_and_drawing",         "Visual",                 "Creating expressive or communicative images and forms",                          "Visual Art & Expression",  "psychomotor,affective", "Early Childhood → Lifelong"),
    ("Music & Rhythm",                 "music_and_rhythm",               "Auditory",               "Creating, reading, improvising and interpreting musical ideas",                  "Visual Art & Expression",  "psychomotor,cognitive", "Early Childhood → Lifelong"),
    ("Creative Writing & Poetry",      "creative_writing_and_poetry",    "Literary",               "Composing imaginative, literary or experimental written work",                   "Literature & Language",    "cognitive,affective",   "Middle Childhood → Lifelong"),
    ("Design Thinking",                "design_thinking",                "Applied",                "Human-centered, iterative approach to solving creative problems",                 "Engineering",              "cognitive",             "Adolescence → Lifelong"),
    ("Craftsmanship & Making",         "craftsmanship_and_making",       "Applied",                "Skilled hand-making of functional or decorative objects",                        "Engineering",              "psychomotor",           "Early Childhood → Lifelong"),
    ("Photography & Film",             "photography_and_film",           "Visual",                 "Capturing or composing visual narratives through lens-based media",              "Visual Art & Expression",  "psychomotor,cognitive", "Middle Childhood → Lifelong"),
    ("Improvisation",                  "improvisation",                  "Performance",            "Creating spontaneous, responsive expression in real time",                       "Visual Art & Expression",  "affective,psychomotor", "Middle Childhood → Lifelong"),
    # Technical & Digital
    ("Digital Literacy",               "digital_literacy",               "Foundational",           "Safely and effectively using digital tools and navigating information",           "Engineering",              "cognitive",             "Middle Childhood → Lifelong"),
    ("Programming & Coding",           "programming_and_coding",         "Software",               "Writing, debugging and designing computer programs",                             "Engineering",              "cognitive",             "Middle Childhood → Lifelong"),
    ("Data Analysis & Statistics",     "data_analysis_and_statistics",   "Data",                   "Extracting, interpreting and visualizing quantitative data",                     "Mathematics",              "cognitive",             "Adolescence → Lifelong"),
    ("Cybersecurity Awareness",        "cybersecurity_awareness",        "Foundational",           "Understanding and practicing digital safety and privacy",                        "Engineering",              "cognitive",             "Middle Childhood → Lifelong"),
    ("AI & Automation Literacy",       "ai_and_automation_literacy",     "Emerging",               "Understanding, using and critically evaluating AI-driven tools",                 "Engineering",              "cognitive",             "Adolescence → Lifelong"),
    ("Engineering & Systems Design",   "engineering_and_systems_design", "Applied",                "Designing and building functional physical or digital systems",                  "Engineering",              "cognitive,psychomotor", "Middle Childhood → Lifelong"),
    # Practical & Life
    ("Financial Literacy",             "financial_literacy",             "Life Management",        "Understanding money, budgeting, investing and economic systems",                  "Happiness & Finance",      "cognitive",             "Middle Childhood → Lifelong"),
    ("Cooking & Nutrition",            "cooking_and_nutrition",          "Life Management",        "Preparing healthy, safe, and satisfying food",                                   "Medicine & Healthcare",    "psychomotor",           "Early Childhood → Lifelong"),
    ("Household & DIY Management",     "household_and_diy_management",   "Life Management",        "Maintaining a home, making repairs and managing domestic logistics",              "Engineering",              "psychomotor",           "Young Adult → Lifelong"),
    ("Time & Energy Management",       "time_and_energy_management",     "Productivity",           "Allocating time, attention and energy toward priorities",                        "Psychology",               "cognitive",             "Middle Childhood → Lifelong"),
    ("Project Management",             "project_management",             "Productivity",           "Planning, executing and closing defined scopes of work",                         "Engineering",              "cognitive",             "Adolescence → Lifelong"),
    ("First Aid & Safety",             "first_aid_and_safety",           "Life Management",        "Responding effectively to medical emergencies and hazards",                      "Medicine & Healthcare",    "psychomotor,cognitive", "Middle Childhood → Lifelong"),
    ("Environmental Stewardship",      "environmental_stewardship",      "Life Management",        "Understanding and acting to protect natural systems",                             "Environmental Biology",    "affective,cognitive",   "Early Childhood → Lifelong"),
    ("Parenting & Caregiving",         "parenting_and_caregiving",       "Relationships",          "Nurturing the development and wellbeing of children or dependents",              "Psychology",               "affective",             "Young Adult → Lifelong"),
    # Philosophical & Spiritual
    ("Ethical Reasoning",              "ethical_reasoning",              "Moral",                  "Deliberating about right, wrong and responsibility with nuance",                  "Public Policy & Law",      "cognitive,affective",   "Middle Childhood → Lifelong"),
    ("Mindfulness & Contemplation",    "mindfulness_and_contemplation",  "Inner Life",             "Cultivating present-moment awareness and inner stillness",                       "Psychology",               "affective",             "Middle Childhood → Lifelong"),
    ("Meaning-Making & Purpose",       "meaning-making_and_purpose",     "Inner Life",             "Constructing a coherent sense of meaning and personal direction",                "Psychology",               "affective,cognitive",   "Adolescence → Lifelong"),
    ("Gratitude & Appreciation",       "gratitude_and_appreciation",     "Inner Life",             "Cultivating awareness of and thankfulness for life's gifts",                     "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Philosophical Inquiry",          "philosophical_inquiry",          "Wisdom",                 "Engaging with fundamental questions of existence, knowledge and value",           "Literature & Language",    "cognitive",             "Adolescence → Lifelong"),
    ("Spiritual Practice",             "spiritual_practice",             "Inner Life",             "Engaging with practices that connect to the sacred or transcendent",             "Psychology",               "affective",             "Early Childhood → Lifelong"),
    # Meta-Learning & Self-Dev
    ("Learning How to Learn",          "learning_how_to_learn",          "Learning Science",       "Understanding and applying effective strategies for acquiring new skills",        "Psychology",               "cognitive",             "Middle Childhood → Lifelong"),
    ("Self-Directed Learning",         "self-directed_learning",         "Autonomy",               "Initiating and managing one's own learning without external direction",           "Psychology",               "cognitive,affective",   "Middle Childhood → Lifelong"),
    ("Feedback Integration",           "feedback_integration",           "Autonomy",               "Receiving, processing and applying feedback to improve performance",              "Psychology",               "affective,cognitive",   "Early Childhood → Lifelong"),
    ("Habit Formation",                "habit_formation",                "Behavior Change",        "Designing and sustaining productive routines and behaviors",                     "Psychology",               "cognitive",             "Middle Childhood → Lifelong"),
    ("Adaptability & Flexibility",     "adaptability_and_flexibility",   "Resilience",             "Adjusting effectively to change, uncertainty or new information",                "Psychology",               "affective",             "Early Childhood → Lifelong"),
    ("Goal Setting & Vision",          "goal_setting_and_vision",        "Autonomy",               "Articulating clear, motivating goals and pathways to achieve them",              "Psychology",               "cognitive",             "Middle Childhood → Lifelong"),
    ("Curiosity & Wonder",             "curiosity_and_wonder",           "Learning Science",       "Sustaining an open, questioning orientation toward the world",                   "Psychology",               "affective,cognitive",   "Infancy → Lifelong"),
]


async def seed():
    conn = await aiomysql.connect(**DB)
    async with conn.cursor() as cur:
        inserted = 0
        skipped  = 0
        for order, (name, slug, subcat, desc, domain, skill_type, stage) in enumerate(SKILLS):
            try:
                await cur.execute("""
                    INSERT IGNORE INTO skills
                      (name, slug, subcategory, description, learning_domain,
                       skill_type, developmental_stage, max_level, sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,3,%s)
                """, (name, slug, subcat, desc, domain, skill_type, stage, order))
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"  ⚠ Error on {name}: {e}")

        await conn.commit()
        print(f"✓ Inserted {inserted} skills ({skipped} already existed)")
    conn.close()

if __name__ == "__main__":
    asyncio.run(seed())
