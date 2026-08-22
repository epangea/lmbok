-- 2026-08-20-mouseion-domains-migration.sql
--
-- Retires the legacy subject-matter learning_domain taxonomy (Physiology,
-- Physics, etc. -- the '14 domains' from the old PHILOSOPHY.md section, of
-- which only 11 values were ever actually used by leckos rows) in favor of
-- the 8 Mouseion domains, which is the ONLY domain taxonomy that should
-- exist anywhere on the platform going forward (per 2026-08-20 decision --
-- the other rooted taxonomy is the 15 Arts, untouched by this migration).
--
-- PART 1: skills.learning_domain
-- Deterministic remap by skill NAME. The name->domain mapping below is
-- mirrored EXACTLY from MOUSEION_DOMAIN_SKILLS in backend/routes/learners.py
-- (itself mirrored from frontend/app.js's _DOMS in Mouseion()) -- these three
-- copies must be kept in sync if the grid ever changes; there is currently
-- no single shared source file for it, which is worth fixing separately.
--
-- SAFE: this doesn't change any matching *behavior* in generate.py's skill-
-- reuse fallback tier (learning_domain + skill_type match) -- it groups
-- skills into 8 broader families instead of the old 14 narrower subject
-- buckets, which if anything gives that fallback tier MORE candidates to
-- work with, not fewer. See generate.py lines ~78-83 for that logic.
--
-- Run the SELECT first to review before the UPDATE.

-- Preview: what will change
SELECT id, name, learning_domain AS old_domain, CASE name
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
  ELSE learning_domain END AS new_domain
FROM skills
ORDER BY new_domain, name;

-- Preview: any skill name NOT covered by the 48-skill Mouseion grid
-- (should return zero rows on a healthy DB; if not, decide what those
-- skills' domain should be before running the UPDATE below)
SELECT id, name, learning_domain FROM skills WHERE name NOT IN (
  'Critical Thinking',
  'Problem Solving',
  'Systems Thinking',
  'Memory & Retention',
  'Decision Making',
  'Project Management',
  'Visual Art',
  'Music & Rhythm',
  'Creative Writing',
  'Drama & Theatre',
  'Improvisation & Public Speaking',
  'Craftsmanship & Making',
  'Gross Motor',
  'Fine Motor',
  'Physical Fitness',
  'Dance & Movement',
  'Body Awareness',
  'First Aid & Nursing',
  'Collaboration',
  'Conflict Resolution',
  'Empathetic Leadership',
  'Negotiation',
  'Cultural Competence',
  'Parenting & Caregiving',
  'Active Reading',
  'Active Listening',
  'Storytelling',
  'Debate & Argumentation',
  'Foreign Language Acquisition',
  'Rhetoric & Persuasion',
  'Self-Awareness',
  'Emotional Regulation',
  'Empathy and Compassion',
  'Self-Efficacy',
  'Contemplative Practice',
  'Gratitude & Appreciation',
  'Learning How to Learn',
  'Self-Regulation',
  'Personal Values',
  'Curiosity and Exploration',
  'Vision, Mission and Purpose',
  'Mentorship & Teaching',
  'Digital Literacy',
  'Data Analysis & Statistics',
  'Design Thinking',
  'Philosophy & Ethics',
  'Permaculture',
  'Cooking & Nutrition'
);

-- The actual update
UPDATE skills SET learning_domain = CASE name
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
  ELSE learning_domain
END;


-- PART 2: leckos.learning_domain
-- LECKOs have no direct skill_id -- only art_id. Derived via that art's
-- primary skill (arts_skills.is_primary=1), mapped to a Mouseion domain by
-- skill NAME (same case mapping as PART 1, applied independently here so
-- this part doesn't depend on PART 1 having run first). Where an art has
-- more than one primary skill, the lowest skill_id is the deterministic
-- tiebreaker. LECKOs whose art has zero primary skills are left untouched
-- (see the second preview query) and need a manual look.
--
-- This does NOT change the contribute-form submission path itself -- that's
-- a separate frontend fix (contribute.html's freeform 'f-domain' text input
-- -> a <select> of the 8 domains), shipped alongside this migration, so new
-- submissions can't reintroduce the retired taxonomy.

-- Preview: what will change
SELECT l.id, l.title, l.learning_domain AS old_domain, sk.name AS derived_from_skill,
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
    ELSE NULL
  END AS new_domain
FROM leckos l
JOIN (
  SELECT art_id, MIN(skill_id) AS skill_id
  FROM arts_skills WHERE is_primary = 1 GROUP BY art_id
) primary_sk ON primary_sk.art_id = l.art_id
JOIN skills sk ON sk.id = primary_sk.skill_id
ORDER BY new_domain, l.title;

-- Preview: LECKOs whose art has no primary skill (left untouched by the UPDATE below)
SELECT l.id, l.title, l.art_id, l.learning_domain
FROM leckos l
LEFT JOIN arts_skills ars ON ars.art_id = l.art_id AND ars.is_primary = 1
WHERE ars.art_id IS NULL;

-- The actual update
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
    ELSE NULL
  END
WHERE l.art_id IS NOT NULL;

