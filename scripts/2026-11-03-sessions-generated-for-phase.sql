-- ============================================================
-- 2026-11-03, sessions.generated_for_phase_id
--
-- Live AI-generated and per-learner library-served session rows deliberately
-- have dev_phase_id = NULL (generate.py): a non-NULL dev_phase_id makes a row
-- eligible for the shared library, and live sessions embed one learner's
-- interests / portfolio. The side effect: the admin session browser showed a
-- blank phase for every such row and the phase the session was generated for
-- was not stored anywhere.
--
-- This adds an INFORMATIONAL column for it. It is never read by the library /
-- reuse selection (that is still dev_phase_id). Admin list/detail show
-- COALESCE(dev_phase_id, generated_for_phase_id).
--
-- !! RUN THIS BEFORE restarting freqlearn with the new code. The ORM selects
-- !! the column on every sessions query; without it every Session query fails.
--
-- Existing rows stay NULL (the phase they were generated for was never
-- recorded and cannot be reconstructed), so old live sessions keep showing a
-- blank phase; new ones fill in.
--
-- Rollback: ALTER TABLE sessions DROP COLUMN generated_for_phase_id;
-- (after reverting the code). Idempotent, safe to re-run.
-- ============================================================

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS generated_for_phase_id INT NULL DEFAULT NULL AFTER dev_phase_id;

SELECT COUNT(*) AS sessions_total,
       SUM(generated_for_phase_id IS NOT NULL) AS with_generated_for_phase
FROM sessions;
