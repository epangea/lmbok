-- ============================================================
-- FreqLearn — add_art_domain_weights.sql
-- Creates the art_domain_weights table and seeds all 51 mappings
-- (15 arts × 1–4 domains each, weights per art summing to 1.00).
--
-- Purpose: connects the 15-art "who you are" avatar radar to the
-- 8-domain "what you're learning" domain radar.
-- Client-side computation in index.html uses the same weights;
-- this table persists them server-side for engine and admin use.
--
-- Run: sudo mysql -u freqlearn -p freqlearn < add_art_domain_weights.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS art_domain_weights (
  art_id  tinyint(3) unsigned NOT NULL,
  domain  ENUM('cognitive','creative','physical','social',
               'language','emotional','meta','technical') NOT NULL,
  weight  DECIMAL(3,2) NOT NULL COMMENT 'Fractional contribution 0.00–1.00; per-art weights sum to 1.00',
  PRIMARY KEY (art_id, domain),
  CONSTRAINT adw_art_fk FOREIGN KEY (art_id) REFERENCES arts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Weighted mapping from each of the 15 Arts to 8 learning domains';

-- Clear any previous seed so this is safe to re-run
DELETE FROM art_domain_weights;

-- ── Being ─────────────────────────────────────────────────
INSERT INTO art_domain_weights (art_id, domain, weight)

-- move: body as teacher → physical, emotional awareness, meta-learning
SELECT id, 'physical',  0.65 FROM arts WHERE slug='move' UNION ALL
SELECT id, 'emotional', 0.20 FROM arts WHERE slug='move' UNION ALL
SELECT id, 'meta',      0.15 FROM arts WHERE slug='move' UNION ALL

-- eat: nourishment as practice → physical, cognitive (food systems), emotional, meta
SELECT id, 'physical',  0.40 FROM arts WHERE slug='eat' UNION ALL
SELECT id, 'cognitive', 0.25 FROM arts WHERE slug='eat' UNION ALL
SELECT id, 'emotional', 0.20 FROM arts WHERE slug='eat' UNION ALL
SELECT id, 'meta',      0.15 FROM arts WHERE slug='eat' UNION ALL

-- feel: emotional intelligence → emotional, social attunement, meta
SELECT id, 'emotional', 0.65 FROM arts WHERE slug='feel' UNION ALL
SELECT id, 'social',    0.20 FROM arts WHERE slug='feel' UNION ALL
SELECT id, 'meta',      0.15 FROM arts WHERE slug='feel' UNION ALL

-- notice: outward attention without judgement → cognitive, meta, emotional, creative
SELECT id, 'cognitive', 0.40 FROM arts WHERE slug='notice' UNION ALL
SELECT id, 'meta',      0.30 FROM arts WHERE slug='notice' UNION ALL
SELECT id, 'emotional', 0.20 FROM arts WHERE slug='notice' UNION ALL
SELECT id, 'creative',  0.10 FROM arts WHERE slug='notice' UNION ALL

-- express: inward→outward clarity → creative, language, emotional
SELECT id, 'creative',  0.55 FROM arts WHERE slug='express' UNION ALL
SELECT id, 'language',  0.25 FROM arts WHERE slug='express' UNION ALL
SELECT id, 'emotional', 0.20 FROM arts WHERE slug='express' UNION ALL

-- ── Becoming ──────────────────────────────────────────────

-- live: civic and personal agency → cognitive, social, meta, technical
SELECT id, 'cognitive',  0.35 FROM arts WHERE slug='live' UNION ALL
SELECT id, 'social',     0.25 FROM arts WHERE slug='live' UNION ALL
SELECT id, 'meta',       0.25 FROM arts WHERE slug='live' UNION ALL
SELECT id, 'technical',  0.15 FROM arts WHERE slug='live' UNION ALL

-- listen: deep empathy → social, language, emotional
SELECT id, 'social',    0.45 FROM arts WHERE slug='listen' UNION ALL
SELECT id, 'language',  0.35 FROM arts WHERE slug='listen' UNION ALL
SELECT id, 'emotional', 0.20 FROM arts WHERE slug='listen' UNION ALL

-- give: selfless contribution → social, emotional, meta
SELECT id, 'social',    0.50 FROM arts WHERE slug='give' UNION ALL
SELECT id, 'emotional', 0.30 FROM arts WHERE slug='give' UNION ALL
SELECT id, 'meta',      0.20 FROM arts WHERE slug='give' UNION ALL

-- receive: acceptance and humility → emotional, social, meta
SELECT id, 'emotional', 0.45 FROM arts WHERE slug='receive' UNION ALL
SELECT id, 'social',    0.30 FROM arts WHERE slug='receive' UNION ALL
SELECT id, 'meta',      0.25 FROM arts WHERE slug='receive' UNION ALL

-- collaborate: shared vision → social, language, cognitive
SELECT id, 'social',    0.55 FROM arts WHERE slug='collaborate' UNION ALL
SELECT id, 'language',  0.20 FROM arts WHERE slug='collaborate' UNION ALL
SELECT id, 'cognitive', 0.25 FROM arts WHERE slug='collaborate' UNION ALL

-- ── Connecting ────────────────────────────────────────────

-- understand: first principles thinking → cognitive, meta, technical
SELECT id, 'cognitive',  0.60 FROM arts WHERE slug='understand' UNION ALL
SELECT id, 'meta',       0.20 FROM arts WHERE slug='understand' UNION ALL
SELECT id, 'technical',  0.20 FROM arts WHERE slug='understand' UNION ALL

-- respect: the golden rule extended → social, emotional, cognitive
SELECT id, 'social',    0.40 FROM arts WHERE slug='respect' UNION ALL
SELECT id, 'emotional', 0.35 FROM arts WHERE slug='respect' UNION ALL
SELECT id, 'cognitive', 0.25 FROM arts WHERE slug='respect' UNION ALL

-- build: bioconstruction and design → technical, creative, cognitive, physical
SELECT id, 'technical', 0.40 FROM arts WHERE slug='build' UNION ALL
SELECT id, 'creative',  0.25 FROM arts WHERE slug='build' UNION ALL
SELECT id, 'cognitive', 0.20 FROM arts WHERE slug='build' UNION ALL
SELECT id, 'physical',  0.15 FROM arts WHERE slug='build' UNION ALL

-- grow: regenerative agriculture → physical, cognitive, technical, meta
SELECT id, 'physical',  0.30 FROM arts WHERE slug='grow' UNION ALL
SELECT id, 'cognitive', 0.25 FROM arts WHERE slug='grow' UNION ALL
SELECT id, 'technical', 0.20 FROM arts WHERE slug='grow' UNION ALL
SELECT id, 'meta',      0.25 FROM arts WHERE slug='grow' UNION ALL

-- consume: water and resource stewardship → cognitive, technical, meta, physical
SELECT id, 'cognitive',  0.35 FROM arts WHERE slug='consume' UNION ALL
SELECT id, 'technical',  0.25 FROM arts WHERE slug='consume' UNION ALL
SELECT id, 'meta',       0.25 FROM arts WHERE slug='consume' UNION ALL
SELECT id, 'physical',   0.15 FROM arts WHERE slug='consume';

-- ── Verify ────────────────────────────────────────────────
SELECT
  a.slug,
  a.name,
  COUNT(adw.domain)        AS domain_count,
  ROUND(SUM(adw.weight),2) AS weight_sum
FROM art_domain_weights adw
JOIN arts a ON a.id = adw.art_id
GROUP BY a.id, a.slug, a.name
ORDER BY a.sort_order;
