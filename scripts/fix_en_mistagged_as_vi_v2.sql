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
-- Strategy: re-tag every vi row whose text content contains NONE of the
-- 4 Vietnamese-specific byte pairs back to 'en'. We check every text column
-- on the sessions table (warmup_prompt, explore_content, challenge_prompt,
-- challenge_response, reflect_prompt, reflect_response) plus the JSON-in-
-- LONGTEXT fields (engine_reasoning, assess_question) by casting to text.
-- A row is kept as 'vi' only if AT LEAST ONE of those columns contains
-- a Vietnamese-specific byte pair.
--
-- The challenge: MariaDB LIKE is per-column, so we OR together per-column
-- checks instead of trying to concatenate them.
--
-- The 12 rows that survived the 2026-06-28 partial cleanup
-- (challenge_response IS NULL AND engine_reasoning IS NULL) all have
-- non-empty text in warmup_prompt / explore_content / challenge_prompt,
-- and that text is English. This script catches those plus any other
-- vi-tagged rows where the text is fully English.
--
-- Expected post-fix distribution (from 1799 sessions):
--   en  ≈ 1791   (was 1640, +151 from the 2026-06-27 fix script that ran
--                 to completion, plus any remaining rows)
--   vi  ≈ 6-12   (genuine Vietnamese — exact count depends on whether
--                 the 6 "Vietnamese-specific bytes" rows from 2026-06-27
--                 have been preserved)
--   es  = 1
--   ru  = 1
--   total = 1799
--
-- BACKUP THE DB BEFORE RUNNING.
--   mysqldump freqlearn > /var/backups/freqlearn/freqlearn_$(date +%Y%m%d_%H%M%S).sql

SET NAMES utf8mb4;

-- Per-column Vietnamese-byte checks. A row is "genuine Vietnamese" if
-- ANY of its text columns contains one of the 4 VN byte pairs.
-- We use NULL-safe wrappers so empty/NULL columns don't make the whole
-- expression NULL (which would exclude them from the "is VN" set).

-- Step 1: preview what we're about to change (run this first if you want to verify)
-- Rows that will be flipped to 'en' = vi rows where ALL text columns lack VN bytes.
-- Should be roughly the leftover 12 from the 2026-06-28 partial cleanup, plus
-- any other vi rows with English content in every text column.
SELECT id, language, created_at,
       LEFT(warmup_prompt,     60) AS warmup,
       LEFT(explore_content,   60) AS explore,
       LEFT(challenge_prompt,  60) AS challenge,
       LEFT(challenge_response,60) AS challenge_resp,
       LEFT(reflect_response,  60) AS reflect_resp
FROM sessions
WHERE language = 'vi'
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
ORDER BY created_at;

-- Step 2: the actual UPDATE. Wrapped so a long WHERE doesn't get cut off.
-- Flip every vi row to 'en' when no text column contains a Vietnamese byte.
UPDATE sessions
SET language = 'en'
WHERE language = 'vi'
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(warmup_prompt,     '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(explore_content,   '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_prompt,  '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(challenge_response,'') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C6B0' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C6A1' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C491' USING utf8mb4) COLLATE utf8mb4_bin
  AND COALESCE(reflect_response,  '') NOT LIKE CONVERT(X'C483' USING utf8mb4) COLLATE utf8mb4_bin;

-- Step 3: verify
SELECT '=== Post-fix language distribution ===' AS info;
SELECT language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;

-- Expected after this script + the 2026-06-28 partial cleanup:
--   en  ≈ 1791
--   vi  = 6  (the 6 rows with genuine Vietnamese-specific bytes
--             from 2026-06-27 diag, IF none of them were caught by
--             today's partial fix)
--   es  = 1
--   ru  = 1
--   total = 1799