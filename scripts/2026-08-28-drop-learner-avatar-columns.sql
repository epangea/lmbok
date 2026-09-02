-- 2026-08-28-drop-learner-avatar-columns.sql
--
-- Removes learners.avatar_emoji and learners.avatar_color. The learner-
-- customizable emoji/color avatar (picked in Preferences, or randomized
-- at onboarding since 2026-08-20) has been fully replaced across the
-- platform by the dev-phase icon/color (dev_phases.icon/dev_phases.color,
-- already single-sourced via /phases and stored per-learner on
-- learners.phase_id). Nothing reads avatar_emoji/avatar_color anymore as
-- of this migration -- nav header, org match lists, and Polis
-- comments/proposals all now render phase icon/color instead.
--
-- NOT the same thing as "avatar stage" (Seed->Sprout->...->Ecosystem, the
-- XP/breadth-based growth path in utils.py/app.js) -- that's an unrelated
-- feature that happens to share the word "avatar" and is untouched here.
--
-- Preflight (sanity check before dropping -- confirm no unexpectedly
-- customized values that might matter to someone):
SELECT COUNT(*) AS total_learners,
       COUNT(DISTINCT avatar_emoji) AS distinct_emoji,
       COUNT(DISTINCT avatar_color) AS distinct_color
  FROM learners;

ALTER TABLE learners
  DROP COLUMN avatar_emoji,
  DROP COLUMN avatar_color;

-- Verify:
DESCRIBE learners;
