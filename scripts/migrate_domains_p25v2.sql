-- ============================================================
-- FreqLearn — Domain Taxonomy Migration P25b
-- Date: 2026-06-14b  |  Final: 8 domains × 6 skills = 48
-- Run against: freqlearn DB on build.onehouse.top
-- Safe to re-run (id-based UPDATEs are idempotent)
-- ============================================================

-- ── STEP 1: RENAMES (name + slug to match P25 UI exactly) ────

UPDATE skills SET name = 'Active Reading',               slug = 'active-reading'             WHERE id = 13;
UPDATE skills SET name = 'Storytelling',                 slug = 'storytelling'               WHERE id = 17;
UPDATE skills SET name = 'Gross Motor',                  slug = 'gross-motor'                WHERE id = 29;
UPDATE skills SET name = 'Fine Motor',                   slug = 'fine-motor'                 WHERE id = 30;
UPDATE skills SET name = 'Physical Fitness',             slug = 'physical-fitness'           WHERE id = 31;
UPDATE skills SET name = 'Dance & Movement',             slug = 'dance-and-movement'         WHERE id = 34;
UPDATE skills SET name = 'Body Awareness',               slug = 'body-awareness'             WHERE id = 35;
UPDATE skills SET name = 'Collaboration',                slug = 'collaboration'              WHERE id = 37;
UPDATE skills SET name = 'Mentorship & Teaching',        slug = 'mentorship-and-teaching'    WHERE id = 43;
UPDATE skills SET name = 'Visual Art',                   slug = 'visual-art'                 WHERE id = 45;
UPDATE skills SET name = 'Creative Writing',             slug = 'creative-writing'           WHERE id = 47;
UPDATE skills SET name = 'First Aid & Nursing',          slug = 'first-aid-and-nursing'      WHERE id = 63;
UPDATE skills SET name = 'Self-Regulation',              slug = 'self-regulation'            WHERE id = 73;
UPDATE skills SET name = 'Vision, Mission and Purpose',  slug = 'vision-mission-and-purpose' WHERE id = 77;
UPDATE skills SET name = 'Curiosity and Exploration',    slug = 'curiosity-and-exploration'  WHERE id = 78;

-- ── STEP 2: DOMAIN UPDATES for the 45 existing 8×6 skills ───
-- (3 new skills — Personal Values, Philosophy & Ethics, Permaculture — handled in Step 4)

-- Cognitive & Intellectual (6 existing)
UPDATE skills SET learning_domain = 'Cognitive & Intellectual' WHERE id IN (1, 2, 3, 5, 10, 62);
-- 1=Critical Thinking  2=Problem Solving  3=Systems Thinking
-- 5=Memory & Retention  10=Decision Making  62=Project Management

-- Creative & Artistic (6 existing)
UPDATE skills SET learning_domain = 'Creative & Artistic' WHERE id IN (45, 46, 47, 51, 79, 49);
-- 45=Visual Art  46=Music & Rhythm  47=Creative Writing
-- 51=Drama & Theatre  79=Improvisation & Public Speaking  49=Craftsmanship & Making

-- Physical & Motor (6 existing)
UPDATE skills SET learning_domain = 'Physical & Motor' WHERE id IN (29, 30, 31, 34, 35, 63);
-- 29=Gross Motor  30=Fine Motor  31=Physical Fitness
-- 34=Dance & Movement  35=Body Awareness  63=First Aid & Nursing

-- Social & Relational (6 existing)
UPDATE skills SET learning_domain = 'Social & Relational' WHERE id IN (37, 38, 39, 40, 41, 65);
-- 37=Collaboration  38=Conflict Resolution  39=Empathetic Leadership
-- 40=Negotiation  41=Cultural Competence  65=Parenting & Caregiving

-- Language & Communication (6 existing)
UPDATE skills SET learning_domain = 'Language & Communication' WHERE id IN (13, 15, 17, 12, 18, 19);
-- 13=Active Reading  15=Active Listening  17=Storytelling
-- 12=Debate & Argumentation  18=Foreign Language Acquisition  19=Rhetoric & Persuasion

-- Emotional & Psychological (6 existing)
UPDATE skills SET learning_domain = 'Emotional & Psychological' WHERE id IN (21, 22, 23, 24, 27, 69);
-- 21=Self-Awareness  22=Emotional Regulation  23=Empathy and Compassion
-- 24=Self-Efficacy  27=Contemplative Practice  69=Gratitude & Appreciation

-- Meta-Learning (5 existing — Personal Values inserted in Step 4)
UPDATE skills SET learning_domain = 'Meta-Learning' WHERE id IN (72, 73, 43, 78, 77);
-- 72=Learning How to Learn  73=Self-Regulation  43=Mentorship & Teaching
-- 78=Curiosity and Exploration  77=Vision, Mission and Purpose

-- Tools & Systems (4 existing — Philosophy & Ethics + Permaculture inserted in Step 4)
UPDATE skills SET learning_domain = 'Tools & Systems' WHERE id IN (52, 54, 48, 59);
-- 52=Digital Literacy  54=Data Analysis & Statistics
-- 48=Design Thinking  59=Cooking & Nutrition

-- ── STEP 3: DEACTIVATE non-8×6 skills (preserved for session history) ──

UPDATE skills SET is_active = 0 WHERE id IN (
  4,   -- Abstract Reasoning
  6,   -- Attention & Focus
  7,   -- Research & Inquiry
  8,   -- Mathematical Literacy
  9,   -- Scientific Method
  11,  -- Imagination & Conceptual Thinking
  14,  -- Writing (retired P25b)
  16,  -- Non-Verbal Communication
  20,  -- Digital Communication
  25,  -- Stress Management
  26,  -- Motivation & Self-Drive
  28,  -- Boundary Setting
  32,  -- Sports & Athletic Skills
  33,  -- Instrument Playing
  36,  -- Nutrition & Health Literacy
  42,  -- Community Building
  44,  -- Networking & Relationship Building
  50,  -- Photography & Film
  53,  -- Programming & Coding
  55,  -- Cybersecurity Awareness
  56,  -- AI & Automation Literacy
  57,  -- Engineering & Systems Design
  58,  -- Financial Literacy
  60,  -- Household & DIY Management
  61,  -- Time & Energy Management
  64,  -- Environmental Stewardship
  66,  -- Ethical Reasoning (superseded by Philosophy & Ethics)
  67,  -- Mindfulness & Contemplation (covered by Contemplative Practice)
  68,  -- Meaning-Making & Purpose (covered by Vision, Mission and Purpose)
  70,  -- Philosophical Inquiry (superseded by Philosophy & Ethics)
  71,  -- Spiritual Practice
  74,  -- Feedback Integration
  75,  -- Habit Formation (retired)
  76   -- Adaptability & Flexibility
);

-- ── STEP 4: INSERT 3 new skills not yet in DB ──────────────

INSERT INTO skills (name, slug, learning_domain, skill_type, is_active)
VALUES
  ('Personal Values',     'personal-values',       'Meta-Learning',   'affective',            1),
  ('Philosophy & Ethics', 'philosophy-and-ethics',  'Tools & Systems', 'cognitive,affective',  1),
  ('Permaculture',        'permaculture',            'Tools & Systems', 'cognitive,psychomotor',1)
ON DUPLICATE KEY UPDATE
  learning_domain = VALUES(learning_domain),
  skill_type      = VALUES(skill_type),
  is_active       = 1;

-- ── STEP 5: ENSURE all 45 existing 8×6 skills are active ──

UPDATE skills SET is_active = 1 WHERE id IN (
  1, 2, 3, 5, 10, 62,    -- Cognitive & Intellectual
  45, 46, 47, 51, 79, 49, -- Creative & Artistic
  29, 30, 31, 34, 35, 63, -- Physical & Motor
  37, 38, 39, 40, 41, 65, -- Social & Relational
  13, 15, 17, 12, 18, 19, -- Language & Communication
  21, 22, 23, 24, 27, 69, -- Emotional & Psychological
  72, 73, 43, 78, 77,     -- Meta-Learning (Personal Values via INSERT above)
  52, 54, 48, 59          -- Tools & Systems (Philosophy & Ethics + Permaculture via INSERT above)
);

-- ── STEP 6: VERIFY ────────────────────────────────────────────

SELECT
  learning_domain,
  COUNT(*) AS skill_count,
  GROUP_CONCAT(name ORDER BY name SEPARATOR ' · ') AS skills
FROM skills
WHERE is_active = 1
GROUP BY learning_domain
ORDER BY learning_domain;

-- Expected output: exactly 8 rows, 6 skills each (48 total active)
