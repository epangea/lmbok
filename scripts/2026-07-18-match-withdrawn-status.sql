-- ============================================================
-- 2026-07-18 — add 'withdrawn' to opportunity_matches.learner_status
--
-- Why: matching.py's withdraw_interest() now sets learner_status =
-- "withdrawn" instead of hard-deleting the OpportunityMatch row
-- (hard-delete violated the messages.match_id FK whenever a message
-- thread existed — see MAINTENANCE.md gotcha table, 2026-07-18).
-- The live enum was ('pending','interested','declined','connected')
-- with no 'withdrawn' option, so the UPDATE failed with
-- "Data truncated for column 'learner_status'" (errno 1265).
--
-- This is a purely additive enum change — adding an option doesn't
-- touch any existing row's value. Safe to run any time.
-- ============================================================

-- ---- PART A: read-only preflight — confirm current state before altering ----
DESCRIBE opportunity_matches;
SELECT learner_status, COUNT(*) FROM opportunity_matches GROUP BY learner_status;

-- ---- PART B: the actual change ----
ALTER TABLE opportunity_matches
    MODIFY COLUMN learner_status
    ENUM('pending','interested','declined','connected','withdrawn')
    DEFAULT 'pending';

-- ---- Verify ----
DESCRIBE opportunity_matches;
