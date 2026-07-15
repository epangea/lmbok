-- ============================================================
-- FreqLearn — seed_listings.sql
-- Sample opportunity listings for the New Match card.
-- required_arts: JSON array of art slugs the listing needs.
-- Run: mysql -u freqlearn -p freqlearn < seed_listings.sql
-- ============================================================

-- Create a placeholder organisation first (if none exist)
INSERT IGNORE INTO organizations (id, name, slug, description, org_type, is_verified, is_active, created_at)
VALUES (1, 'FreqLearn Community', 'freqlearn-community',
        'Community projects surfacing through the platform', 'community', 1, 1, NOW());

-- Clear existing sample listings (safe to re-run)
DELETE FROM opportunity_listings WHERE org_id = 1;

INSERT INTO opportunity_listings
  (org_id, title, description, listing_type, required_skills, required_arts, is_active, created_at)
VALUES

(1, 'Youth Music Project',
 'A community music group working with children aged 8–14. We need someone who can move with kids, express creatively, and collaborate on arrangements.',
 'volunteer',
 '{}',
 '["move","express","collaborate"]',
 1, NOW()),

(1, 'Community Garden Initiative',
 'Regenerative food garden in need of growers, designers, and respectful stewards of the land. Permaculture principles welcome.',
 'project',
 '{}',
 '["grow","respect","collaborate"]',
 1, NOW()),

(1, 'Local History Documentation',
 'Capturing stories from elders in the neighbourhood. Requires keen noticing, clear expression, and first-principles understanding of oral history.',
 'project',
 '{}',
 '["notice","express","understand"]',
 1, NOW()),

(1, 'Peer Mental Health Support Circle',
 'Trained listeners needed for a community circle. Deep feeling awareness, empathetic listening, and a genuine capacity to give without agenda.',
 'volunteer',
 '{}',
 '["feel","listen","give"]',
 1, NOW()),

(1, 'Natural Building Workshop',
 'Learning and building with earth, bamboo, and reclaimed materials. Builders who understand materials, respect ecological limits, and consume thoughtfully.',
 'project',
 '{}',
 '["build","understand","consume"]',
 1, NOW()),

(1, 'Language Exchange & Cultural Bridge',
 'Connecting speakers across languages and cultures. Requires listening with full attention, receiving feedback graciously, and living across cultural difference.',
 'volunteer',
 '{}',
 '["listen","receive","live"]',
 1, NOW()),

(1, 'Food Sovereignty Education Program',
 'Teaching communities to grow, eat, and steward food systems. Connects growing knowledge with eating wisdom and respectful land relationships.',
 'project',
 '{}',
 '["grow","eat","respect"]',
 1, NOW()),

(1, 'Conflict Resolution & Civic Dialogue',
 'Facilitators needed for community disagreements. Requires deep listening, the ability to collaborate under tension, and genuine giving without score-keeping.',
 'volunteer',
 '{}',
 '["listen","collaborate","give"]',
 1, NOW());

-- Verify
SELECT id, title, required_arts FROM opportunity_listings ORDER BY id;
