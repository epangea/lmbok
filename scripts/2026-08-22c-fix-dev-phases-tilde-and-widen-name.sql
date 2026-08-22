-- 2026-08-22c-fix-dev-phases-tilde-and-widen-name.sql
--
-- Supersedes 2026-08-22b-fix-dev-phases-age-ranges.sql, which failed at line
-- 26 ("Data too long for column 'name'") and committed nothing — dev_phases
-- is untouched by that attempt. Root cause of that failure: `name` was
-- VARCHAR(30), too narrow for the full ParentGuide/GuardianGuide labels.
-- This script widens it first, then applies the correct values.
--
-- Also corrects course on the age-range numbers themselves: commit 3ef1da3
-- ("Onboarding redesign...") added the ParentGuide/GuardianGuide labels to
-- frontend/app.js's PHASES array and claimed in its message that age ranges
-- were updated to 12-19/20-59/60+, but the actual diff never touched the
-- age numbers — only the name labels changed. So app.js, dev_phases, and
-- everywhere else have been quietly showing the old 12-17/18-60/61+ boundary
-- this whole time despite being documented as fixed. Confirmed by git show
-- 3ef1da3 -- frontend/app.js. This script (paired with the app.js edit made
-- alongside it) is the actual, complete fix.
--
-- Per Charbel: ages use a tilde (~) rather than a hyphen, deliberately, so
-- they read as approximate guidance rather than rigid cutoffs. Applied here
-- consistently to all six phases, not just the three that are numerically
-- changing.
--
-- Run the preflight SELECT first to confirm current (broken) state.

-- Preflight: current state.
SELECT slug, name, age_range, sort_order FROM dev_phases ORDER BY sort_order;

-- Widen name to fit the full ParentGuide/GuardianGuide labels.
ALTER TABLE dev_phases MODIFY COLUMN name VARCHAR(50) NOT NULL;

-- The actual values.
UPDATE dev_phases SET name = 'Expecting a child (ParentGuide)',   age_range = 'Pregnancy'  WHERE slug = 'prenascent';
UPDATE dev_phases SET name = 'Newborn & Infant (GuardianGuide)',  age_range = 'Ages 0~2'   WHERE slug = 'nascent';
UPDATE dev_phases SET name = 'Child (GuardianGuide)',             age_range = 'Ages 3~11'  WHERE slug = 'child';
UPDATE dev_phases SET name = 'Adolescent',                        age_range = 'Ages 12~19' WHERE slug = 'adolescent';
UPDATE dev_phases SET name = 'Adult',                             age_range = 'Ages 20~59' WHERE slug = 'adult';
UPDATE dev_phases SET name = 'Elder',                             age_range = 'Ages 60+'   WHERE slug = 'elder';

-- Verify: should show the 6 corrected rows above, nothing else changed.
SELECT slug, name, age_range, sort_order FROM dev_phases ORDER BY sort_order;
