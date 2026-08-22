-- 2026-08-20c-check-arts-losing-all-primary-skills.sql
-- Read-only. Run BEFORE STEP2 -- checks whether any of the 15 Arts would end up
-- with ZERO primary skills after the 34 non-Mouseion skills are deleted, which
-- would break the LECKO-domain derivation in 2026-08-20-mouseion-domains-
-- migration.sql Part 2 (it needs every art to have at least one primary skill).

SELECT a.id, a.name AS art_name,
  COUNT(ars.skill_id) AS primary_skills_total,
  SUM(CASE WHEN s.name IN (
    'Abstract Reasoning','Attention & Focus','Research & Inquiry','Mathematical Literacy','Scientific Method',
    'Imagination & Conceptual Thinking','Writing','Non-Verbal Communication','Digital Communication',
    'Stress Management','Motivation & Self-Drive','Boundary Setting','Sports & Athletic Skills',
    'Instrument Playing','Nutrition & Health Literacy','Community Building','Networking & Relationship Building',
    'Photography & Film','Programming & Coding','Cybersecurity Awareness','AI & Automation Literacy',
    'Engineering & Systems Design','Financial Literacy','Household & DIY Management','Time & Energy Management',
    'Environmental Stewardship','Ethical Reasoning','Mindfulness & Contemplation','Meaning-Making & Purpose',
    'Philosophical Inquiry','Spiritual Practice','Feedback Integration','Habit Formation','Adaptability & Flexibility'
  ) THEN 1 ELSE 0 END) AS would_be_removed
FROM arts a
JOIN arts_skills ars ON ars.art_id = a.id AND ars.is_primary = 1
JOIN skills s ON s.id = ars.skill_id
GROUP BY a.id, a.name
HAVING primary_skills_total = would_be_removed
ORDER BY a.name;
