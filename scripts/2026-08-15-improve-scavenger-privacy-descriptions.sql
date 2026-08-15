-- 2026-08-15-improve-scavenger-privacy-descriptions.sql
--
-- Data-only: expands the Scavenger and Privacy & access category
-- descriptions in platform_settings to the same explanatory level as
-- the 'ai' category's descriptions (which got a detail pass during P41,
-- 2026-07-29). The original 2026-06-27 seed wrote these as short labels
-- rather than explanations -- fine at launch, not enough for a new
-- admin encountering the Settings page cold. No code or UI change
-- required; description is read-only display text in AdminSettings().
--
-- Safe to re-run: plain UPDATE by key_name, not an insert, so there's
-- no ON DUPLICATE KEY concern. Does NOT touch `value` -- won't clobber
-- anything an admin has configured.

UPDATE platform_settings SET description =
  'Display name shown in the From: field of outreach emails sent to prospective partner organizations, e.g. "OneHouse Outreach Team". Leave blank to fall back to the raw sender email.'
  WHERE key_name = 'scavenger_sender_name';

UPDATE platform_settings SET description =
  'Mailbox outreach emails are actually sent from (the From: address). Must be a real, monitored inbox -- any reply from a contacted organization lands here, not in the admin panel.'
  WHERE key_name = 'scavenger_sender_email';

UPDATE platform_settings SET description =
  'When ON, an outreach draft is emailed automatically as soon as the AI scavenger generates it, with no admin review. OFF (default) queues every draft as "pending" in the Outreach section for a human to read, optionally edit, and send manually.'
  WHERE key_name = 'scavenger_auto_send';

UPDATE platform_settings SET description =
  'Requires a new learner to click the verification link in their welcome email before they can log in. Turning this OFF allows immediate login right after signup -- only intended for controlled testing, not production use.'
  WHERE key_name = 'require_email_verification';

UPDATE platform_settings SET description =
  'Lets learners permanently delete their own account and progress data themselves from their profile, without needing to ask an admin to do it for them.'
  WHERE key_name = 'allow_learner_data_deletion';

UPDATE platform_settings SET description =
  'Controls whether an organization can see a learner''s real name in an anonymized match candidate list before that learner has accepted the match. OFF (default) keeps names hidden until mutual reveal, preserving the consent-first matching model (see P11).'
  WHERE key_name = 'show_learner_names_to_orgs';

UPDATE platform_settings SET description =
  'Lets learners submit LECKO (learning resource) contributions without their name or profile being attached to the submission.'
  WHERE key_name = 'allow_anonymous_leckos';

SELECT key_name, description FROM platform_settings WHERE category IN ('scavenger', 'privacy');
