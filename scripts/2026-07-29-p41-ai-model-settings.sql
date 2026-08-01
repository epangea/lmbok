-- FreqLearn — 2026-07-29 (P41)
-- Adds the settings that make AI model choice fully admin-configurable,
-- replacing model names that used to be hardcoded (llama-3.3-70b-versatile)
-- or scattered across env vars with silently different fallback defaults
-- across six different files. See ai_client.py's module docstring for the
-- full story.
--
--   ai_model_groq_large    — Groq model for content-quality calls
--                            (session generation, Socratic companions,
--                            guiding star, needs-parsing, bioregion drafts)
--   ai_model_groq_small    — Groq model for lightweight/classification calls
--                            (Scavenger, bioregion portrait synthesis)
--   ai_model_ollama_large  — same split for Ollama, if/when reinstalled
--   ai_model_ollama_small
--
-- Defaults below are the two models Groq is pointing existing free-tier
-- accounts toward as llama-3.3-70b-versatile / llama-3.1-8b-instant are
-- decommissioned 2026-08-16 (see PROJECT_MASTER PART 23). Change these in
-- Admin > Settings > AI generation any time — no restart, no deploy needed.
--
-- Idempotent: safe to re-run.

INSERT INTO platform_settings (key_name, value, category, description)
VALUES
  ('ai_model_groq_large', 'openai/gpt-oss-120b', 'ai',
   'Groq model used for content-quality AI calls (session generation, companions, guiding star, needs-parsing, bioregion drafts).'),
  ('ai_model_groq_small', 'openai/gpt-oss-20b', 'ai',
   'Groq model used for lightweight/classification AI calls (Scavenger, bioregion portrait synthesis).'),
  ('ai_model_ollama_large', 'llama3.1:8b', 'ai',
   'Ollama model used for content-quality AI calls, if the admin selects Ollama as the provider.'),
  ('ai_model_ollama_small', 'llama3.1:8b', 'ai',
   'Ollama model used for lightweight/classification AI calls, if the admin selects Ollama as the provider.')
ON DUPLICATE KEY UPDATE
  category = VALUES(category);
  -- value intentionally NOT overwritten on re-run, in case an admin already changed it
