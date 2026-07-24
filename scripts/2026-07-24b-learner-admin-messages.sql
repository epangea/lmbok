-- ============================================================
-- 2026-07-24b — create learner_admin_messages (P9.2: Learners
-- admin messaging)
--
-- Why: part of finalizing the admin Learners page — lets admins
-- send a composed email to a learner (validate/support/congratulate/
-- notify-of-org-interest/custom) via the existing mail.send_mail(),
-- and keeps a simple audit trail of what was sent and when.
--
-- No new send infra — reuses backend/mail.py, same as the Outreach
-- table added earlier today (2026-07-24-outreach-drafts.sql).
-- ============================================================

-- ---- PART A: read-only preflight ----
SHOW TABLES LIKE 'learner_admin_messages';

-- ---- PART B: create table (idempotent, only migration file for this table) ----
CREATE TABLE IF NOT EXISTS learner_admin_messages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    learner_id  INT UNSIGNED  NOT NULL,
    template    VARCHAR(30)   NOT NULL DEFAULT 'custom',
    subject     VARCHAR(500)  NOT NULL,
    body        TEXT          NOT NULL,
    sent_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_lam_learner FOREIGN KEY (learner_id) REFERENCES learners(id)
);

-- ---- Verify ----
DESCRIBE learner_admin_messages;
SELECT COUNT(*) AS row_count FROM learner_admin_messages;
