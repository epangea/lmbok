-- ═══════════════════════════════════════════════════════════════════════════
-- migrate_bio_versions.sql
-- P_MAP versioning: add version tracking to bioregion_portraits
-- Run after DESCRIBE bioregion_portraits confirms current column set.
--
-- SAFE to run multiple times (IF NOT EXISTS / IF EXISTS guards throughout).
-- ═══════════════════════════════════════════════════════════════════════════

-- ── PART A — Read-only preflight checks ──────────────────────────────────────
-- Run these SELECT statements first and verify output before proceeding.

-- A1. Confirm current portrait schema
DESCRIBE bioregion_portraits;

-- A2. Snapshot current row count
SELECT COUNT(*) AS current_portrait_count FROM bioregion_portraits;

-- A3. Preview what will become version 1 records
SELECT id, cluster_label, version_number, last_generated_at, contributor_count
FROM bioregion_portraits
ORDER BY id;
-- Expected: version_number column does NOT exist yet. If it does, stop — migration already run.

-- ── PART B — Schema changes (uncomment and run after verifying Part A) ────────

/*

-- B1. Add versioning columns to bioregion_portraits
ALTER TABLE bioregion_portraits
  ADD COLUMN IF NOT EXISTS version_number       TINYINT UNSIGNED  NOT NULL DEFAULT 1
                                                COMMENT 'Increments each time a new portrait is generated',
  ADD COLUMN IF NOT EXISTS vitality_snapshot    VARCHAR(120)      NULL
                                                COMMENT 'Modal vitality value from contributions at generation time',
  ADD COLUMN IF NOT EXISTS change_notes         TEXT              NULL
                                                COMMENT 'Admin-authored notes on what changed in this version';

-- B2. Create the version history archive table
CREATE TABLE IF NOT EXISTS bioregion_portrait_versions (
  id                 INT UNSIGNED    AUTO_INCREMENT PRIMARY KEY,
  portrait_id        INT UNSIGNED    NOT NULL
                     COMMENT 'FK to bioregion_portraits — the living portrait this version belongs to',
  version_number     TINYINT UNSIGNED NOT NULL
                     COMMENT 'Version being archived (e.g. 1 when overwriting to become 2)',
  summary            TEXT            NOT NULL
                     COMMENT 'Full AI-generated text snapshot at this version',
  contributor_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  vitality_snapshot  VARCHAR(120)    NULL
                     COMMENT 'Captured vitality label at this version',
  change_notes       TEXT            NULL
                     COMMENT 'Admin notes explaining what changed since the previous version',
  generated_at       DATETIME        NOT NULL
                     COMMENT 'When this version was generated (copied from last_generated_at)',

  FOREIGN KEY fk_bpv_portrait (portrait_id)
    REFERENCES bioregion_portraits(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,

  UNIQUE KEY uq_portrait_version (portrait_id, version_number),
  INDEX idx_portrait_versions (portrait_id, version_number DESC)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Archive of all past portrait generations; current version lives in bioregion_portraits';

*/

-- ── PART C — Post-check (run after Part B) ───────────────────────────────────

/*

-- C1. Confirm new columns exist on bioregion_portraits
DESCRIBE bioregion_portraits;
-- Expected: version_number, vitality_snapshot, change_notes appear at end

-- C2. Confirm version archive table created
DESCRIBE bioregion_portrait_versions;

-- C3. Confirm existing portraits have version_number = 1 (DEFAULT applied)
SELECT id, cluster_label, version_number, vitality_snapshot
FROM bioregion_portraits
ORDER BY id;
-- Expected: version_number = 1 for all rows, vitality_snapshot = NULL

-- C4. Confirm archive table is empty (no versions archived yet — correct at this point)
SELECT COUNT(*) AS archived_versions FROM bioregion_portrait_versions;
-- Expected: 0

*/
