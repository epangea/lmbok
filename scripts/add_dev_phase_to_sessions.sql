-- ============================================================
-- FreqLearn — add_dev_phase_to_sessions.sql
-- Adds dev_phase_id to sessions so the reuse branch can serve
-- phase-appropriate content to child/adolescent/elder learners.
-- NULL = untagged (pre-seeded adult content, acceptable fallback).
-- Run: mysql -u freqlearn -p freqlearn < add_dev_phase_to_sessions.sql
-- ============================================================

ALTER TABLE sessions
  ADD COLUMN dev_phase_id INT NULL DEFAULT NULL
  AFTER art_id;

-- Tag existing sessions as adult (phase_id=4 = adult in most seeds;
-- verify with: SELECT id, slug FROM dev_phases;)
-- Leave NULL if unsure — NULL sessions are served as fallback to any phase.

-- Verify
SELECT COUNT(*) AS total_sessions,
       SUM(dev_phase_id IS NULL) AS untagged,
       SUM(dev_phase_id IS NOT NULL) AS tagged
FROM sessions;
