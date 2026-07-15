-- FreqLearn — diagnostic: are the 157 'vi' rows really Vietnamese?
-- Run on server:
--   mysql freqlearn < scripts/diag_vietnamese_overcount.sql
--
-- Hypothesis: many of the 157 rows tagged 'vi' may actually be English
-- with Spanish/French/Portuguese accents (which my Vietnamese regex
-- matched because the regex uses Latin-1 supplement chars that are
-- shared across many languages).

SET NAMES utf8mb4;

-- 1. Show first 20 vi rows so we can spot-check
SELECT '=== A. First 20 vi-tagged rows ===' AS '';
SELECT id, LEFT(warmup_prompt, 80) AS preview
FROM sessions WHERE language = 'vi'
ORDER BY id LIMIT 20;

-- 2. Distinct 2-byte hex prefixes in vi rows
SELECT '=== B. Distinct first-2-byte hex prefixes in vi-tagged rows ===' AS '';
SELECT LEFT(HEX(warmup_prompt), 2) AS b1, SUBSTRING(HEX(warmup_prompt), 3, 2) AS b2, COUNT(*) AS n
FROM sessions WHERE language = 'vi' AND warmup_prompt IS NOT NULL
GROUP BY b1, b2 ORDER BY n DESC LIMIT 20;

-- 3. Count rows with Vietnamese-specific markers (ư ơ đ)
--    These are diagnostic for Vietnamese and not in Spanish/French/Portuguese
SELECT '=== C. Rows with Vietnamese-specific markers ===' AS '';
SELECT COUNT(*) AS has_vietnamese_specific
FROM sessions
WHERE language = 'vi'
  AND (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
  );

-- 4. Count vi rows that are LIKELY Spanish (have ñ ¿ ¡ or Spanish accents but no Vietnamese markers)
SELECT '=== D. Rows likely Spanish mis-tagged as vi ===' AS '';
SELECT COUNT(*) AS likely_spanish_mistagged
FROM sessions
WHERE language = 'vi'
  AND (
        warmup_prompt REGEXP '[ñ¿¡]'
     OR explore_content REGEXP '[ñ¿¡]'
  )
  AND NOT (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483'
  );

-- 5. Count vi rows that are LIKELY Portuguese (ã õ, no Vietnamese markers)
SELECT '=== E. Rows likely Portuguese mis-tagged as vi ===' AS '';
SELECT COUNT(*) AS likely_portuguese_mistagged
FROM sessions
WHERE language = 'vi'
  AND (
        warmup_prompt REGEXP '[ãõÃÕ]'
     OR explore_content REGEXP '[ãõÃÕ]'
  )
  AND NOT (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483'
  );

-- 6. Sample vi rows that have NO Vietnamese-specific markers
SELECT '=== F. vi rows WITHOUT Vietnamese-specific markers (sample) ===' AS '';
SELECT id, LEFT(warmup_prompt, 80) AS preview
FROM sessions
WHERE language = 'vi'
  AND NOT (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D'
  )
LIMIT 20;