-- 2026-08-24b-fix-icon-charset-and-reinsert.sql
--
-- Fixes the failure from 2026-08-24-elemental-phases-restructure.sql:
-- the `icon` column inherited a charset too narrow for 4-byte emoji
-- (🌱 U+1F331 and friends), so the 13-row INSERT rolled back entirely,
-- leaving dev_phases at 0 rows. Everything else in that migration
-- (legacy_phase_slug snapshots, untagging, new columns) already
-- committed successfully and is untouched by this file.
--
-- Preflight — confirm dev_phases is currently empty before proceeding:
SELECT COUNT(*) AS should_be_zero FROM dev_phases;

SET NAMES utf8mb4;

ALTER TABLE dev_phases MODIFY COLUMN icon VARCHAR(8) CHARACTER SET utf8mb4 NULL;

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

-- Verify:
SELECT slug, name, age_range, icon, color, sort_order FROM dev_phases ORDER BY sort_order;
