-- ============================================================
-- FreqLearn — Domain Taxonomy Migration (P25)
-- Date: 2026-06-14  |  Final: 8 domains × 5 skills = 40
-- ============================================================

-- ── CREATIVE & ARTISTIC ──────────────────────────────────────
UPDATE skills SET name = 'Drama & Theatre'
  WHERE name = 'Improvisation';
INSERT INTO skills (name, learning_domain, skill_type)
  VALUES ('Improvisation & Public Speaking', 'Creative & Artistic', 'affective,psychomotor')
  ON DUPLICATE KEY UPDATE learning_domain = VALUES(learning_domain);
-- Design Thinking moves to Tools & Systems (handled below)

-- ── LANGUAGE & COMMUNICATION ─────────────────────────────────
-- Oral Communication retired (absorbed by Improvisation & Public Speaking)
UPDATE skills SET name = 'Debate & Argumentation', skill_type = 'cognitive'
  WHERE name = 'Oral Communication';

-- ── SOCIAL & RELATIONAL ──────────────────────────────────────
UPDATE skills SET name = 'Collaboration'         WHERE name = 'Cooperation';
UPDATE skills SET name = 'Empathetic Leadership' WHERE name = 'Leadership';
UPDATE skills SET name = 'Negotiation'           WHERE name = 'Networking';

-- ── EMOTIONAL & PSYCHOLOGICAL ────────────────────────────────
UPDATE skills SET name = 'Empathy and Compassion' WHERE name = 'Empathy';
UPDATE skills SET name = 'Self-Efficacy'           WHERE name = 'Resilience';
-- Growth Mindset retired (covered by Self-Efficacy + Curiosity and Exploration)
UPDATE skills SET name = 'Contemplative Practice', learning_domain = 'Emotional & Psychological', skill_type = 'affective'
  WHERE name = 'Growth Mindset';

-- ── META-LEARNING ─────────────────────────────────────────────
UPDATE skills SET name = 'Self-Regulation'             WHERE name = 'Self-Direction';
DELETE FROM skills                                      WHERE name = 'Habit Formation';
UPDATE skills SET name = 'Curiosity and Exploration'   WHERE name = 'Curiosity';
UPDATE skills SET name = 'Vision, Mission and Purpose' WHERE name = 'Goal Setting';
INSERT INTO skills (name, learning_domain, skill_type)
  VALUES ('Personal Values', 'Meta-Learning', 'affective')
  ON DUPLICATE KEY UPDATE learning_domain = VALUES(learning_domain);

-- ── TOOLS & SYSTEMS (was Technical & Digital) ────────────────
UPDATE skills SET learning_domain = 'Tools & Systems'
  WHERE learning_domain = 'Technical & Digital';
-- Move Design Thinking from Creative & Artistic to Tools & Systems
UPDATE skills SET learning_domain = 'Tools & Systems', skill_type = 'cognitive,psychomotor'
  WHERE name = 'Design Thinking';
-- Legacy skills kept for session history, domain updated
UPDATE skills SET learning_domain = 'Tools & Systems'
  WHERE name IN ('Programming','Cybersecurity','AI Literacy');
-- Add new Tools & Systems skills
INSERT INTO skills (name, learning_domain, skill_type) VALUES
  ('Philosophy & Ethics', 'Tools & Systems', 'cognitive,affective'),
  ('Permaculture',        'Tools & Systems', 'cognitive,psychomotor')
  ON DUPLICATE KEY UPDATE learning_domain = VALUES(learning_domain);

-- ── VERIFY ───────────────────────────────────────────────────
SELECT learning_domain, GROUP_CONCAT(name ORDER BY name SEPARATOR ' · ') AS skills
FROM skills
WHERE learning_domain IN (
  'Cognitive & Intellectual','Creative & Artistic','Physical & Motor',
  'Social & Relational','Language & Communication','Emotional & Psychological',
  'Meta-Learning','Tools & Systems'
)
GROUP BY learning_domain
ORDER BY learning_domain;
