-- 2026-08-20b-STEP2-delete-non-mouseion-skills.sql
--
-- Run 2026-08-20b-STEP1-preview-non-mouseion-skills.sql FIRST and look at the
-- numbers before running this. This actually deletes rows across 5 tables.
--
-- Per 2026-08-20 decision: the platform's skill taxonomy is deliberately just the
-- 8x6=48 Mouseion grid -- high-level and universal on purpose, everything else
-- falls beneath it. These 34 skill rows sit outside that grid entirely (confirmed
-- live: `skills` has 82 rows total, only 48 match frontend/app.js's _DOMS). They
-- still carried the retired subject-matter taxonomy in learning_domain, which is
-- what surfaced them during the 11/14-domain cleanup. Removing them outright
-- rather than remapping, per Charbel: "removing any of these domains and skills
-- that do not form the 8x6 we had already agreed on."
--
-- BACKUP FIRST -- see the mysqldump command from earlier in this thread.
--
-- Order matters -- no ON DELETE CASCADE is configured on any of these FKs, so
-- children must go before the skills rows themselves, or MariaDB will reject
-- the DELETE with a foreign key constraint error:
--   learner_skill_progress.skill_id  -> skills.id
--   sessions.primary_skill_id        -> skills.id  (NOT NULL -- sessions get deleted)
--   verified_skills.skill_id         -> skills.id
--   arts_skills.skill_id             -> skills.id  (composite PK with art_id)
--
-- Note: sessions.secondary_skill_ids is a JSON array, not FK-enforced -- a skill
-- id could theoretically linger there after this runs. Not fixed by this script.

START TRANSACTION;

DELETE FROM learner_skill_progress
WHERE skill_id IN (SELECT id FROM skills WHERE name IN (
  'Abstract Reasoning',
  'Attention & Focus',
  'Research & Inquiry',
  'Mathematical Literacy',
  'Scientific Method',
  'Imagination & Conceptual Thinking',
  'Writing',
  'Non-Verbal Communication',
  'Digital Communication',
  'Stress Management',
  'Motivation & Self-Drive',
  'Boundary Setting',
  'Sports & Athletic Skills',
  'Instrument Playing',
  'Nutrition & Health Literacy',
  'Community Building',
  'Networking & Relationship Building',
  'Photography & Film',
  'Programming & Coding',
  'Cybersecurity Awareness',
  'AI & Automation Literacy',
  'Engineering & Systems Design',
  'Financial Literacy',
  'Household & DIY Management',
  'Time & Energy Management',
  'Environmental Stewardship',
  'Ethical Reasoning',
  'Mindfulness & Contemplation',
  'Meaning-Making & Purpose',
  'Philosophical Inquiry',
  'Spiritual Practice',
  'Feedback Integration',
  'Habit Formation',
  'Adaptability & Flexibility'
));

DELETE FROM sessions
WHERE primary_skill_id IN (SELECT id FROM skills WHERE name IN (
  'Abstract Reasoning',
  'Attention & Focus',
  'Research & Inquiry',
  'Mathematical Literacy',
  'Scientific Method',
  'Imagination & Conceptual Thinking',
  'Writing',
  'Non-Verbal Communication',
  'Digital Communication',
  'Stress Management',
  'Motivation & Self-Drive',
  'Boundary Setting',
  'Sports & Athletic Skills',
  'Instrument Playing',
  'Nutrition & Health Literacy',
  'Community Building',
  'Networking & Relationship Building',
  'Photography & Film',
  'Programming & Coding',
  'Cybersecurity Awareness',
  'AI & Automation Literacy',
  'Engineering & Systems Design',
  'Financial Literacy',
  'Household & DIY Management',
  'Time & Energy Management',
  'Environmental Stewardship',
  'Ethical Reasoning',
  'Mindfulness & Contemplation',
  'Meaning-Making & Purpose',
  'Philosophical Inquiry',
  'Spiritual Practice',
  'Feedback Integration',
  'Habit Formation',
  'Adaptability & Flexibility'
));

DELETE FROM verified_skills
WHERE skill_id IN (SELECT id FROM skills WHERE name IN (
  'Abstract Reasoning',
  'Attention & Focus',
  'Research & Inquiry',
  'Mathematical Literacy',
  'Scientific Method',
  'Imagination & Conceptual Thinking',
  'Writing',
  'Non-Verbal Communication',
  'Digital Communication',
  'Stress Management',
  'Motivation & Self-Drive',
  'Boundary Setting',
  'Sports & Athletic Skills',
  'Instrument Playing',
  'Nutrition & Health Literacy',
  'Community Building',
  'Networking & Relationship Building',
  'Photography & Film',
  'Programming & Coding',
  'Cybersecurity Awareness',
  'AI & Automation Literacy',
  'Engineering & Systems Design',
  'Financial Literacy',
  'Household & DIY Management',
  'Time & Energy Management',
  'Environmental Stewardship',
  'Ethical Reasoning',
  'Mindfulness & Contemplation',
  'Meaning-Making & Purpose',
  'Philosophical Inquiry',
  'Spiritual Practice',
  'Feedback Integration',
  'Habit Formation',
  'Adaptability & Flexibility'
));

DELETE FROM arts_skills
WHERE skill_id IN (SELECT id FROM skills WHERE name IN (
  'Abstract Reasoning',
  'Attention & Focus',
  'Research & Inquiry',
  'Mathematical Literacy',
  'Scientific Method',
  'Imagination & Conceptual Thinking',
  'Writing',
  'Non-Verbal Communication',
  'Digital Communication',
  'Stress Management',
  'Motivation & Self-Drive',
  'Boundary Setting',
  'Sports & Athletic Skills',
  'Instrument Playing',
  'Nutrition & Health Literacy',
  'Community Building',
  'Networking & Relationship Building',
  'Photography & Film',
  'Programming & Coding',
  'Cybersecurity Awareness',
  'AI & Automation Literacy',
  'Engineering & Systems Design',
  'Financial Literacy',
  'Household & DIY Management',
  'Time & Energy Management',
  'Environmental Stewardship',
  'Ethical Reasoning',
  'Mindfulness & Contemplation',
  'Meaning-Making & Purpose',
  'Philosophical Inquiry',
  'Spiritual Practice',
  'Feedback Integration',
  'Habit Formation',
  'Adaptability & Flexibility'
));

DELETE FROM skills
WHERE name IN (
  'Abstract Reasoning',
  'Attention & Focus',
  'Research & Inquiry',
  'Mathematical Literacy',
  'Scientific Method',
  'Imagination & Conceptual Thinking',
  'Writing',
  'Non-Verbal Communication',
  'Digital Communication',
  'Stress Management',
  'Motivation & Self-Drive',
  'Boundary Setting',
  'Sports & Athletic Skills',
  'Instrument Playing',
  'Nutrition & Health Literacy',
  'Community Building',
  'Networking & Relationship Building',
  'Photography & Film',
  'Programming & Coding',
  'Cybersecurity Awareness',
  'AI & Automation Literacy',
  'Engineering & Systems Design',
  'Financial Literacy',
  'Household & DIY Management',
  'Time & Energy Management',
  'Environmental Stewardship',
  'Ethical Reasoning',
  'Mindfulness & Contemplation',
  'Meaning-Making & Purpose',
  'Philosophical Inquiry',
  'Spiritual Practice',
  'Feedback Integration',
  'Habit Formation',
  'Adaptability & Flexibility'
);

-- Verify before committing: should show exactly 48, all 8 real Mouseion domains
SELECT COUNT(*) AS remaining_skill_count FROM skills;
SELECT DISTINCT learning_domain FROM skills ORDER BY learning_domain;

-- If those two results above look right: COMMIT;
-- If anything looks wrong:               ROLLBACK;
