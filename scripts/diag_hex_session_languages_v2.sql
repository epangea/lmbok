-- FreqLearn — diagnostic v2: find ACTUAL non-ASCII rows and test regexes against them
-- Run on server:
--   mysql freqlearn < scripts/diag_hex_session_languages_v2.sql
--
-- Fixes from v1:
--   - Filter uses byte-range comparison (CHAR_LENGTH vs LENGTH) instead of broken regex
--   - Tests both Cyrillic HEX regex AND literal Cyrillic regex AND Vietnamese HEX regex
--   - Reports byte-by-byte hex preview of detected non-ASCII rows

SELECT '=== A. Find genuinely non-ASCII rows (LENGTH > CHAR_LENGTH = has multi-byte) ===' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 40)        AS preview,
    CHAR_LENGTH(warmup_prompt)     AS char_len,
    LENGTH(warmup_prompt)          AS byte_len,
    LENGTH(warmup_prompt) - CHAR_LENGTH(warmup_prompt) AS multibyte_bytes
FROM sessions
WHERE LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt)
   OR LENGTH(explore_content) > CHAR_LENGTH(explore_content)
   OR LENGTH(challenge_prompt) > CHAR_LENGTH(challenge_prompt)
   OR LENGTH(reflect_prompt) > CHAR_LENGTH(reflect_prompt)
LIMIT 10;

SELECT '' AS '';
SELECT '=== B. Hex preview of first 3 truly non-ASCII rows ===' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 40)                AS preview,
    HEX(LEFT(warmup_prompt, 30))           AS hex_preview
FROM sessions
WHERE LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt)
LIMIT 3;

SELECT '' AS '';
SELECT '=== C. Test regex against real Cyrillic hex pattern (D0/D1 80-BF) ===' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 40) AS preview,
    HEX(LEFT(warmup_prompt, 30)) AS hex,
    CASE
        WHEN HEX(warmup_prompt) REGEXP 'D[01][89ABCDEF][0-9A-F]' THEN 'CYRILLIC MATCH'
        ELSE 'no cyrillic'
    END AS cyrillic_hex_test
FROM sessions
WHERE LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt)
LIMIT 10;

SELECT '' AS '';
SELECT '=== D. Test regex against Vietnamese diacritics hex patterns ===' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 40) AS preview,
    HEX(LEFT(warmup_prompt, 30)) AS hex,
    CASE
        WHEN HEX(warmup_prompt) REGEXP '(C3A2|C3AA|C3B4|C483|C491|C6A1|C6B0|C482|C490)' THEN 'VIETNAMESE MATCH'
        ELSE 'no vietnamese'
    END AS vietnamese_hex_test
FROM sessions
WHERE LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt)
LIMIT 10;

SELECT '' AS '';
SELECT '=== E. Sample distinct 2-byte UTF-8 prefixes found in warmup_prompt ===' AS '';
SELECT
    LEFT(HEX(warmup_prompt), 2) AS first_byte_hex,
    SUBSTRING(HEX(warmup_prompt), 3, 2) AS second_byte_hex,
    COUNT(*) AS n
FROM sessions
WHERE LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt)
GROUP BY first_byte_hex, second_byte_hex
ORDER BY n DESC
LIMIT 20;

SELECT '' AS '';
SELECT '=== F. Total row counts ===' AS '';
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt) THEN 1 ELSE 0 END) AS has_non_ascii
FROM sessions;