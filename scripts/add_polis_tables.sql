-- ============================================================
-- FreqLearn — add_polis_tables.sql
-- Civic participation tables for the Polis portal.
-- Run: mysql -u freqlearn -p freqlearn < add_polis_tables.sql
-- ============================================================

-- Referenda: civic questions put to a vote
CREATE TABLE IF NOT EXISTS referenda (
  id           INT PRIMARY KEY AUTO_INCREMENT,
  title        VARCHAR(200) NOT NULL,
  description  TEXT,
  scope        ENUM('local','regional','global') DEFAULT 'local',
  bioregion    VARCHAR(100),
  status       ENUM('open','closed','draft') DEFAULT 'open',
  proposed_by  INT NULL,  -- learner_id, NULL for platform-seeded
  opens_at     DATETIME,
  closes_at    DATETIME,
  created_at   DATETIME DEFAULT NOW()
);

-- Votes on referenda (one per learner per referendum)
CREATE TABLE IF NOT EXISTS referendum_votes (
  id             INT PRIMARY KEY AUTO_INCREMENT,
  referendum_id  INT NOT NULL,
  learner_id     INT NOT NULL,
  position       ENUM('support','oppose','abstain') NOT NULL,
  reasoning      TEXT,
  created_at     DATETIME DEFAULT NOW(),
  UNIQUE KEY uq_vote (referendum_id, learner_id),
  FOREIGN KEY (referendum_id) REFERENCES referenda(id) ON DELETE CASCADE
);

-- Discussion comments on referenda
CREATE TABLE IF NOT EXISTS polis_discussions (
  id             INT PRIMARY KEY AUTO_INCREMENT,
  referendum_id  INT NOT NULL,
  learner_id     INT NOT NULL,
  parent_id      INT NULL,   -- for threaded replies
  body           TEXT NOT NULL,
  upvotes        INT DEFAULT 0,
  created_at     DATETIME DEFAULT NOW(),
  FOREIGN KEY (referendum_id) REFERENCES referenda(id) ON DELETE CASCADE
);

-- Civic proposals: ideas submitted by learners
CREATE TABLE IF NOT EXISTS proposals (
  id             INT PRIMARY KEY AUTO_INCREMENT,
  learner_id     INT NOT NULL,
  title          VARCHAR(200) NOT NULL,
  description    TEXT,
  scope          ENUM('local','regional','global') DEFAULT 'local',
  bioregion      VARCHAR(100),
  status         ENUM('submitted','promoted','archived') DEFAULT 'submitted',
  support_count  INT DEFAULT 0,
  created_at     DATETIME DEFAULT NOW()
);

-- Proposal endorsements
CREATE TABLE IF NOT EXISTS proposal_supports (
  proposal_id  INT NOT NULL,
  learner_id   INT NOT NULL,
  created_at   DATETIME DEFAULT NOW(),
  PRIMARY KEY (proposal_id, learner_id),
  FOREIGN KEY (proposal_id) REFERENCES proposals(id) ON DELETE CASCADE
);

-- ── Seed referenda ───────────────────────────────────────────
INSERT INTO referenda (title, description, scope, bioregion, status, opens_at, closes_at) VALUES

('Free daily outdoor play for all children in school',
 'Should every school be required to provide at least one hour of free, unstructured outdoor time each day, regardless of weather or curriculum pressure? Research links outdoor play to emotional regulation, creativity, and long-term learning capacity.',
 'global', NULL, 'open', NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY)),

('Cycling infrastructure over urban car parking',
 'Should city governments prioritise the conversion of on-street car parking into protected cycling lanes and pedestrian space in urban centres? This referendum asks whether the balance of public space should shift toward human-powered movement.',
 'regional', 'Urban bioregions', 'open', NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY)),

('Universal basic income pilot in this bioregion',
 'Should a time-limited universal basic income trial be launched in this bioregion, giving every adult resident a guaranteed monthly income regardless of employment status, to measure effects on health, creativity, and civic participation?',
 'regional', 'Local bioregion', 'open', NOW(), DATE_ADD(NOW(), INTERVAL 60 DAY)),

('30% minimum green space in all urban developments',
 'Should local governments be legally required to ensure that at least 30% of all new urban developments is dedicated to green space — trees, gardens, wetlands, or community food forests — accessible to all residents at no cost?',
 'local', NULL, 'open', NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY)),

('Open source AI for public education globally',
 'Should all AI systems used in public education be mandated to be open source, auditable by the community, and governed by independent civic bodies rather than private corporations?',
 'global', NULL, 'open', NOW(), DATE_ADD(NOW(), INTERVAL 90 DAY));

-- Verify
SELECT id, title, scope, status FROM referenda ORDER BY id;
