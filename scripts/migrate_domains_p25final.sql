-- ============================================================
-- FreqLearn — Domain Taxonomy Migration (P25)
-- Date: 2026-06-14  |  Final: 8 domains × 5 skills = 40
-- ============================================================

-- ── CREATIVE & ARTISTIC ──────────────────────────────────────
-- Improvisation → Drama & Theatre (repurpose existing row)
UPDATE skills SET
  name             = 'Drama & Theatre',
  slug             = 'drama-and-theatre',
  skill_type       = 'affective,psychomotor',
  learning_domain  = 'Creative & Artistic'
WHERE name = 'Improvisation';

-- Improvisation & Public Speaking (new)
INSERT INTO skills (name, slug, learning_domain, skill_type) VALUES
  ('Improvisation & Public Speaking','improvisation-and-public-speaking','Creative & Artistic','affective,psychomotor')
ON DUPLICATE KEY UPDATE learning_domain = VALUES(learning_domain), skill_type = VALUES(skill_type);

-- Design Thinking moves Creative → Tools & Systems (handled in T&S block below)

-- ── LANGUAGE & COMMUNICATION ─────────────────────────────────
-- Oral Communication → Debate & Argumentation (repurpose existing row)
UPDATE skills SET
  name            = 'Debate & Argumentation',
  slug            = 'debate-and-argumentation',
  skill_type      = 'cognitive',
  learning_domain = 'Language & Communication'
WHERE name = 'Oral Communication';

-- ── SOCIAL & RELATIONAL ──────────────────────────────────────
UPDATE skills SET name = 'Collaboration',         slug = 'collaboration'          WHERE name = 'Cooperation';
UPDATE skills SET name = 'Empathetic Leadership', slug = 'empathetic-leadership'  WHERE name = 'Leadership';
UPDATE skills SET name = 'Negotiation',           slug = 'negotiation'            WHERE name = 'Networking';

-- ── EMOTIONAL & PSYCHOLOGICAL ────────────────────────────────
UPDATE skills SET name = 'Empathy and Compassion', slug = 'empathy-and-compassion' WHERE name = 'Empathy';
UPDATE skills SET name = 'Self-Efficacy',          slug = 'self-efficacy'          WHERE name = 'Resilience';

-- Growth Mindset → Contemplative Practice (repurpose row; moves to Emotional & Psychological)
UPDATE skills SET
  name            = 'Contemplative Practice',
  slug            = 'contemplative-practice',
  skill_type      = 'affective',
  learning_domain = 'Emotional & Psychological'
WHERE name = 'Growth Mindset';

-- ── META-LEARNING ─────────────────────────────────────────────
UPDATE skills SET name = 'Self-Regulation',            slug = 'self-regulation'              WHERE name = 'Self-Direction';
DELETE FROM skills                                                                            WHERE name = 'Habit Formation';
UPDATE skills SET name = 'Curiosity and Exploration',  slug = 'curiosity-and-exploration'    WHERE name = 'Curiosity';
UPDATE skills SET name = 'Vision, Mission and Purpose',slug = 'vision-mission-and-purpose'   WHERE name = 'Goal Setting';

-- Personal Values (new)
INSERT INTO skills (name, slug, learning_domain, skill_type) VALUES
  ('Personal Values','personal-values','Meta-Learning','affective')
ON DUPLICATE KEY UPDATE learning_domain = VALUES(learning_domain), skill_type = VALUES(skill_type);

-- ── TOOLS & SYSTEMS (was Technical & Digital) ────────────────
-- Rename domain label on all surviving technical skills
UPDATE skills SET learning_domain = 'Tools & Systems'
  WHERE learning_domain = 'Technical & Digital';

-- Design Thinking: move from Creative & Artistic to Tools & Systems
UPDATE skills SET
  learning_domain = 'Tools & Systems',
  skill_type      = 'cognitive,psychomotor'
WHERE name = 'Design Thinking';

-- Legacy skills: keep rows for session history, update domain label
UPDATE skills SET learning_domain = 'Tools & Systems', is_active = 0
  WHERE name IN ('Programming','Cybersecurity','AI Literacy');

-- New Tools & Systems skills
INSERT INTO skills (name, slug, learning_domain, skill_type) VALUES
  ('Philosophy & Ethics','philosophy-and-ethics','Tools & Systems','cognitive,affective'),
  ('Permaculture',       'permaculture',         'Tools & Systems','cognitive,psychomotor')
ON DUPLICATE KEY UPDATE learning_domain = VALUES(learning_domain), skill_type = VALUES(skill_type);

-- ── VERIFY ───────────────────────────────────────────────────
SELECT learning_domain, COUNT(*) AS active_skills
FROM skills
WHERE is_active = 1
  AND learning_domain IN (
    'Cognitive & Intellectual','Creative & Artistic','Physical & Motor',
    'Social & Relational','Language & Communication','Emotional & Psychological',
    'Meta-Learning','Tools & Systems'
  )
GROUP BY learning_domain
ORDER BY learning_domain;
