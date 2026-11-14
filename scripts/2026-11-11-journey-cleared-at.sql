-- ============================================================
-- 2026-11-11, journey export and delete (work plan step 2)
--
-- Adds learners.journey_cleared_at: set when a learner deletes their journey
-- (DELETE /api/learners/me/journey). NULL means they never did.
--
-- It lets the code that can rebuild journey content leave a deleted journey
-- deleted:
--   * backend/journey.py: after a delete, first_in_art and all_families are
--     not fired again for Arts the learner had completed sessions in before
--     the delete.
--   * backend/routes/weekly_report.py: the weekly story only reads sessions
--     completed after the delete.
--   * scripts/backfill_journey.py: skips learners who have a marker.
--
-- !! RUN THIS BEFORE restarting freqlearn with the new code, and before the
-- !! next weekly report run: both read the column.
--
-- UTC, like sessions.completed_at (the code writes datetime.now(timezone.utc)).
--
-- Purely additive and re-runnable (IF NOT EXISTS).
-- Rollback (after reverting the code):
--   ALTER TABLE learners DROP COLUMN IF EXISTS journey_cleared_at;
-- ============================================================

ALTER TABLE learners
    ADD COLUMN IF NOT EXISTS journey_cleared_at DATETIME NULL DEFAULT NULL;
