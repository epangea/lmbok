-- P11: Synergy — AI-driven org needs matching
-- Run this against the live DB before deploying the corresponding code.
--
-- PREFLIGHT — run these first and eyeball the output before ALTERing anything:
--   DESCRIBE opportunity_listings;
--   DESCRIBE opportunity_matches;
-- Confirm opportunity_matches.learner_status is currently:
--   ENUM('pending','interested','declined','connected','withdrawn')
-- If it differs, STOP and adjust the ENUM list below to match reality first.

-- 1. Org's free-text needs box + the AI-parsed skill targets derived from it.
ALTER TABLE opportunity_listings
    ADD COLUMN needs_text TEXT NULL AFTER description,
    ADD COLUMN needs_skill_targets JSON NULL AFTER needs_text;

-- 2. Where a match came from, and when the org last pinged the learner about it.
ALTER TABLE opportunity_matches
    ADD COLUMN origin ENUM('learner_initiated','ai_suggested') NOT NULL DEFAULT 'learner_initiated' AFTER listing_id,
    ADD COLUMN notified_at DATETIME NULL AFTER matched_at;

-- 3. Two new learner_status values for the AI-suggested flow:
--      'suggested' — AI ranked them into an org's top 10; org sees them anonymized, hasn't invited yet
--      'invited'   — org sent a notification; learner hasn't responded yet
--    Existing values are preserved verbatim (do not drop/reorder them).
ALTER TABLE opportunity_matches
    MODIFY COLUMN learner_status
        ENUM('pending','interested','declined','connected','withdrawn','suggested','invited')
        NOT NULL DEFAULT 'pending';

-- POSTFLIGHT — confirm:
--   DESCRIBE opportunity_listings;
--   DESCRIBE opportunity_matches;
-- and that existing rows still read learner_status/org_status unchanged
-- (SELECT learner_status, COUNT(*) FROM opportunity_matches GROUP BY learner_status;)
