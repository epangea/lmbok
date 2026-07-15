-- ============================================================
-- FreqLearn — Prototype Seed Data Cleanup
-- Generated: 2026-06-03
-- Run each block carefully. SELECT before DELETE always.
-- ============================================================

-- ── STEP 1: Review what we're about to deactivate ────────────
-- Prototype orgs (IDs 3-17): all have .example.org websites,
-- none are verified, none have password_hash (no real org auth)
SELECT id, name, slug, website, is_verified
FROM organizations
WHERE id BETWEEN 3 AND 17
ORDER BY id;
-- Expected: 15 rows, all .example.org websites

-- Prototype listings tied to these orgs (IDs 38-67)
SELECT ol.id, ol.title, ol.listing_type, o.name as org_name
FROM opportunity_listings ol
JOIN organizations o ON ol.org_id = o.id
WHERE ol.org_id BETWEEN 3 AND 17
ORDER BY ol.id;
-- Expected: 30 rows across 15 orgs

-- ── STEP 2: Check matches against prototype listings ─────────
-- Learner 2 has 2 matches against prototype listings (IDs 47, 54)
-- We deactivate listings but KEEP match records for data integrity
SELECT om.id, om.learner_id, om.listing_id, om.learner_status, ol.title
FROM opportunity_matches om
JOIN opportunity_listings ol ON om.listing_id = ol.id
WHERE ol.org_id BETWEEN 3 AND 17;
-- Expected: matches for listing IDs 47 and 54

-- ── STEP 3: Add lifecycle columns if not already present ─────
ALTER TABLE opportunity_listings
    ADD COLUMN IF NOT EXISTS last_verified_at  DATETIME     NULL,
    ADD COLUMN IF NOT EXISTS deactivation_reason VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS expires_at         DATE         NULL;

-- ── STEP 4: Deactivate prototype listings (NOT delete) ───────
-- Soft-delete: is_active=0 preserves match history
UPDATE opportunity_listings
SET    is_active            = 0,
       deactivation_reason  = 'prototype_seed_data'
WHERE  org_id BETWEEN 3 AND 17;
-- Expected: 30 rows affected

-- ── STEP 5: Deactivate prototype orgs ────────────────────────
UPDATE organizations
SET    is_active = 0
WHERE  id BETWEEN 3 AND 17;
-- Expected: 15 rows affected

-- ── STEP 6: Handle the dead scavenged URL (listing 70) ───────
UPDATE opportunity_listings
SET    is_active           = 0,
       deactivation_reason = 'url_dead',
       last_verified_at    = NOW()
WHERE  id = 70;
-- Expected: 1 row affected

-- ── STEP 7: Mark verified URLs as checked ────────────────────
-- Run AFTER verify_listings.py confirms which ones are live
-- Update with actual results from the script:
UPDATE opportunity_listings
SET    last_verified_at = NOW()
WHERE  id IN (68, 71, 72);  -- adjust based on script output
-- (skip 69/UNESCO if it returns a warning — verify manually)

-- ── STEP 8: Verify final state ───────────────────────────────
SELECT
    CASE
        WHEN o.website LIKE '%example.org%' THEN 'prototype'
        WHEN o.slug = 'freqlearn-scavenger' THEN 'scavenged'
        WHEN o.slug = 'freqlearn-community' THEN 'internal'
        ELSE 'real_org'
    END AS source,
    ol.is_active,
    COUNT(*) as count
FROM opportunity_listings ol
JOIN organizations o ON ol.org_id = o.id
GROUP BY source, ol.is_active
ORDER BY source, ol.is_active;
-- Expected after cleanup:
--   internal   | 1 | 8   (FreqLearn Community listings, still active)
--   prototype  | 0 | 30  (all deactivated)
--   scavenged  | 0 | 1   (iyervalli dead link)
--   scavenged  | 1 | 4   (worldvision, unesco, nps, msf — if URLs live)

-- ── STEP 9: Confirm learner matches still intact ─────────────
SELECT om.id, om.learner_id, om.listing_id, om.learner_status,
       ol.title, ol.is_active, o.name
FROM opportunity_matches om
JOIN opportunity_listings ol ON om.listing_id = ol.id
JOIN organizations o ON ol.org_id = o.id
ORDER BY om.id;
-- Match records preserved even for deactivated listings
-- Frontend should handle is_active=0 gracefully (show as "no longer available")
