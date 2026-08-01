-- FreqLearn — 2026-07-29b (P41 follow-up)
-- Adds Gemini as a third free AI provider, alongside Groq and Ollama.
-- Charbel's current server is too small to run Ollama locally; Gemini
-- (Google AI Studio's free tier, no card required) is a second independent
-- cloud provider in the meantime, and Ollama slots in unchanged whenever
-- the server is upgraded — see ai_client.py's module docstring.
--
--   ai_model_gemini_large  — Gemini model for content-quality calls
--   ai_model_gemini_small  — Gemini model for lightweight/classification calls
--
-- Requires GEMINI_API_KEY in backend/.env (get one free, no card, at
-- aistudio.google.com) — that's an env var, not a platform_setting, same
-- reasoning as GROQ_API_KEY/OLLAMA_URL (infra/secret, not model/engine
-- choice).
--
-- Idempotent: safe to re-run.

INSERT INTO platform_settings (key_name, value, category, description)
VALUES
  ('ai_model_gemini_large', 'gemini-2.5-flash', 'ai',
   'Gemini model used for content-quality AI calls (session generation, companions, guiding star, needs-parsing, bioregion drafts).'),
  ('ai_model_gemini_small', 'gemini-2.5-flash-lite', 'ai',
   'Gemini model used for lightweight/classification AI calls (Scavenger, bioregion portrait synthesis).')
ON DUPLICATE KEY UPDATE
  category = VALUES(category);
  -- value intentionally NOT overwritten on re-run, in case an admin already changed it
