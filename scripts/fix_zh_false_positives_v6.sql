-- FreqLearn — fix zh false positives v6 (heuristic: ratio of multi-byte to total)
-- Run on server AFTER fix_zh_false_positives_v5.sql:
--   mysql freqlearn < scripts/fix_zh_false_positives_v6.sql
--
-- Why v5 still over-tagged (1604 rows still zh):
--   The CJK regex matches `E[4-9]B[89ABCDEF][0-9A-F]` which fires when ANY
--   CJK-like byte sequence appears ANYWHERE in the row. Many English
--   sessions have a stray Chinese character somewhere (e.g., a proper noun,
--   a stray test artifact, an accidental paste). 1 Chinese character in
--   a 500-char English row tags the whole row as zh.
--
-- Fix: ratio heuristic. Count multi-byte bytes; if < 10% of total, treat as English.
--       This catches "mostly English with 1 stray CJK char" without losing
--       genuinely Chinese-dominant rows.

SET NAMES utf8mb4;

-- Step 1: For each row tagged 'zh', compute the ratio of multi-byte bytes
--         to total bytes across all 4 content columns combined
DROP TEMPORARY TABLE IF EXISTS zh_analysis;
CREATE TEMPORARY TABLE zh_analysis AS
SELECT
    id,
    LENGTH(COALESCE(warmup_prompt,'')    ) + LENGTH(COALESCE(explore_content,'')  ) +
    LENGTH(COALESCE(challenge_prompt,'') ) + LENGTH(COALESCE(reflect_prompt,'')    ) AS total_bytes,
    LENGTH(COALESCE(warmup_prompt,'')    ) - CHAR_LENGTH(COALESCE(warmup_prompt,'')    ) +
    LENGTH(COALESCE(explore_content,'')  ) - CHAR_LENGTH(COALESCE(explore_content,'')  ) +
    LENGTH(COALESCE(challenge_prompt,'') ) - CHAR_LENGTH(COALESCE(challenge_prompt,'') ) +
    LENGTH(COALESCE(reflect_prompt,'')   ) - CHAR_LENGTH(COALESCE(reflect_prompt,'')   ) AS multibyte_bytes
FROM sessions
WHERE language = 'zh';

-- Step 2: Re-tag rows where multibyte < 5% of total as 'en'
--         (genuinely English with stray non-ASCII bytes)
UPDATE sessions s
JOIN zh_analysis za ON s.id = za.id
SET s.language = 'en'
WHERE s.language = 'zh'
  AND za.total_bytes > 0
  AND (za.multibyte_bytes * 1.0 / za.total_bytes) < 0.05;

-- Step 3: Re-tag rows where multibyte is 5-50% as 'und'
--         (mixed content, ambiguous)
UPDATE sessions s
JOIN zh_analysis za ON s.id = za.id
SET s.language = 'und'
WHERE s.language = 'zh'
  AND za.total_bytes > 0
  AND (za.multibyte_bytes * 1.0 / za.total_bytes) BETWEEN 0.05 AND 0.50;

-- Step 4: Show what's STILL tagged zh (should be rows where multibyte > 50%)
SELECT '=== Still zh after ratio heuristic (should be near-empty) ===' AS '';
SELECT s.id, LEFT(s.warmup_prompt, 60) AS preview, za.multibyte_bytes, za.total_bytes
FROM sessions s
JOIN zh_analysis za ON s.id = za.id
WHERE s.language = 'zh'
LIMIT 10;

-- Step 5: Final distribution
SELECT '=== Final distribution ===' AS '';
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;

DROP TEMPORARY TABLE IF EXISTS zh_analysis;