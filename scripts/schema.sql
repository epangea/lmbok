-- ============================================================
-- FreqLearn — schema.sql v2
-- Updated to reflect the 15 Arts framework from "To Be Human"
-- by Charbel Haddad, Vietnam 2026
--
-- Three arts → 15 individual arts → 78 base skills
-- Five development phases: prenascent, child, adolescent, adult, elder
-- Greek space naming: Agora · Academy · Mouseion · Stoa · Pnyx
--
-- Run as: mysql -u freqlearn -p freqlearn < schema.sql
-- ============================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS messages, opportunity_matches, opportunity_listings,
  organizations, radar_snapshots, reflections, activity_log, learner_streaks,
  sessions, skill_evidence, learner_skill_progress, learner_art_progress,
  learner_preferences, learners, skill_prerequisites, arts_skills, skills,
  leckos, arts, arts_group, dev_phases, refresh_tokens;
SET FOREIGN_KEY_CHECKS = 1;

-- ── Development phases ────────────────────────────────────────
CREATE TABLE dev_phases (
    id          TINYINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(30) NOT NULL,
    slug        VARCHAR(30) NOT NULL UNIQUE,
    age_range   VARCHAR(20),
    description TEXT,
    sort_order  TINYINT UNSIGNED DEFAULT 0
) ENGINE=InnoDB;

-- ── The three arts groups ─────────────────────────────────────
CREATE TABLE arts_group (
    id          TINYINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(40)  NOT NULL,
    slug        VARCHAR(40)  NOT NULL UNIQUE,
    tagline     VARCHAR(160),
    description TEXT,
    color_hex   VARCHAR(7),
    sort_order  TINYINT UNSIGNED DEFAULT 0
) ENGINE=InnoDB;

-- ── The 15 individual arts ────────────────────────────────────
CREATE TABLE arts (
    id          TINYINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    group_id    TINYINT UNSIGNED NOT NULL,
    name        VARCHAR(40)  NOT NULL,
    slug        VARCHAR(40)  NOT NULL UNIQUE,
    tagline     VARCHAR(200),
    description TEXT,
    sort_order  TINYINT UNSIGNED DEFAULT 0,
    FOREIGN KEY (group_id) REFERENCES arts_group(id)
) ENGINE=InnoDB;

-- ── Base skills (78+) ─────────────────────────────────────────
CREATE TABLE skills (
    id                  SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(120) NOT NULL,
    slug                VARCHAR(120) NOT NULL UNIQUE,
    subcategory         VARCHAR(80),
    description         TEXT,
    learning_domain     VARCHAR(80),
    skill_type          SET('cognitive','affective','psychomotor') NOT NULL DEFAULT 'cognitive',
    developmental_stage VARCHAR(80),
    max_level           TINYINT UNSIGNED DEFAULT 3,
    is_active           BOOLEAN DEFAULT TRUE,
    sort_order          SMALLINT UNSIGNED DEFAULT 0
) ENGINE=InnoDB;

-- ── Skills ↔ Arts (many-to-many) ─────────────────────────────
CREATE TABLE arts_skills (
    art_id      TINYINT UNSIGNED  NOT NULL,
    skill_id    SMALLINT UNSIGNED NOT NULL,
    is_primary  BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (art_id, skill_id),
    FOREIGN KEY (art_id)   REFERENCES arts(id),
    FOREIGN KEY (skill_id) REFERENCES skills(id)
) ENGINE=InnoDB;

-- ── Skill prerequisites ───────────────────────────────────────
CREATE TABLE skill_prerequisites (
    skill_id        SMALLINT UNSIGNED NOT NULL,
    requires_skill  SMALLINT UNSIGNED NOT NULL,
    min_level       TINYINT UNSIGNED DEFAULT 1,
    PRIMARY KEY (skill_id, requires_skill),
    FOREIGN KEY (skill_id)       REFERENCES skills(id),
    FOREIGN KEY (requires_skill) REFERENCES skills(id)
) ENGINE=InnoDB;

-- ── LECKO — Learning Experience Knowledge Chunk Object ────────
CREATE TABLE leckos (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    art_id          TINYINT UNSIGNED NOT NULL,
    phase_id        TINYINT UNSIGNED NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    learning_domain VARCHAR(80),
    skill_type      SET('cognitive','affective','psychomotor') DEFAULT 'cognitive',
    assessment_type SET('mindset','task','communication','portfolio','community','peer') DEFAULT 'task',
    assessment_desc TEXT,
    community_need  TEXT,
    source_credit   VARCHAR(300),
    evidence_url    VARCHAR(500),
    utility_score   DECIMAL(3,2) DEFAULT 0.00,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (art_id)   REFERENCES arts(id),
    FOREIGN KEY (phase_id) REFERENCES dev_phases(id),
    INDEX idx_art_phase (art_id, phase_id)
) ENGINE=InnoDB;

-- ── Learners ──────────────────────────────────────────────────
CREATE TABLE learners (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(40)  NOT NULL UNIQUE,
    email           VARCHAR(180) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(80),
    birth_year      SMALLINT UNSIGNED,
    phase_id        TINYINT UNSIGNED,
    avatar_emoji    VARCHAR(8)   DEFAULT NULL,
    avatar_color    VARCHAR(7)   DEFAULT '#1D9E75',
    timezone        VARCHAR(50)  DEFAULT 'UTC',
    language        VARCHAR(10)  DEFAULT 'en',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    DATETIME,
    FOREIGN KEY (phase_id) REFERENCES dev_phases(id),
    INDEX idx_email (email)
) ENGINE=InnoDB;

CREATE TABLE learner_preferences (
    learner_id              INT UNSIGNED PRIMARY KEY,
    daily_goal_minutes      TINYINT UNSIGNED DEFAULT 20,
    preferred_session_time  VARCHAR(20),
    notify_streak           BOOLEAN DEFAULT TRUE,
    allow_matching          BOOLEAN DEFAULT TRUE,
    profile_visible         BOOLEAN DEFAULT FALSE,
    tier                    TINYINT UNSIGNED DEFAULT 1,
    updated_at              DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ── Art progress (three-axis radar scores) ────────────────────
CREATE TABLE learner_art_progress (
    learner_id  INT UNSIGNED     NOT NULL,
    art_id      TINYINT UNSIGNED NOT NULL,
    score       DECIMAL(4,3) DEFAULT 0.000,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (learner_id, art_id),
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    FOREIGN KEY (art_id)     REFERENCES arts(id)
) ENGINE=InnoDB;

-- ── Skill progress ────────────────────────────────────────────
CREATE TABLE learner_skill_progress (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id          INT UNSIGNED      NOT NULL,
    skill_id            SMALLINT UNSIGNED NOT NULL,
    current_level       TINYINT UNSIGNED DEFAULT 0,
    evidence_count      TINYINT UNSIGNED DEFAULT 0,
    recall_count        TINYINT UNSIGNED DEFAULT 0,
    transfer_count      TINYINT UNSIGNED DEFAULT 0,
    self_assessed_level TINYINT UNSIGNED,
    last_practiced_at   DATETIME,
    next_review_at      DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_learner_skill (learner_id, skill_id),
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id)   REFERENCES skills(id),
    INDEX idx_next_review (learner_id, next_review_at)
) ENGINE=InnoDB;

CREATE TABLE skill_evidence (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    progress_id     INT UNSIGNED NOT NULL,
    level_achieved  TINYINT UNSIGNED NOT NULL,
    evidence_type   ENUM('mindset','task','communication','portfolio','community','peer') NOT NULL,
    description     TEXT,
    content_url     VARCHAR(500),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (progress_id) REFERENCES learner_skill_progress(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ── Sessions (the Academy) ────────────────────────────────────
CREATE TABLE sessions (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id          INT UNSIGNED      NOT NULL,
    art_id              TINYINT UNSIGNED  NOT NULL,
    lecko_id            INT UNSIGNED,
    primary_skill_id    SMALLINT UNSIGNED NOT NULL,
    secondary_skill_ids JSON,
    title               VARCHAR(160),
    recommended_by      ENUM('engine','learner','admin') DEFAULT 'engine',
    engine_reasoning    JSON,
    status              ENUM('scheduled','in_progress','completed','skipped') DEFAULT 'scheduled',
    phase_reached       TINYINT UNSIGNED DEFAULT 0,
    duration_seconds    SMALLINT UNSIGNED,
    xp_earned           TINYINT UNSIGNED DEFAULT 0,
    warmup_prompt       TEXT,
    explore_content     TEXT,
    challenge_prompt    TEXT,
    reflect_prompt      TEXT,
    assess_question     JSON,
    challenge_response  TEXT,
    reflect_response    TEXT,
    assess_score        TINYINT UNSIGNED,
    started_at          DATETIME,
    completed_at        DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id)       REFERENCES learners(id) ON DELETE CASCADE,
    FOREIGN KEY (art_id)           REFERENCES arts(id),
    FOREIGN KEY (lecko_id)         REFERENCES leckos(id),
    FOREIGN KEY (primary_skill_id) REFERENCES skills(id),
    INDEX idx_learner_sessions (learner_id, created_at)
) ENGINE=InnoDB;

-- ── Streaks + activity ────────────────────────────────────────
CREATE TABLE learner_streaks (
    learner_id          INT UNSIGNED PRIMARY KEY,
    current_streak      SMALLINT UNSIGNED DEFAULT 0,
    longest_streak      SMALLINT UNSIGNED DEFAULT 0,
    last_activity_date  DATE,
    total_sessions      SMALLINT UNSIGNED DEFAULT 0,
    total_xp            INT UNSIGNED DEFAULT 0,
    total_minutes       INT UNSIGNED DEFAULT 0,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE activity_log (
    learner_id      INT UNSIGNED NOT NULL,
    activity_date   DATE        NOT NULL,
    sessions_done   TINYINT UNSIGNED DEFAULT 0,
    xp_earned       SMALLINT UNSIGNED DEFAULT 0,
    minutes_spent   SMALLINT UNSIGNED DEFAULT 0,
    PRIMARY KEY (learner_id, activity_date),
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ── Radar snapshots (the Agora) ───────────────────────────────
CREATE TABLE radar_snapshots (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id          INT UNSIGNED NOT NULL,
    score_being         DECIMAL(4,3) DEFAULT 0.000,
    score_becoming      DECIMAL(4,3) DEFAULT 0.000,
    score_connecting    DECIMAL(4,3) DEFAULT 0.000,
    art_scores          JSON NOT NULL,
    triggered_by        ENUM('session_complete','manual','weekly_auto') DEFAULT 'session_complete',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    INDEX idx_snapshots (learner_id, created_at)
) ENGINE=InnoDB;

-- ── Reflections (the Stoa) ────────────────────────────────────
CREATE TABLE reflections (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id  INT UNSIGNED     NOT NULL,
    session_id  INT UNSIGNED,
    art_id      TINYINT UNSIGNED,
    prompt      TEXT,
    body        TEXT NOT NULL,
    is_private  BOOLEAN DEFAULT TRUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (art_id)     REFERENCES arts(id),
    INDEX idx_learner_reflect (learner_id, created_at)
) ENGINE=InnoDB;

-- ── Organizations + matching (the Pnyx) ──────────────────────
CREATE TABLE organizations (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(160) NOT NULL,
    slug            VARCHAR(160) NOT NULL UNIQUE,
    description     TEXT,
    website         VARCHAR(300),
    contact_email   VARCHAR(180),
    org_type        ENUM('employer','ngo','school','community','permaculture','other') DEFAULT 'other',
    is_verified     BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE opportunity_listings (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    org_id          INT UNSIGNED NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    listing_type    ENUM('job','volunteer','project','collaboration','apprenticeship') DEFAULT 'project',
    required_skills JSON NOT NULL,
    required_arts   JSON,
    phase_min       TINYINT UNSIGNED,
    phase_max       TINYINT UNSIGNED,
    is_active       BOOLEAN DEFAULT TRUE,
    source_url      VARCHAR(500),
    scavenged       BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
) ENGINE=InnoDB;

CREATE TABLE opportunity_matches (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id      INT UNSIGNED NOT NULL,
    listing_id      INT UNSIGNED NOT NULL,
    match_score     TINYINT UNSIGNED,
    skills_met      JSON,
    skills_gap      JSON,
    arts_met        JSON,
    learner_status  ENUM('pending','interested','declined','connected') DEFAULT 'pending',
    org_status      ENUM('pending','interested','declined','connected') DEFAULT 'pending',
    matched_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_match (learner_id, listing_id),
    FOREIGN KEY (learner_id)  REFERENCES learners(id),
    FOREIGN KEY (listing_id)  REFERENCES opportunity_listings(id)
) ENGINE=InnoDB;

CREATE TABLE messages (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    match_id        INT UNSIGNED NOT NULL,
    sender_type     ENUM('learner','org','admin') NOT NULL,
    sender_id       INT UNSIGNED NOT NULL,
    body            TEXT NOT NULL,
    read_at         DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES opportunity_matches(id),
    INDEX idx_match_messages (match_id, created_at)
) ENGINE=InnoDB;

-- ── Auth ──────────────────────────────────────────────────────
CREATE TABLE refresh_tokens (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    learner_id  INT UNSIGNED NOT NULL,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,
    expires_at  DATETIME NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (learner_id) REFERENCES learners(id) ON DELETE CASCADE,
    INDEX idx_token (token_hash)
) ENGINE=InnoDB;

-- ════════════════════════════════════════════════════════════
-- SEED DATA
-- ════════════════════════════════════════════════════════════

INSERT INTO dev_phases (name, slug, age_range, description, sort_order) VALUES
('Prenascent', 'prenascent', '0–2',   'The parent is the primary learner. The child absorbs everything.',         1),
('Child',       'child',      '3–11',  'Curiosity-led exploration. Play as the primary mode of learning.',        2),
('Adolescent',  'adolescent', '12–17', 'Identity formation. Abstract reasoning emerges. Peers deepen.',          3),
('Adult',       'adult',      '18–60', 'Generativity. Building, leading, contributing, mentoring.',              4),
('Elder',       'elder',      '61+',   'Wisdom transmission. Integration. Legacy and acceptance.',               5);

INSERT INTO arts_group (name, slug, tagline, color_hex, sort_order) VALUES
('Being',      'being',      'Developing the self through inward awareness',       '#1D9E75', 1),
('Becoming',   'becoming',   'Developing the self through outward awareness',      '#4D9EFF', 2),
('Connecting', 'connecting', 'Developing together with our environments',          '#FFB830', 3);

INSERT INTO arts (group_id, name, slug, tagline, sort_order) VALUES
(1, 'Move',        'move',        'Inner-connectedness and physical growth',                      1),
(1, 'Eat',         'eat',         'Outer-connectedness and bodily nourishment',                   2),
(1, 'Feel',        'feel',        'Inward awareness and emotional growth',                        3),
(1, 'Notice',      'notice',      'Outward awareness without judgement',                          4),
(1, 'Express',     'express',     'Inward-outward clarity and creative growth',                   5),
(2, 'Live',        'live',        'Personal needs, rights and civil duties',                      6),
(2, 'Listen',      'listen',      'Empathy, understanding and civil discourse',                   7),
(2, 'Give',        'give',        'Compassion, care and selfless scaffolding',                    8),
(2, 'Receive',     'receive',     'Acceptance, humility and equity',                              9),
(2, 'Collaborate', 'collaborate', 'Shared vision and universal inclusivity',                     10),
(3, 'Understand',  'understand',  'First principles, science and theory of knowledge',           11),
(3, 'Respect',     'respect',     'The golden rule extended to all living things',               12),
(3, 'Build',       'build',       'Bioconstruction, green design and accessibility',             13),
(3, 'Grow',        'grow',        'Regenerative agriculture and food sovereignty',               14),
(3, 'Consume',     'consume',     'Water, resource and energy stewardship',                      15);

-- ════════════════════════════════════════════════════════════
-- Done. Run seed_skills.py next to populate skills → arts mapping.
-- ════════════════════════════════════════════════════════════
