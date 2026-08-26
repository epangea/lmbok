-- 2026-08-25-add-dev-phases-age-bounds.sql
--
-- Adds numeric age_min/age_max to dev_phases. age_range ('0~2', '81+',
-- NULL for Light) is display text only — computing a learner's phase
-- from birth_year needs real numbers to compare against, not a string
-- to parse at request time. age_max NULL means unbounded (Wood, 81+).
-- Light keeps both NULL — it's resolved via is_expecting_parent, never
-- by age.
--
-- Preflight:
SELECT slug, age_range FROM dev_phases ORDER BY sort_order;

ALTER TABLE dev_phases
  ADD COLUMN age_min SMALLINT UNSIGNED NULL AFTER age_range,
  ADD COLUMN age_max SMALLINT UNSIGNED NULL AFTER age_min;

UPDATE dev_phases SET age_min = 0,  age_max = 2   WHERE slug = 'sandy-soil';
UPDATE dev_phases SET age_min = 3,  age_max = 5   WHERE slug = 'moist-soil';
UPDATE dev_phases SET age_min = 6,  age_max = 8   WHERE slug = 'humus-soil';
UPDATE dev_phases SET age_min = 9,  age_max = 11  WHERE slug = 'low-fire';
UPDATE dev_phases SET age_min = 12, age_max = 14  WHERE slug = 'medium-fire';
UPDATE dev_phases SET age_min = 15, age_max = 17  WHERE slug = 'high-fire';
UPDATE dev_phases SET age_min = 18, age_max = 22  WHERE slug = 'low-wind';
UPDATE dev_phases SET age_min = 23, age_max = 27  WHERE slug = 'high-wind';
UPDATE dev_phases SET age_min = 28, age_max = 38  WHERE slug = 'water';
UPDATE dev_phases SET age_min = 39, age_max = 59  WHERE slug = 'metal';
UPDATE dev_phases SET age_min = 60, age_max = 80  WHERE slug = 'stone';
UPDATE dev_phases SET age_min = 81, age_max = NULL WHERE slug = 'wood';
-- 'light' stays NULL/NULL — resolved via is_expecting_parent, not age.

-- Verify:
SELECT slug, age_range, age_min, age_max FROM dev_phases ORDER BY sort_order;
