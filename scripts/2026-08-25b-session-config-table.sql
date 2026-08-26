-- 2026-08-25b-session-config-table.sql
--
-- New table for session-generation config values that should live in one
-- place rather than be duplicated across generate.py / seed_sessions.py.
-- First use: the standing caveat appended to every phase pedagogy block
-- (Step C, 2026-08-25) -- previously identical text repeated 13 times
-- across 3 files, now one row.
--
-- Deliberately NOT admin-editable via UI yet -- that's a larger feature
-- (full session-config admin panel + change-ledger for tamper tracking)
-- planned as a combined later task. This table is forward-compatible
-- with that: config_key/config_value/description is exactly the shape
-- an admin edit form would need, so nothing here gets thrown away when
-- that feature is built -- only a UI and a ledger get added on top.
--
-- For now, edit config_value directly via SQL when a value needs to
-- change.

CREATE TABLE session_config (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    config_key   VARCHAR(64) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    description  TEXT,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO session_config (config_key, config_value, description) VALUES
('phase_guidance_disclaimer',
 'This is a starting point drawn from general research on this phase, not a rule about this specific learner. Adjust freely to what the art, the skill, and the moment actually call for.',
 'Appended to every phase''s pedagogy guidance when building an AI generation prompt (generate.py, seed_sessions.py). Edit this row to update the disclaimer everywhere at once, instead of touching each phase block.');

-- Verify:
SELECT config_key, config_value FROM session_config;
