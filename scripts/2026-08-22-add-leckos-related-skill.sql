-- 2026-08-22-add-leckos-related-skill.sql
--
-- Adds a new nullable `related_skill` column to `leckos`, populated by the
-- optional second dropdown on contribute.html's LECKO submission form
-- (Step 2 "The context" — domain -> skill, cascading from the 8 Mouseion
-- domains via the new GET /api/mouseion-domains endpoint). Free-text at the
-- DB level (not a foreign key to `skills.id` — leckos have no skill_id
-- column at all, only art_id/phase_id), but the frontend only ever submits
-- one of the 48 known Mouseion skill names from mouseion_domains.py.
--
-- Purely additive, nullable, no backfill needed — every existing row will
-- just have NULL here, which the app already treats as "not provided."
--
-- Run the preflight SELECTs first to confirm current state before the ALTER.

-- Preflight: confirm current leckos schema and row count.
DESCRIBE leckos;
SELECT COUNT(*) AS total_leckos FROM leckos;

-- The actual change.
ALTER TABLE leckos
  ADD COLUMN related_skill VARCHAR(120) NULL AFTER learning_domain;

-- Verify: column exists, all existing rows NULL as expected.
DESCRIBE leckos;
SELECT COUNT(*) AS rows_with_related_skill FROM leckos WHERE related_skill IS NOT NULL;
