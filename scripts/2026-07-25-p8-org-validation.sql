-- ============================================================
-- P8 — Org validation system (task line-item completions +
-- org-verified skill demonstrations). Additive only.
--
-- Read PART 22 in PROJECT_MASTER for the full spec.
--
-- ⚠ PREFLIGHT — run these first and eyeball signedness before the
-- CREATE TABLEs below. This codebase has hit FK errno 150 twice
-- already from guessing a parent PK's signedness wrong (learners.id
-- was declared int(10) unsigned even though models.py just said
-- Integer) — same risk here for opportunity_matches.id / skills.id.
-- If DESCRIBE disagrees with the INT UNSIGNED / SMALLINT UNSIGNED
-- used below, fix the CREATE TABLE statements before running them.
-- ============================================================

DESCRIBE opportunity_listings;
DESCRIBE opportunity_matches;
DESCRIBE skills;
SELECT COUNT(*) AS listing_count FROM opportunity_listings;
SELECT COUNT(*) AS match_count   FROM opportunity_matches;

-- ── (1) needs_tasks: AI-derived line items, same parse-needs pass ──
-- as needs_skill_targets. JSON array of plain task-description strings,
-- e.g. ["Facilitate two group discussions", "Draft a first-aid checklist"].
-- Purely additive column, NULL until an org runs parse-needs again.
ALTER TABLE opportunity_listings
    ADD COLUMN IF NOT EXISTS needs_tasks JSON NULL AFTER needs_skill_targets;

-- ── (2) task_completions: per-match tracking of each needs_tasks line item ──
-- One row per (match_id, task_index) once a learner submits or an org rep
-- checks it off — no row at all means "open"/untouched, so this table only
-- ever grows additively as work actually happens on a match.
CREATE TABLE IF NOT EXISTS task_completions (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    match_id        INT UNSIGNED NOT NULL,
    task_index      SMALLINT UNSIGNED NOT NULL,   -- index into the listing's needs_tasks array at time of submission
    task_text       VARCHAR(300) NOT NULL,          -- snapshot, so later edits to needs_tasks don't retroactively relabel a completed item
    status          ENUM('submitted','verified','rejected') NOT NULL DEFAULT 'submitted',
    learner_note    TEXT NULL,
    session_ids     JSON NULL,                       -- sessions/LECKOs the learner points to as evidence
    submitted_at    DATETIME NULL,
    verified_at     DATETIME NULL,
    verified_by     VARCHAR(160) NULL,               -- free-text name of the org rep who checked it off (orgs have no per-rep login)
    org_note        TEXT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_match_task (match_id, task_index),
    CONSTRAINT fk_task_completions_match
        FOREIGN KEY (match_id) REFERENCES opportunity_matches(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── (3) verified_skills: org-confirmed skill demonstrations per match ──
-- Deliberately NOT written into learner_skill_progress.current_level (see
-- PART 22 open-questions resolution — org validation is a citable, visible
-- credential tied to the Need it was earned on, not an automatic write to
-- the learner's global, self-paced skill level).
CREATE TABLE IF NOT EXISTS verified_skills (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    match_id        INT UNSIGNED NOT NULL,
    skill_id        SMALLINT UNSIGNED NOT NULL,
    level           ENUM('developing','proficient','master') NOT NULL,
    session_ids     JSON NULL,                       -- sessions/LECKOs cited as evidence for this level
    note            TEXT NULL,
    verified_by     VARCHAR(160) NULL,
    verified_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_match_skill (match_id, skill_id),   -- re-verifying the same skill on the same match is an UPDATE, not a new row
    CONSTRAINT fk_verified_skills_match
        FOREIGN KEY (match_id) REFERENCES opportunity_matches(id),
    CONSTRAINT fk_verified_skills_skill
        FOREIGN KEY (skill_id) REFERENCES skills(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── Sanity check after running ──────────────────────────────
DESCRIBE task_completions;
DESCRIBE verified_skills;
