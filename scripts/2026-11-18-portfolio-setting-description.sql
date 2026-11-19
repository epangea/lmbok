-- ============================================================
-- 2026-11-18, ai_include_learner_portfolio: description now covers the weekly story
--
-- Since 2026-11-15 the weekly job (backend/routes/weekly_report.py) reads this
-- setting as well: with it off, no weekly story paragraph is written for anyone
-- and the stats email still goes out. The label shown in admin Settings → AI was
-- seeded by 2026-11-01-learner-portfolio-setting.sql and only mentions session
-- prompts, so this updates the label. The value is not touched.
--
-- 2026-11-01-learner-portfolio-setting.sql seeds the row with
-- ON DUPLICATE KEY UPDATE updated_at = NOW(), which never rewrites an existing
-- description, so editing that file would not change a database that already has
-- the row. This script does, and for a database built by running the scripts in
-- date order it runs after that one and sets the final text.
--
-- Idempotent, safe to re-run. Changes 0 rows if the setting row does not exist
-- (the setting then runs on its default, on).
-- ============================================================

UPDATE platform_settings
SET description = 'Include the learner''s My Story profile and short excerpts of their recent reflections in session prompts and weekly story paragraphs (sent to the active AI provider). Off = assess-only continuity in sessions, no weekly stories (weekly email still sent).'
WHERE key_name = 'ai_include_learner_portfolio';

SELECT key_name, value, description FROM platform_settings
WHERE key_name = 'ai_include_learner_portfolio';
