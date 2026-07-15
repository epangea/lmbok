-- ============================================================
-- FreqLearn — migrate: add email verification to learners
-- Run once after deploying updated models.py:
--   mysql freqlearn < scripts/2026-06-23-add-email-verification.sql
-- ============================================================

ALTER TABLE learners
  ADD COLUMN email_verified       BOOLEAN      NOT NULL DEFAULT FALSE,
  ADD COLUMN verification_token   VARCHAR(255) NULL,
  ADD COLUMN verification_expires DATETIME     NULL;

CREATE INDEX idx_verification_token ON learners(verification_token);
