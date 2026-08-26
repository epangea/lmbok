-- 2026-08-24-elemental-phases-restructure.sql
--
-- Full replacement of the 6-row dev_phases scheme (prenascent/nascent/
-- child/adolescent/adult/elder) with 13 flat, independently-taggable
-- phases, per this session's design discussion with Charbel:
--
--   Light (Unborn)                            — no age, gestational
--   Sandy Soil / Moist Soil / Humus Soil       (Depending 1/2/3) — 0~2/3~5/6~8
--   Low Fire / Medium Fire / High Fire         (Weaning 1/2/3)   — 9~11/12~14/15~17
--   Low Wind / High Wind                       (Adulting 1/2)    — 18~22/23~27
--   Water (Adult)                              — 28~38
--   Metal (Maturing)                           — 39~59
--   Stone (Mature)                             — 60~80
--   Wood (Cresting)                            — 81+
--
-- This is a structural change, not a rename-in-place: sub-bands that
-- used to nest under one parent phase (e.g. old "adolescent" 12~19) are
-- now independent rows, so the row count goes from 6 to 13 and none of
-- the old IDs survive.
--
-- Consequently: any existing FK reference to the old 6 rows (sessions.
-- dev_phase_id, leckos.phase_id, learners.phase_id) is now pointing at
-- data we're about to delete. Per Charbel: do NOT try to auto-remap old
-- tags onto the new scheme — untag instead, and preserve the old slug
-- as a legacy_phase_slug snapshot rather than losing it outright.
--
-- Also per Charbel: NULL must no longer mean "serve to anyone" (that
-- fallback was live in generate.py's _select_reusable_pool — see the
-- paired code change in this same batch). NULL now means "unresolved,
-- excluded from serving until re-tagged." This migration only touches
-- data; the serving-logic change is a separate, paired code edit.
--
-- leckos.phase_id is currently NOT NULL — loosened to nullable here,
-- since "untag pending re-tag" is now a valid, expected state for a
-- LECKO, not an error condition.
--
-- Run the preflight SELECTs first.

-- ── Preflight: current state ───────────────────────────────────
SELECT slug, name, age_range, sort_order FROM dev_phases ORDER BY sort_order;
SELECT COUNT(*) AS sessions_tagged FROM sessions WHERE dev_phase_id IS NOT NULL;
SELECT COUNT(*) AS leckos_tagged   FROM leckos   WHERE phase_id IS NOT NULL;
SELECT COUNT(*) AS learners_tagged FROM learners WHERE phase_id IS NOT NULL;

-- ── Schema changes ──────────────────────────────────────────────

-- dev_phases gains icon (emoji) + color (hex), for the single-source
-- /phases endpoint to carry both instead of each frontend page
-- hardcoding its own icon/color mirror.
ALTER TABLE dev_phases
  ADD COLUMN icon  VARCHAR(8) NULL AFTER age_range,
  ADD COLUMN color VARCHAR(7) NULL AFTER icon;

-- Legacy-slug snapshots, so untagging below doesn't erase history.
ALTER TABLE sessions ADD COLUMN legacy_phase_slug VARCHAR(20) NULL AFTER dev_phase_id;
ALTER TABLE leckos   ADD COLUMN legacy_phase_slug VARCHAR(20) NULL AFTER phase_id;

-- leckos.phase_id was NOT NULL; "unresolved, pending re-tag" is now a
-- legitimate state, not an error, so this has to be loosened.
ALTER TABLE leckos MODIFY COLUMN phase_id TINYINT UNSIGNED NULL;

-- New learner field: expecting-parent flag overrides normal
-- birth-year-based phase computation and routes straight to Light.
-- birth_year is kept as-is (already exists); no trimester field per
-- Charbel's decision to drop that level of granularity.
ALTER TABLE learners ADD COLUMN is_expecting_parent BOOLEAN NOT NULL DEFAULT FALSE AFTER birth_year;

-- ── Snapshot legacy slugs before untagging ─────────────────────
UPDATE sessions s
  JOIN dev_phases dp ON s.dev_phase_id = dp.id
  SET s.legacy_phase_slug = dp.slug
  WHERE s.dev_phase_id IS NOT NULL;

UPDATE leckos l
  JOIN dev_phases dp ON l.phase_id = dp.id
  SET l.legacy_phase_slug = dp.slug
  WHERE l.phase_id IS NOT NULL;

-- ── Untag everything pointing at the old 6-row scheme ──────────
-- Sessions/LECKOs: NULL now means "needs re-tagging before it can be
-- served again" — deliberate, not a fallback-to-anyone state anymore.
UPDATE sessions SET dev_phase_id = NULL;
UPDATE leckos   SET phase_id     = NULL;

-- Learners: no legacy snapshot needed here — phase_id is a derived
-- field going forward (computed fresh from birth_year / expecting-
-- parent status), not historical data worth preserving as legacy.
UPDATE learners SET phase_id = NULL;

-- ── Replace dev_phases wholesale ───────────────────────────────
DELETE FROM dev_phases;
ALTER TABLE dev_phases AUTO_INCREMENT = 1;

INSERT INTO dev_phases (name, slug, age_range, icon, color, description, sort_order) VALUES
('Light (Unborn)',              'light',      NULL,    '☀️', '#FFC93C', 'The parent is the primary learner, tuning in before the child arrives.', 1),
('Sandy Soil (Depending 1)',    'sandy-soil', '0~2',   '🌱', '#8BC34A', 'Loose, absorbent, entirely dependent on what surrounds it.',             2),
('Moist Soil (Depending 2)',    'moist-soil', '3~5',   '🌱', '#4CAF50', 'Holding and retaining — curiosity-led exploration takes root.',          3),
('Humus Soil (Depending 3)',    'humus-soil', '6~8',   '🌱', '#2E7D32', 'Rich and self-sustaining — the most fertile ground for growth.',         4),
('Low Fire (Weaning 1)',        'low-fire',   '9~11',  '🔥', '#FF8A50', 'A first spark of independence, still close to the hearth.',              5),
('Medium Fire (Weaning 2)',     'medium-fire','12~14', '🔥', '#FF5722', 'Identity catching alight. Peers become a second family.',                6),
('High Fire (Weaning 3)',       'high-fire',  '15~17', '🔥', '#E53935', 'Full blaze — pushing outward, testing independence in earnest.',         7),
('Low Wind (Adulting 1)',       'low-wind',   '18~22', '🪁', '#4FC3F7', 'Newly airborne, finding direction through movement.',                    8),
('High Wind (Adulting 2)',      'high-wind',  '23~27', '🪁', '#00ACC1', 'A steadier current — building momentum toward a chosen path.',           9),
('Water (Adult)',               'water',      '28~38', '💧', '#1E88E5', 'Flowing and shaping — building, leading, contributing.',                10),
('Metal (Maturing)',            'metal',      '39~59', '⚙️', '#C9A227', 'Forged and dependable — the load-bearing years.',                       11),
('Stone (Mature)',              'stone',      '60~80', '🪨', '#8D6E63', 'Weathered and solid — wisdom transmission, legacy taking shape.',       12),
('Wood (Cresting)',             'wood',       '81+',   '🌳', '#A0672E', 'Rooted, weathered, still standing — integration and acceptance.',       13);

-- ── Verify ───────────────────────────────────────────────────────
SELECT slug, name, age_range, icon, color, sort_order FROM dev_phases ORDER BY sort_order;
SELECT COUNT(*) AS sessions_legacy_snapshotted FROM sessions WHERE legacy_phase_slug IS NOT NULL;
SELECT COUNT(*) AS leckos_legacy_snapshotted   FROM leckos   WHERE legacy_phase_slug IS NOT NULL;
SELECT COUNT(*) AS sessions_now_untagged FROM sessions WHERE dev_phase_id IS NULL;
SELECT COUNT(*) AS leckos_now_untagged   FROM leckos   WHERE phase_id IS NULL;
