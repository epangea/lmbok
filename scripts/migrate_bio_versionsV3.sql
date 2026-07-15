-- ═══════════════════════════════════════════════════════════════════════════
-- migrate_bio_versions_v3.sql
-- Fixes errno 150: portrait_id changed INT UNSIGNED → INT to match
-- bioregion_portraits.id int(11) (signed).
-- B1 uses IF NOT EXISTS so it's safe to re-run if it already executed.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── PART A — Confirm current state before running ────────────────────────────

-- A1. Check which new columns already exist on bioregion_portraits
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME   = 'bioregion_portraits'
  AND COLUMN_NAME IN ('version_number','vitality_snapshot','change_notes')
ORDER BY COLUMN_NAME;
-- Expected after a partial previous run: version_number may or may not appear.
-- If all three appear, B1 is already done — skip to B2.

-- A2. Confirm version archive table still does not exist
SELECT COUNT(*) AS version_table_exists
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME   = 'bioregion_portrait_versions';
-- Expected: 0 (table creation failed last time)


-- ── PART B — Schema changes ──────────────────────────────────────────────────

-- B1. Add columns to bioregion_portraits (IF NOT EXISTS — safe to re-run)
ALTER TABLE bioregion_portraits
  ADD COLUMN IF NOT EXISTS version_number    TINYINT UNSIGNED NOT NULL DEFAULT 1
    COMMENT 'Increments each time a new portrait is generated',
  ADD COLUMN IF NOT EXISTS vitality_snapshot VARCHAR(120)     NULL
    COMMENT 'Modal vitality value from contributions at generation time',
  ADD COLUMN IF NOT EXISTS change_notes      TEXT             NULL
    COMMENT 'Admin-authored notes on what changed in this version';

-- B2. Create version archive table
--     portrait_id is INT (not UNSIGNED) to match bioregion_portraits.id int(11)
CREATE TABLE IF NOT EXISTS bioregion_portrait_versions (
  id                INT              AUTO_INCREMENT PRIMARY KEY,
  portrait_id       INT              NOT NULL
    COMMENT 'FK to bioregion_portraits.id (int, signed)',
  version_number    TINYINT UNSIGNED NOT NULL
    COMMENT 'Version number being archived',
  summary           TEXT             NOT NULL
    COMMENT 'Full AI-generated text snapshot at this version',
  contributor_count INT              NOT NULL DEFAULT 0,
  vitality_snapshot VARCHAR(120)     NULL
    COMMENT 'Captured vitality label at this version',
  change_notes      TEXT             NULL
    COMMENT 'Admin notes explaining what changed since the previous version',
  generated_at      DATETIME         NOT NULL
    COMMENT 'When this version was generated (copied from last_generated_at)',

  FOREIGN KEY fk_bpv_portrait (portrait_id)
    REFERENCES bioregion_portraits(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,

  UNIQUE KEY uq_portrait_version (portrait_id, version_number),
  INDEX idx_portrait_versions    (portrait_id, version_number DESC)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Archive of all past portrait generations; current version lives in bioregion_portraits';


-- ── PART C — Post-check ──────────────────────────────────────────────────────

-- C1. Confirm all three new columns exist on bioregion_portraits
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME   = 'bioregion_portraits'
  AND COLUMN_NAME IN ('version_number','vitality_snapshot','change_notes')
ORDER BY COLUMN_NAME;
-- Expected: all three rows present

-- C2. Existing portrait has version_number = 1
SELECT id, cluster_label, version_number, vitality_snapshot
FROM bioregion_portraits ORDER BY id;
-- Expected: version_number = 1, vitality_snapshot = NULL

-- C3. Archive table exists and is empty
SELECT COUNT(*) AS archived_versions FROM bioregion_portrait_versions;
-- Expected: 0

-- C4. FK is correctly formed — this will error if the FK is broken
SELECT COUNT(*) AS fk_check
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA        = DATABASE()
  AND TABLE_NAME          = 'bioregion_portrait_versions'
  AND CONSTRAINT_NAME     = 'fk_bpv_portrait';
-- Expected: 1
