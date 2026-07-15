-- ═══════════════════════════════════════════════════════════════════════════
-- migrate_bio_versions.sql
-- P_MAP versioning: add version tracking to bioregion_portraits
--
-- WORKFLOW:
--   Step 1 — Run the whole file as-is (Part A only, B is commented out).
--             Verify the output matches expectations below each query.
--   Step 2 — Uncomment Part B, re-run the whole file.
--   Step 3 — Run Part C to confirm clean state.
-- ═══════════════════════════════════════════════════════════════════════════


-- ── PART A — Read-only preflight (run first, no changes) ─────────────────────

-- A1. Confirm current portrait schema — version_number should NOT appear
DESCRIBE bioregion_portraits;
-- Expected columns: id, cluster_label, center_lat, center_lng, radius_km,
--   summary, contributor_count, last_generated_at, created_at
-- If version_number already appears → migration was already run, STOP.

-- A2. Current row count
SELECT COUNT(*) AS current_portrait_count FROM bioregion_portraits;

-- A3. Current portrait rows (no version_number — it doesn't exist yet)
SELECT id, cluster_label, last_generated_at, contributor_count
FROM bioregion_portraits
ORDER BY id;
-- These rows will each become version_number = 1 once Part B runs.

-- A4. Confirm version archive table does NOT yet exist
SELECT COUNT(*) AS version_table_exists
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'bioregion_portrait_versions';
-- Expected: 0


-- ── PART B — Schema changes (uncomment after verifying Part A) ────────────────



-- B1. Add versioning columns to bioregion_portraits
ALTER TABLE bioregion_portraits
  ADD COLUMN version_number    TINYINT UNSIGNED  NOT NULL DEFAULT 1
    COMMENT 'Increments each time a new portrait is generated',
  ADD COLUMN vitality_snapshot VARCHAR(120)      NULL
    COMMENT 'Modal vitality value from contributions at generation time',
  ADD COLUMN change_notes      TEXT              NULL
    COMMENT 'Admin-authored notes on what changed in this version';

-- B2. Create the version archive table
CREATE TABLE IF NOT EXISTS bioregion_portrait_versions (
  id                INT UNSIGNED     AUTO_INCREMENT PRIMARY KEY,
  portrait_id       INT UNSIGNED     NOT NULL
    COMMENT 'FK to bioregion_portraits — the living portrait this version belongs to',
  version_number    TINYINT UNSIGNED NOT NULL
    COMMENT 'Version number being archived',
  summary           TEXT             NOT NULL
    COMMENT 'Full AI-generated text snapshot at this version',
  contributor_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
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
  INDEX idx_portrait_versions   (portrait_id, version_number DESC)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Archive of all past portrait generations; current version lives in bioregion_portraits';




-- ── PART C — Post-check (uncomment and run after Part B) ─────────────────────

/*

-- C1. Confirm new columns present on bioregion_portraits
DESCRIBE bioregion_portraits;
-- Expected: version_number, vitality_snapshot, change_notes now appear

-- C2. All existing portraits should have version_number = 1 (DEFAULT applied)
SELECT id, cluster_label, version_number, vitality_snapshot
FROM bioregion_portraits
ORDER BY id;
-- Expected: version_number = 1, vitality_snapshot = NULL for all rows

-- C3. Confirm archive table created and empty (correct — nothing archived yet)
DESCRIBE bioregion_portrait_versions;
SELECT COUNT(*) AS archived_versions FROM bioregion_portrait_versions;
-- Expected: 0

*/
