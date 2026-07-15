-- P2b: Dummy org & listing seed data cleanup
-- ============================================================
-- Removes seed-inserted orgs (no password_hash = never self-
-- registered) and their full FK chain: messages → matches →
-- listings → orgs.
--
-- The freqlearn-scavenger system org (id=18) is explicitly
-- excluded by slug regardless of its password_hash state.
--
-- WORKFLOW:
--   1. Run PART A (read-only). Verify every row looks like
--      dummy data before proceeding.
--   2. Uncomment PART B and run the transaction.
--   3. Run PART C to confirm clean state.
--
-- Run: mysql -u freqlearn -p freqlearn < migrate_p2b_org_cleanup.sql
-- ============================================================


-- ── PART A: Diagnostics (read-only) ──────────────────────────

SELECT '=== DUMMY ORGS ===' AS section;
SELECT id, name, slug, org_type, is_active, created_at
FROM organizations
WHERE password_hash IS NULL
  AND slug != 'freqlearn-scavenger'
ORDER BY id;

SELECT '=== THEIR LISTINGS ===' AS section;
SELECT ol.id, ol.title, o.name AS org_name,
       ol.listing_type, ol.is_active, ol.scavenged, ol.created_at
FROM opportunity_listings ol
JOIN organizations o ON o.id = ol.org_id
WHERE o.password_hash IS NULL
  AND o.slug != 'freqlearn-scavenger'
ORDER BY ol.org_id, ol.id;

SELECT '=== MATCHES REFERENCING THOSE LISTINGS ===' AS section;
SELECT om.id AS match_id, om.listing_id,
       ol.title AS listing_title,
       om.learner_id, om.org_status
FROM opportunity_matches om
JOIN opportunity_listings ol ON ol.id = om.listing_id
JOIN organizations o ON o.id = ol.org_id
WHERE o.password_hash IS NULL
  AND o.slug != 'freqlearn-scavenger';

SELECT '=== MESSAGES IN THOSE MATCHES ===' AS section;
SELECT m.id, m.match_id, m.sender_type,
       LEFT(m.body, 60) AS preview
FROM messages m
JOIN opportunity_matches om ON om.id = m.match_id
JOIN opportunity_listings ol ON ol.id = om.listing_id
JOIN organizations o ON o.id = ol.org_id
WHERE o.password_hash IS NULL
  AND o.slug != 'freqlearn-scavenger';


-- ── PART B: Cleanup — uncomment when Part A looks correct ────


START TRANSACTION;

-- 1. Messages inside affected matches
DELETE m FROM messages m
  JOIN opportunity_matches om ON om.id = m.match_id
  JOIN opportunity_listings ol ON ol.id = om.listing_id
  JOIN organizations o ON o.id = ol.org_id
  WHERE o.password_hash IS NULL
    AND o.slug != 'freqlearn-scavenger';
SELECT ROW_COUNT() AS messages_deleted;

-- 2. Matches for affected listings
DELETE om FROM opportunity_matches om
  JOIN opportunity_listings ol ON ol.id = om.listing_id
  JOIN organizations o ON o.id = ol.org_id
  WHERE o.password_hash IS NULL
    AND o.slug != 'freqlearn-scavenger';
SELECT ROW_COUNT() AS matches_deleted;

-- 3. Listings under dummy orgs
DELETE ol FROM opportunity_listings ol
  JOIN organizations o ON o.id = ol.org_id
  WHERE o.password_hash IS NULL
    AND o.slug != 'freqlearn-scavenger';
SELECT ROW_COUNT() AS listings_deleted;

-- 4. Dummy orgs themselves
DELETE FROM organizations
  WHERE password_hash IS NULL
    AND slug != 'freqlearn-scavenger';
SELECT ROW_COUNT() AS orgs_deleted;

COMMIT;



-- ── PART C: Post-check ────────────────────────────────────────

SELECT '=== REMAINING ORGS (expect only freqlearn-scavenger) ===' AS section;
SELECT id, name, slug, is_active, password_hash IS NOT NULL AS has_password
FROM organizations
ORDER BY id;

SELECT '=== REMAINING ACTIVE LISTINGS ===' AS section;
SELECT ol.id, ol.title, o.name AS org_name, ol.is_active, ol.scavenged
FROM opportunity_listings ol
JOIN organizations o ON o.id = ol.org_id
WHERE ol.is_active = 1
ORDER BY ol.id;

SELECT '=== SYSTEM ORG INTACT ===' AS section;
SELECT id, name, slug, is_active
FROM organizations
WHERE slug = 'freqlearn-scavenger';
