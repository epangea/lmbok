-- 2026-08-22b-fix-dev-phases-age-ranges.sql
--
-- dev_phases.age_range (and name, for the ParentGuide/GuardianGuide labels)
-- were never updated when the onboarding phase card was corrected on
-- 2026-08-20 (2026.123, CLOSED) — that fix only touched the hardcoded
-- PHASES array in frontend/app.js, not this DB table. Nothing read this
-- table's age_range for display until today's GET /api/phases (added for
-- contribute.html), which is how the stale values surfaced.
--
-- Corrects dev_phases to match the agreed, already-live onboarding values:
--   prenascent: Expecting a child (ParentGuide) — Pregnancy
--   nascent:    Newborn & Infant (GuardianGuide) — Ages 0–2
--   child:      Child (GuardianGuide) — Ages 3–11
--   adolescent: Adolescent — Ages 12–19   (was 12–17)
--   adult:      Adult — Ages 20–59        (was 18–60)
--   elder:      Elder — Ages 60+          (was 61+)
--
-- Run the preflight SELECT first — if these are already correct (i.e. this
-- was fixed some other way already), the UPDATEs below are harmless no-ops,
-- but check first rather than assume.

-- Preflight: current state.
SELECT slug, name, age_range, sort_order FROM dev_phases ORDER BY sort_order;

-- The actual change.
UPDATE dev_phases SET name = 'Expecting a child (ParentGuide)', age_range = 'Pregnancy' WHERE slug = 'prenascent';
UPDATE dev_phases SET name = 'Newborn & Infant (GuardianGuide)', age_range = 'Ages 0–2'  WHERE slug = 'nascent';
UPDATE dev_phases SET name = 'Child (GuardianGuide)',            age_range = 'Ages 3–11' WHERE slug = 'child';
UPDATE dev_phases SET name = 'Adolescent',                       age_range = 'Ages 12–19' WHERE slug = 'adolescent';
UPDATE dev_phases SET name = 'Adult',                             age_range = 'Ages 20–59' WHERE slug = 'adult';
UPDATE dev_phases SET name = 'Elder',                             age_range = 'Ages 60+'   WHERE slug = 'elder';

-- Verify: should show the 6 corrected rows above, nothing else changed.
SELECT slug, name, age_range, sort_order FROM dev_phases ORDER BY sort_order;
