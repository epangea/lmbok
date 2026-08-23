-- ============================================================
-- 2026-08-23 — Admin Newsletter section
--
-- Why: admin panel had no way to broadcast an email to every learner
-- at once. Outreach (2026-07-24) sends one-off emails to orgs;
-- Learner messages (P9.2) send one-off emails to a single learner;
-- this adds the missing "send one email to everyone" case.
--
-- One new table (newsletters) + one new column
-- (learner_preferences.newsletter_opt_out). No FK on newsletters --
-- it logs broadcasts, not per-recipient sends, same reasoning
-- outreach_drafts used for its own status column (plain VARCHAR, not
-- an ENUM, to avoid the ENUM-ALTER friction hit on
-- opportunity_matches.learner_status -- see gotcha table, 2026-07-18).
--
-- newsletter_opt_out defaults FALSE for every row, existing and new --
-- opt-out model, on by default, same as P30's story-email preference.
-- Unlike the 2026-06-26 email_verified migration (which wrongly
-- defaulted existing legacy accounts to a state that then locked them
-- out), there's no equivalent legacy-data trap here: every learner,
-- old or new, should simply start subscribed.
-- ============================================================

-- ---- PART A: read-only preflight — confirm current shape before touching it ----
SHOW TABLES LIKE 'newsletters';
DESCRIBE learner_preferences;

-- ---- PART B: create table (idempotent) ----
START TRANSACTION;

CREATE TABLE IF NOT EXISTS newsletters (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    subject          VARCHAR(500)  NOT NULL,
    body             TEXT          NOT NULL,
    status           VARCHAR(20)   NOT NULL DEFAULT 'draft',   -- draft | sending | sent
    recipient_count  INT           NOT NULL DEFAULT 0,
    sent_count       INT           NOT NULL DEFAULT 0,
    failed_count     INT           NOT NULL DEFAULT 0,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at          DATETIME      NULL
);

-- ---- PART C: new opt-out column on the existing preferences table ----
-- MariaDB's ADD COLUMN ... DEFAULT backfills every existing row with the
-- default value, so no separate UPDATE is needed for current learners.
ALTER TABLE learner_preferences
    ADD COLUMN newsletter_opt_out BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;

-- ---- Verify — don't trust this script's own exit code, count rows independently ----
-- (2026-08-20's domain-taxonomy delete found a real bug where a COMMIT
-- written as a SQL comment instead of a real statement let MariaDB
-- silently roll everything back in batch mode -- confirm with a fresh
-- SELECT after running, not just by watching this script print success.)
DESCRIBE newsletters;
DESCRIBE learner_preferences;
SELECT COUNT(*) AS total_learners FROM learner_preferences;
SELECT COUNT(*) AS opted_out FROM learner_preferences WHERE newsletter_opt_out = TRUE;
