-- ============================================================
-- FreqLearn — fix_org_status_enum.sql
-- Adds 'reviewing' to the opportunity_matches.org_status ENUM.
--
-- Why: routes/orgs.py cycles org_status through
--   pending → reviewing → connected → declined
-- but the DB only had ('pending','interested','declined','connected').
-- MariaDB would silently truncate 'reviewing' to '', breaking the
-- org match-management workflow.
--
-- Safe: MODIFY COLUMN on an ENUM never drops existing values or data.
-- Existing rows with 'pending','interested','declined','connected'
-- are unaffected.
--
-- Run: sudo mysql -u freqlearn -p freqlearn < fix_org_status_enum.sql
-- ============================================================

ALTER TABLE opportunity_matches
  MODIFY COLUMN org_status
    ENUM('pending','reviewing','interested','declined','connected')
    DEFAULT 'pending';

-- Verify
SHOW COLUMNS FROM opportunity_matches WHERE Field = 'org_status';
