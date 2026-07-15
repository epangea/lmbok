-- P2: Peripatos learning journal
-- Creates peripatos_entries for saved Socratic companion exchanges
--
-- Pre-flight check:
--   DESCRIBE learners;           ← verify id is INT UNSIGNED (migration matches this)
--   DESCRIBE peripatos_entries;  ← run AFTER to confirm
--
-- Run:
--   mysql -u freqlearn -p freqlearn < migrate_peripatos.sql

CREATE TABLE IF NOT EXISTS peripatos_entries (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    learner_id  INT UNSIGNED    NOT NULL,
    title       VARCHAR(255)    NOT NULL,
    messages    JSON            NOT NULL,         -- [{role, content}, ...] full thread
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_learner_created (learner_id, created_at),

    CONSTRAINT fk_peripatos_learner
        FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify
SELECT 'peripatos_entries created' AS status;
DESCRIBE peripatos_entries;
