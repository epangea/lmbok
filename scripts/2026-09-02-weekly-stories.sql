-- ============================================================
-- 2026-09-02 — add weekly_stories table
--
-- Why: weekly_report.py already distils each learner's week of
-- challenge/reflect answers + companion verdicts into a short
-- "this week's growth" paragraph for the email (see
-- _weekly_story_paragraph()), but that paragraph was ephemeral —
-- generated fresh each send and never kept. This table persists
-- one row per learner per report run, so Portfolio can show a
-- reverse-chronological history of past weekly paragraphs
-- (bank-statement style), distinct from learners.learner_profile
-- (My Story's Life-CV), which is a merged/compressed *current*
-- snapshot with no history of its own — see update_learner_profile()
-- in generate.py ("Do not simply append; distil").
--
-- Deliberately decoupled from learner_preferences.weekly_report_opt_out:
-- that flag only controls whether the email is sent, not whether the
-- learner's own progress gets recorded, so weekly_report.py writes a
-- row here for every active learner regardless of opt-out.
--
-- week_start is the run's window-start date (CURDATE() - 7), shared
-- by every row written in the same run; UNIQUE(learner_id, week_start)
-- makes a re-run of the same week idempotent (ON DUPLICATE KEY UPDATE
-- in application code) rather than producing duplicate entries.
--
-- Purely additive, new table. Safe to run any time.
-- ============================================================

-- ---- PART A: read-only preflight — confirm no existing table ----
SHOW TABLES LIKE 'weekly_stories';

-- ---- PART B: the actual change ----
CREATE TABLE weekly_stories (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id   INT UNSIGNED NOT NULL,
    week_start   DATE         NOT NULL,
    paragraph    TEXT         NOT NULL,
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    UNIQUE KEY uq_learner_week (learner_id, week_start),
    INDEX idx_learner_stories (learner_id, week_start)
) ENGINE=InnoDB;

-- ---- Verify ----
DESCRIBE weekly_stories;
