-- ============================================================
-- 2026-11-01 — ai_include_learner_portfolio platform setting
--
-- Adds the toggle for the learner-portfolio additions to the /session
-- prompt (generate.py / prior_session_context.py):
--   * LEARNER PORTFOLIO block — learners.learner_profile (Prosopon /
--     My Story life-CV), capped at 1500 chars.
--   * Journey additions to the LEARNER CONTINUITY block — short excerpts
--     of the learner's own challenge/reflect responses, and their last 3
--     completed sessions on other arts.
--
-- Behaviour when the row is absent: backend/ai_client.py::_AI_DEFAULTS
-- supplies "true", so running this migration is NOT required for the
-- feature to work — it only makes the toggle visible/editable in the
-- admin Settings → AI panel.
--
-- Privacy note: when enabled, this learner-authored text is sent to
-- whichever AI provider serves the request (Groq / Gemini / Ollama),
-- on every session generation. Turn off to fall back to the 2026-07-07
-- continuity block (assess data only, same art + phase).
--
-- Rollback:
--   DELETE FROM platform_settings WHERE key_name = 'ai_include_learner_portfolio';
-- (or set the value to 'false' for a no-redeploy kill switch)
--
-- Idempotent — safe to re-run.
-- ============================================================

INSERT INTO platform_settings (key_name, value, description, category) VALUES
    ('ai_include_learner_portfolio', 'true',
     'Include the learner''s My Story profile and short excerpts of their recent reflections in the session prompt (sent to the active AI provider). Off = assess-only continuity.',
     'ai')
ON DUPLICATE KEY UPDATE updated_at = NOW();

SELECT key_name, value, category FROM platform_settings
WHERE key_name = 'ai_include_learner_portfolio';
