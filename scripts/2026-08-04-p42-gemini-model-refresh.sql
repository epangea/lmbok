-- FreqLearn — 2026-08-04 (P42 follow-on: Gemini model refresh)
--
-- The 2026-07-29b migration set ai_model_gemini_large/small to
-- 'gemini-2.5-flash' / 'gemini-2.5-flash-lite' -- Google's own recommended
-- replacements at the time. Confirmed broken live via e2e_org_polis.sh's
-- new Part E (2026-08-04): every call now 404s with "This model
-- models/gemini-2.5-flash is no longer available" -- Google appears to be
-- retiring the 2.5 line ahead of its own documented Oct 16, 2026 shutdown
-- date (multiple independent reports on Google's own developer forum as
-- of this writing). Since the admin dropdown never actually exposed
-- 'gemini' as a selectable provider until this same session's admin.html
-- fix, nobody could have manually changed these away from the P41
-- default in the meantime -- so this is a straight value correction, not
-- a guess about overwriting an admin's real choice.
--
-- New defaults: gemini-3.5-flash (large) / gemini-3.1-flash-lite (small)
-- -- both confirmed on Gemini's current free tier as of this writing.
-- Both remain admin-editable in Admin > Settings > AI generation exactly
-- as before; this migration only touches the stored value, not the
-- column/setting definition.
--
-- Idempotent: safe to re-run. Deliberately conditional (WHERE value = the
-- known-broken 2026-07-29b default) rather than an unconditional
-- overwrite, so a future manual change away from these new defaults won't
-- get silently clobbered by re-running this file.

UPDATE platform_settings
SET value = 'gemini-3.5-flash'
WHERE key_name = 'ai_model_gemini_large'
  AND value = 'gemini-2.5-flash';

UPDATE platform_settings
SET value = 'gemini-3.1-flash-lite'
WHERE key_name = 'ai_model_gemini_small'
  AND value = 'gemini-2.5-flash-lite';
