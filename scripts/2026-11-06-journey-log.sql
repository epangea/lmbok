-- ============================================================
-- 2026-11-06, journey log (Phase 2, patch A)
--
-- Adds two tables:
--   journey_entries           one row per completed session ('session') and
--                             per milestone ('milestone'); written by
--                             routes/sessions.py::complete_session (patch B).
--   learner_profile_versions  one row per distinct My Story text; written at
--                             both UPDATE learners SET learner_profile sites
--                             in routes/generate.py::update_learner_profile.
--
-- !! RUN THIS BEFORE restarting freqlearn with the new code. The profile
-- !! version insert runs after every profile update; if the table is missing
-- !! the insert is skipped and logged (the profile itself still saves), but
-- !! no history is recorded until the table exists.
--
-- Column types match the referenced keys exactly (learners.id and
-- sessions.id INT UNSIGNED, arts.id TINYINT UNSIGNED, skills.id SMALLINT
-- UNSIGNED), which MariaDB requires for foreign keys.
--
-- Deleting a learner cascades to both tables (the admin hard-delete relies
-- on this). Deleting a session or a skill keeps the journey entry and sets
-- the reference to NULL.
--
-- Purely additive and re-runnable (IF NOT EXISTS).
-- Rollback (after reverting the code):
--   DROP TABLE IF EXISTS journey_entries, learner_profile_versions;
-- ============================================================

CREATE TABLE IF NOT EXISTS journey_entries (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id  INT UNSIGNED      NOT NULL,
    kind        ENUM('session','milestone') NOT NULL,
    milestone   ENUM('first_in_art','level_up','stage_change','all_families') NULL DEFAULT NULL,
    session_id  INT UNSIGNED      NULL DEFAULT NULL,
    art_id      TINYINT UNSIGNED  NULL DEFAULT NULL,
    skill_id    SMALLINT UNSIGNED NULL DEFAULT NULL,
    title       VARCHAR(200)      NOT NULL,
    excerpt     VARCHAR(400)      NULL DEFAULT NULL,
    payload     JSON              NULL DEFAULT NULL,
    created_at  DATETIME          DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (art_id)     REFERENCES arts(id)     ON DELETE SET NULL,
    FOREIGN KEY (skill_id)   REFERENCES skills(id)   ON DELETE SET NULL,
    INDEX idx_journey_learner_time (learner_id, created_at),
    INDEX idx_journey_milestone    (learner_id, milestone, art_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS learner_profile_versions (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id  INT UNSIGNED NOT NULL,
    profile     TEXT         NOT NULL,
    source      ENUM('session','sandbox','bioregion','backfill') NOT NULL,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    INDEX idx_profile_versions (learner_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Verify
DESCRIBE journey_entries;
DESCRIBE learner_profile_versions;
