-- FreqLearn — verify which sessions contain real CJK characters
-- vs. em-dashes / smart quotes mis-tagged as 'zh'
-- Run on server:
--   mysql freqlearn < scripts/verify_zh_after_fix.sql

SELECT '=== A. Sessions still tagged zh ===' AS '';
SELECT id, LEFT(warmup_prompt, 50) AS preview, HEX(LEFT(warmup_prompt, 30)) AS hex
FROM sessions WHERE language = 'zh' LIMIT 10;

SELECT '' AS '';
SELECT '=== B. Distinct first 2-byte hex prefixes in zh-tagged rows ===' AS '';
SELECT LEFT(HEX(warmup_prompt), 2) AS b1, SUBSTRING(HEX(warmup_prompt), 3, 2) AS b2, COUNT(*) AS n
FROM sessions
WHERE language = 'zh'
  AND warmup_prompt IS NOT NULL
GROUP BY b1, b2
ORDER BY n DESC
LIMIT 20;

SELECT '' AS '';
SELECT '=== C. Same breakdown for vi-tagged rows (sanity check) ===' AS '';
SELECT LEFT(HEX(warmup_prompt), 2) AS b1, SUBSTRING(HEX(warmup_prompt), 3, 2) AS b2, COUNT(*) AS n
FROM sessions
WHERE language = 'vi'
  AND warmup_prompt IS NOT NULL
GROUP BY b1, b2
ORDER BY n DESC
LIMIT 20;