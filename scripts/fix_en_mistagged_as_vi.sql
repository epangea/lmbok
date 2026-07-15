-- fix_en_mistagged_as_vi.sql
-- 2026-06-28 — written after diag_vietnamese_overcount.sql output confirmed
-- that 151 of 157 vi-tagged rows are actually ENGLISH, not Spanish/Portuguese.
--
-- Vietnamese-specific byte markers (UTF-8):
--   C6 B0 = ư (U+01B0)
--   C6 A1 = ơ (U+01A1)
--   C4 91 = đ (U+0111)
--   C4 83 = ă (U+0103)
--
-- Strategy: re-tag every vi row that does NOT contain any of these 4 byte
-- pairs back to 'en'. Keep the 6 rows that have the markers as 'vi'.
--
-- Expected post-fix distribution (from 1799 sessions):
--   en  ≈ 1791   (was 1640, +151 from this fix)
--   vi  = 6      (genuine Vietnamese)
--   es  = 1
--   ru  = 1
--   total = 1799
--
-- BACKUP THE DB BEFORE RUNNING.
--   mysqldump freqlearn > /var/backups/freqlearn/freqlearn_$(date +%Y%m%d_%H%M%S).sql

SET NAMES utf8mb4;

-- Preview what we're about to change (run this first if you want to verify)
-- SELECT id, language, LEFT(preview, 80) AS preview
-- FROM sessions
-- WHERE language = 'vi'
--   AND NOT (preview LIKE CONVERT(_utf8mb4 x'C6B0' USING utf8mb4) OR
--            preview LIKE CONVERT(_utf8mb4 x'C6A1' USING utf8mb4) OR
--            preview LIKE CONVERT(_utf8mb4 x'C491' USING utf8mb4) OR
--            preview LIKE CONVERT(_utf8mb4 x'C483' USING utf8mb4));
-- Should show ~151 rows.

-- The fix: UPDATE
UPDATE sessions
SET language = 'en'
WHERE language = 'vi'
  AND NOT (
    preview LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin OR
    preview LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin OR
    preview LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin OR
    preview LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  );

-- Verify post-fix
SELECT '=== Post-fix language distribution ===' AS info;
SELECT language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;

-- Should show:
--   en  ≈ 1791
--   vi  = 6
--   es  = 1
--   ru  = 1
--   total = 1799