-- 2026-08-20d-fix-null-leckos-after-real-deletion.sql
--
-- Run AFTER 2026-08-20b-STEP2-delete-non-mouseion-skills-v2.sql actually commits.
--
-- The first (broken) attempt at STEP2 rolled back silently, so when
-- 2026-08-20-mouseion-domains-migration.sql Part 2 ran, some LECKOs' derived
-- "primary skill" still resolved to one of the 34 skills that were supposed to
-- already be gone -- which weren't in that CASE's 48-name list, so its ELSE NULL
-- branch wiped their learning_domain to NULL instead of leaving it alone. 15 of
-- your 45 LECKOs got nulled this way.
--
-- This re-runs the same derivation (art_id -> primary skill -> domain), but
-- ONLY for LECKOs currently NULL, and now that the 34 skills are actually gone,
-- every art's primary-skill lookup will land on one of the real 48 -- so this
-- time every row gets a real domain, not NULL. Also fixed the ELSE branch to
-- preserve the existing value instead of nulling it, as a defensive improvement
-- for next time this ever runs.

-- Preview
SELECT l.id, l.title, l.learning_domain AS currently_null, sk.name AS derived_from_skill,
  CASE sk.name
    WHEN 'Critical Thinking' THEN 'Cognitive & Intellectual'
    WHEN 'Problem Solving' THEN 'Cognitive & Intellectual'
    WHEN 'Systems Thinking' THEN 'Cognitive & Intellectual'
    WHEN 'Memory & Retention' THEN 'Cognitive & Intellectual'
    WHEN 'Decision Making' THEN 'Cognitive & Intellectual'
    WHEN 'Project Management' THEN 'Cognitive & Intellectual'
    WHEN 'Visual Art' THEN 'Creative & Artistic'
    WHEN 'Music & Rhythm' THEN 'Creative & Artistic'
    WHEN 'Creative Writing' THEN 'Creative & Artistic'
    WHEN 'Drama & Theatre' THEN 'Creative & Artistic'
    WHEN 'Improvisation & Public Speaking' THEN 'Creative & Artistic'
    WHEN 'Craftsmanship & Making' THEN 'Creative & Artistic'
    WHEN 'Gross Motor' THEN 'Physical & Motor'
    WHEN 'Fine Motor' THEN 'Physical & Motor'
    WHEN 'Physical Fitness' THEN 'Physical & Motor'
    WHEN 'Dance & Movement' THEN 'Physical & Motor'
    WHEN 'Body Awareness' THEN 'Physical & Motor'
    WHEN 'First Aid & Nursing' THEN 'Physical & Motor'
    WHEN 'Collaboration' THEN 'Social & Relational'
    WHEN 'Conflict Resolution' THEN 'Social & Relational'
    WHEN 'Empathetic Leadership' THEN 'Social & Relational'
    WHEN 'Negotiation' THEN 'Social & Relational'
    WHEN 'Cultural Competence' THEN 'Social & Relational'
    WHEN 'Parenting & Caregiving' THEN 'Social & Relational'
    WHEN 'Active Reading' THEN 'Language & Communication'
    WHEN 'Active Listening' THEN 'Language & Communication'
    WHEN 'Storytelling' THEN 'Language & Communication'
    WHEN 'Debate & Argumentation' THEN 'Language & Communication'
    WHEN 'Foreign Language Acquisition' THEN 'Language & Communication'
    WHEN 'Rhetoric & Persuasion' THEN 'Language & Communication'
    WHEN 'Self-Awareness' THEN 'Emotional & Psychological'
    WHEN 'Emotional Regulation' THEN 'Emotional & Psychological'
    WHEN 'Empathy and Compassion' THEN 'Emotional & Psychological'
    WHEN 'Self-Efficacy' THEN 'Emotional & Psychological'
    WHEN 'Contemplative Practice' THEN 'Emotional & Psychological'
    WHEN 'Gratitude & Appreciation' THEN 'Emotional & Psychological'
    WHEN 'Learning How to Learn' THEN 'Meta-Learning'
    WHEN 'Self-Regulation' THEN 'Meta-Learning'
    WHEN 'Personal Values' THEN 'Meta-Learning'
    WHEN 'Curiosity and Exploration' THEN 'Meta-Learning'
    WHEN 'Vision, Mission and Purpose' THEN 'Meta-Learning'
    WHEN 'Mentorship & Teaching' THEN 'Meta-Learning'
    WHEN 'Digital Literacy' THEN 'Tools & Systems'
    WHEN 'Data Analysis & Statistics' THEN 'Tools & Systems'
    WHEN 'Design Thinking' THEN 'Tools & Systems'
    WHEN 'Philosophy & Ethics' THEN 'Tools & Systems'
    WHEN 'Permaculture' THEN 'Tools & Systems'
    WHEN 'Cooking & Nutrition' THEN 'Tools & Systems'
    ELSE l.learning_domain
  END AS new_domain
FROM leckos l
JOIN (
  SELECT art_id, MIN(skill_id) AS skill_id
  FROM arts_skills WHERE is_primary = 1 GROUP BY art_id
) primary_sk ON primary_sk.art_id = l.art_id
JOIN skills sk ON sk.id = primary_sk.skill_id
WHERE l.learning_domain IS NULL
ORDER BY l.title;

-- The fix
UPDATE leckos l
JOIN (
  SELECT art_id, MIN(skill_id) AS skill_id
  FROM arts_skills WHERE is_primary = 1 GROUP BY art_id
) primary_sk ON primary_sk.art_id = l.art_id
JOIN skills sk ON sk.id = primary_sk.skill_id
SET l.learning_domain = CASE sk.name
    WHEN 'Critical Thinking' THEN 'Cognitive & Intellectual'
    WHEN 'Problem Solving' THEN 'Cognitive & Intellectual'
    WHEN 'Systems Thinking' THEN 'Cognitive & Intellectual'
    WHEN 'Memory & Retention' THEN 'Cognitive & Intellectual'
    WHEN 'Decision Making' THEN 'Cognitive & Intellectual'
    WHEN 'Project Management' THEN 'Cognitive & Intellectual'
    WHEN 'Visual Art' THEN 'Creative & Artistic'
    WHEN 'Music & Rhythm' THEN 'Creative & Artistic'
    WHEN 'Creative Writing' THEN 'Creative & Artistic'
    WHEN 'Drama & Theatre' THEN 'Creative & Artistic'
    WHEN 'Improvisation & Public Speaking' THEN 'Creative & Artistic'
    WHEN 'Craftsmanship & Making' THEN 'Creative & Artistic'
    WHEN 'Gross Motor' THEN 'Physical & Motor'
    WHEN 'Fine Motor' THEN 'Physical & Motor'
    WHEN 'Physical Fitness' THEN 'Physical & Motor'
    WHEN 'Dance & Movement' THEN 'Physical & Motor'
    WHEN 'Body Awareness' THEN 'Physical & Motor'
    WHEN 'First Aid & Nursing' THEN 'Physical & Motor'
    WHEN 'Collaboration' THEN 'Social & Relational'
    WHEN 'Conflict Resolution' THEN 'Social & Relational'
    WHEN 'Empathetic Leadership' THEN 'Social & Relational'
    WHEN 'Negotiation' THEN 'Social & Relational'
    WHEN 'Cultural Competence' THEN 'Social & Relational'
    WHEN 'Parenting & Caregiving' THEN 'Social & Relational'
    WHEN 'Active Reading' THEN 'Language & Communication'
    WHEN 'Active Listening' THEN 'Language & Communication'
    WHEN 'Storytelling' THEN 'Language & Communication'
    WHEN 'Debate & Argumentation' THEN 'Language & Communication'
    WHEN 'Foreign Language Acquisition' THEN 'Language & Communication'
    WHEN 'Rhetoric & Persuasion' THEN 'Language & Communication'
    WHEN 'Self-Awareness' THEN 'Emotional & Psychological'
    WHEN 'Emotional Regulation' THEN 'Emotional & Psychological'
    WHEN 'Empathy and Compassion' THEN 'Emotional & Psychological'
    WHEN 'Self-Efficacy' THEN 'Emotional & Psychological'
    WHEN 'Contemplative Practice' THEN 'Emotional & Psychological'
    WHEN 'Gratitude & Appreciation' THEN 'Emotional & Psychological'
    WHEN 'Learning How to Learn' THEN 'Meta-Learning'
    WHEN 'Self-Regulation' THEN 'Meta-Learning'
    WHEN 'Personal Values' THEN 'Meta-Learning'
    WHEN 'Curiosity and Exploration' THEN 'Meta-Learning'
    WHEN 'Vision, Mission and Purpose' THEN 'Meta-Learning'
    WHEN 'Mentorship & Teaching' THEN 'Meta-Learning'
    WHEN 'Digital Literacy' THEN 'Tools & Systems'
    WHEN 'Data Analysis & Statistics' THEN 'Tools & Systems'
    WHEN 'Design Thinking' THEN 'Tools & Systems'
    WHEN 'Philosophy & Ethics' THEN 'Tools & Systems'
    WHEN 'Permaculture' THEN 'Tools & Systems'
    WHEN 'Cooking & Nutrition' THEN 'Tools & Systems'
    ELSE l.learning_domain
  END
WHERE l.learning_domain IS NULL;

-- Verify: should now be 0
SELECT COUNT(*) AS null_domain_leckos FROM leckos WHERE learning_domain IS NULL;
