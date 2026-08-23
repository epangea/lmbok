-- ============================================================
-- 2026-08-23b — Newsletter: audience filters + per-send exclusions
--
-- Follow-up to 2026-08-23-newsletter.sql (already run/live). Adds two
-- new nullable TEXT columns to the existing newsletters table -- no
-- new table, no change to any row already in it (NULL for every
-- existing newsletter, meaning "no filter, no exclusions", same
-- behavior as before this migration).
--
--   audience_filters      — JSON object, e.g. {"language":"vi","phase_id":3,"bioregion":"..."}
--   excluded_learner_ids  — JSON array of learner ids, e.g. [12, 47]
--
-- Both are read back and re-applied only at /send time (see admin.py);
-- neither is ever queried against directly, so plain TEXT is enough --
-- no need for JSON-typed columns or a normalized child table.
-- ============================================================

-- ---- PART A: read-only preflight ----
DESCRIBE newsletters;

-- ---- PART B: add the two columns ----
START TRANSACTION;

ALTER TABLE newsletters
    ADD COLUMN audience_filters TEXT NULL,
    ADD COLUMN excluded_learner_ids TEXT NULL;

COMMIT;

-- ---- Verify — don't trust this script's own exit code ----
DESCRIBE newsletters;
SELECT COUNT(*) AS total_newsletters,
       SUM(audience_filters IS NULL) AS null_filters,
       SUM(excluded_learner_ids IS NULL) AS null_exclusions
FROM newsletters;
