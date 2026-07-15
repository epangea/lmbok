-- ============================================================
-- FreqLearn — Polis tables migration + seed
-- Run: sudo mysql freqlearn < polis_migrate.sql
-- Safe to re-run: uses CREATE TABLE IF NOT EXISTS + INSERT IGNORE
-- ============================================================

-- Always dump first:
-- sudo mysqldump freqlearn > /root/freqlearn_before_polis_$(date +%Y%m%d).sql

-- ── Tables ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS referenda (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  title       VARCHAR(300) NOT NULL,
  description TEXT,
  scope       ENUM('local','regional','global') NOT NULL DEFAULT 'global',
  bioregion   VARCHAR(100),
  status      ENUM('draft','open','closed','archived') NOT NULL DEFAULT 'open',
  blueprint_pillar VARCHAR(100),
  opens_at    DATETIME DEFAULT NULL,
  closes_at   DATETIME DEFAULT NULL,
  created_at  DATETIME NOT NULL DEFAULT NOW()
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS referendum_votes (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  referendum_id  INT NOT NULL,
  learner_id     INT NOT NULL,
  position       ENUM('support','oppose','abstain') NOT NULL,
  reasoning      TEXT,
  created_at     DATETIME NOT NULL DEFAULT NOW(),
  UNIQUE KEY uq_ref_learner (referendum_id, learner_id),
  FOREIGN KEY (referendum_id) REFERENCES referenda(id) ON DELETE CASCADE,
  FOREIGN KEY (learner_id)    REFERENCES learners(id)  ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS proposals (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  learner_id    INT NOT NULL,
  title         VARCHAR(300) NOT NULL,
  description   TEXT,
  scope         ENUM('local','regional','global') NOT NULL DEFAULT 'local',
  bioregion     VARCHAR(100),
  status        ENUM('open','elevated','archived') NOT NULL DEFAULT 'open',
  support_count INT NOT NULL DEFAULT 0,
  created_at    DATETIME NOT NULL DEFAULT NOW(),
  FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS proposal_supports (
  proposal_id INT NOT NULL,
  learner_id  INT NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT NOW(),
  PRIMARY KEY (proposal_id, learner_id),
  FOREIGN KEY (proposal_id) REFERENCES proposals(id)  ON DELETE CASCADE,
  FOREIGN KEY (learner_id)  REFERENCES learners(id)   ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS polis_discussions (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  referendum_id  INT NOT NULL,
  learner_id     INT NOT NULL,
  parent_id      INT DEFAULT NULL,
  body           TEXT NOT NULL,
  upvotes        INT NOT NULL DEFAULT 0,
  created_at     DATETIME NOT NULL DEFAULT NOW(),
  FOREIGN KEY (referendum_id) REFERENCES referenda(id)          ON DELETE CASCADE,
  FOREIGN KEY (learner_id)    REFERENCES learners(id)           ON DELETE CASCADE,
  FOREIGN KEY (parent_id)     REFERENCES polis_discussions(id)  ON DELETE SET NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ── Seed: 5 referenda mapped to Blueprint pillars ─────────────
-- INSERT IGNORE means safe to re-run (no duplicates on id conflict)

INSERT IGNORE INTO referenda (id, title, description, scope, status, blueprint_pillar, closes_at, created_at) VALUES

(1,
 'Should lifelong learning be treated as a human right, not a product?',
 'Education today is largely a credential market — paid, gatekept, and time-limited. THE BLUEPRINT proposes that learning is a lifelong human practice, not a product to be bought. Do you support reframing learning as a universal right, with freely accessible resources and community mentorship replacing institutional gatekeeping?',
 'global', 'open', 'Personal Growth',
 DATE_ADD(NOW(), INTERVAL 90 DAY), NOW()),

(2,
 'Should communities have the right to grow at least 50% of their own food locally?',
 'Industrial food systems are fragile, polluting, and often disconnected from the land. THE BLUEPRINT envisions bioregional food sovereignty — communities that can feed themselves from nearby ecosystems. Do you support the principle that every bioregion should work toward producing at least half its own food through regenerative, cooperative practices?',
 'global', 'open', 'Food',
 DATE_ADD(NOW(), INTERVAL 90 DAY), NOW()),

(3,
 'Should renewable energy be community-owned rather than controlled by corporations or states?',
 'Energy is infrastructure — like water or roads, it shapes everything. When energy is owned by distant corporations, communities lose autonomy and resilience. THE BLUEPRINT proposes community energy cooperatives as the default model: locally generated, locally governed, surplus shared. Do you support community ownership as the primary model for energy systems?',
 'global', 'open', 'Energy',
 DATE_ADD(NOW(), INTERVAL 90 DAY), NOW()),

(4,
 'Should "value exchange" move beyond money — incorporating time, care, and ecological contribution?',
 'Money measures what markets value, not what communities need. THE BLUEPRINT envisions a richer value system where time spent teaching, caring for others, or restoring ecosystems is formally recognised and exchangeable. Do you support developing multi-dimensional value exchange systems alongside (or instead of) purely monetary ones?',
 'global', 'open', 'Value Exchange',
 DATE_ADD(NOW(), INTERVAL 90 DAY), NOW()),

(5,
 'Should cultural heritage be collectively stewarded — not owned, not commodified?',
 'Language, music, ritual, and story are the living tissue of human culture. When they become intellectual property or tourist spectacle, they lose their meaning. THE BLUEPRINT proposes that culture is a commons — maintained by communities, freely shared, and protected from commodification. Do you support treating cultural heritage as a shared trust rather than private or national property?',
 'global', 'open', 'Culture',
 DATE_ADD(NOW(), INTERVAL 90 DAY), NOW());

-- ── Verify ────────────────────────────────────────────────────
SELECT id, LEFT(title,60) AS title, blueprint_pillar, status FROM referenda;
