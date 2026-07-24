-- ============================================================
-- 2026-07-24 — create outreach_drafts (P9: Outreach section)
--
-- Why: the admin Outreach sidebar section was a fully static,
-- hardcoded UNESCO example card with a fake alert('Email sent!')
-- button — no table, no backend route. Charbel's call: build the
-- real review/send/discard mechanics now with placeholder seed
-- data; wire up real org/learner matching to auto-populate this
-- table in a later session.
--
-- Sending itself uses the existing backend/mail.py send_mail()
-- (sendmail via the droplet's already-configured MTA) — no new
-- send infra needed.
--
-- status is a plain VARCHAR, not an ENUM — deliberately, to avoid
-- the ENUM-ALTER friction hit with opportunity_matches.learner_status
-- (see MAINTENANCE.md gotcha, 2026-07-18) on a table we're free to
-- design from scratch.
-- ============================================================

-- ---- PART A: read-only preflight ----
SHOW TABLES LIKE 'outreach_drafts';

-- ---- PART B: create table (idempotent, only migration file for this table) ----
CREATE TABLE IF NOT EXISTS outreach_drafts (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    org_name       VARCHAR(200)  NOT NULL,
    contact_email  VARCHAR(255)  NOT NULL,
    match_count    INT           NOT NULL DEFAULT 0,
    subject        VARCHAR(500)  NOT NULL,
    body           TEXT          NOT NULL,
    status         VARCHAR(20)   NOT NULL DEFAULT 'pending',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at        DATETIME      NULL
);

-- ---- PART C: seed placeholder data (the former hardcoded card, now real) ----
INSERT INTO outreach_drafts (org_name, contact_email, match_count, subject, body, status)
SELECT * FROM (SELECT
    'UNESCO — Youth Arts Facilitator' AS org_name,
    'careers@unesco.org' AS contact_email,
    4 AS match_count,
    'Qualified learners for your Youth Arts Facilitator role' AS subject,
    'Dear UNESCO Recruitment Team,\n\nI am writing on behalf of Surfing the Frequencies, a free global learning platform where learners develop and demonstrate human arts through structured, assessed practice.\n\nWe have identified 4 learners whose demonstrated skills closely match the requirements of your Youth Arts Facilitator listing. Each has completed verified sessions in creativity, cultural competence and communication, and has consented to be introduced to potential opportunities.\n\nIf you would like to review their portfolios and connect directly, please reply to this email or visit our organization portal at build.onehouse.top/org.\n\nWith respect,\nCharbel Haddad\nSurfing the Frequencies' AS body,
    'pending' AS status
) AS seed1
WHERE NOT EXISTS (SELECT 1 FROM outreach_drafts WHERE org_name = 'UNESCO — Youth Arts Facilitator');

INSERT INTO outreach_drafts (org_name, contact_email, match_count, subject, body, status)
SELECT * FROM (SELECT
    'Peace Corps — Community Health Volunteers' AS org_name,
    'partnerships@peacecorps.gov' AS contact_email,
    2 AS match_count,
    'Learners ready for your Community Health Volunteer program' AS subject,
    'Dear Peace Corps Partnerships Team,\n\nI am writing on behalf of Surfing the Frequencies, a free global learning platform where learners develop and demonstrate human arts through structured, assessed practice.\n\nWe have identified 2 learners whose demonstrated skills closely match the requirements of your Community Health Volunteer program. Each has completed verified sessions in care, communication and resilience, and has consented to be introduced to potential opportunities.\n\nIf you would like to review their portfolios and connect directly, please reply to this email or visit our organization portal at build.onehouse.top/org.\n\nWith respect,\nCharbel Haddad\nSurfing the Frequencies' AS body,
    'pending' AS status
) AS seed2
WHERE NOT EXISTS (SELECT 1 FROM outreach_drafts WHERE org_name = 'Peace Corps — Community Health Volunteers');

-- ---- Verify ----
DESCRIBE outreach_drafts;
SELECT id, org_name, contact_email, match_count, status, created_at FROM outreach_drafts;
