-- FreqLearn — 2026-07-15
-- Adds the settings needed to fix the AI-first regression (BRIEFING 2026-07-09):
--   ai_inline_reuse_enabled      — OFF by default. When true, re-enables the
--                                  old "serve a stored session if >=3 exist"
--                                  shortcut in generate.py (useful as an
--                                  emergency cost-control switch).
--   ai_library_failure_threshold — consecutive AI failures before the
--                                  circuit breaker trips into library mode.
--   ai_library_mode_ttl          — how long library mode lasts once tripped,
--                                  in seconds (600 = 10 minutes).
--
-- Idempotent: safe to re-run.

INSERT INTO platform_settings (key_name, value, category, description)
VALUES
  ('ai_inline_reuse_enabled', 'false', 'ai',
   'Serve a stored session instead of calling AI whenever 3+ exist for the art. OFF by default — AI is tried first.'),
  ('ai_library_failure_threshold', '3', 'ai',
   'Consecutive AI failures before the circuit breaker switches to library-only mode.'),
  ('ai_library_mode_ttl', '600', 'ai',
   'Seconds the circuit breaker stays in library-only mode after tripping (600 = 10 min).')
ON DUPLICATE KEY UPDATE
  category = VALUES(category);
  -- value intentionally NOT overwritten on re-run, in case an admin already changed it
