-- 2026-08-29-split-weekly-report-opt-out.sql
--
-- Splits the weekly progress-digest email (scripts/weekly_report.py) off
-- of LearnerPreferences.newsletter_opt_out into its own column, so a
-- learner can opt out of admin newsletters without also losing their
-- weekly stats digest, or vice versa. Previously both were gated by the
-- same flag (2026-08-29, same day -- see PROJECT.md).
--
-- Existing learners default to weekly_report_opt_out = 0 (still
-- subscribed) regardless of their current newsletter_opt_out value --
-- nobody who was getting weekly reports loses them from this migration
-- alone; they can opt out going forward via the new Preferences toggle.

ALTER TABLE learner_preferences
  ADD COLUMN weekly_report_opt_out TINYINT(1) NOT NULL DEFAULT 0;

-- Verify:
DESCRIBE learner_preferences;
