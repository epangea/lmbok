-- 2026-08-20b-STEP2-delete-non-mouseion-skills-v2.sql
--
-- v2, 2026-08-20: the first version of this file wrote "COMMIT;"/"ROLLBACK;" as
-- SQL COMMENTS (prefixed with --) instead of real statements, intending someone
-- to type one by hand after reviewing the verification SELECTs. Run in batch
-- mode (mysql freqlearn < file.sql), the transaction just... never committed --
-- MariaDB implicitly rolled it back when the client disconnected at EOF. The 34
-- skills were NOT actually deleted the first time. This version issues a real
-- COMMIT unconditionally at the end, since STEP1's preview and the arts-primary-
-- skill check have already been reviewed and came back clean.
--
-- You already have a backup from before the first attempt -- this doesn't need
-- a fresh one, but doesn't hurt either.

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

SELECT COUNT(*) AS remaining_skill_count FROM skills;
SELECT DISTINCT learning_domain FROM skills ORDER BY learning_domain;

COMMIT;
