-- FreqLearn — diagnostic: see actual hex bytes of Cyrillic text in sessions
-- Run on server:
--   mysql freqlearn < scripts/diag_hex_session_languages.sql

SELECT '--- Raw text + hex of first 5 non-ASCII rows ---' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 30)               AS preview,
    HEX(LEFT(warmup_prompt, 20))          AS hex_first_20_bytes,
    CHAR_LENGTH(warmup_prompt)            AS char_len,
    LENGTH(warmup_prompt)                 AS byte_len
FROM sessions
WHERE warmup_prompt REGEXP '[^\\x00-\\x7F]'
LIMIT 5;

SELECT '' AS '';
SELECT '--- Test: does [А-Яа-я] match Cyrillic? ---' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 30) AS preview,
    CASE
        WHEN warmup_prompt REGEXP '[А-Яа-яЁё]' THEN 'MATCH'
        ELSE 'no match'
    END AS cyrillic_class_test
FROM sessions
WHERE warmup_prompt REGEXP '[^\\x00-\\x7F]'
LIMIT 5;

SELECT '' AS '';
SELECT '--- Test: does HEX-based D0/D1 prefix match? ---' AS '';
SELECT
    id,
    LEFT(warmup_prompt, 30) AS preview,
    CASE
        WHEN HEX(warmup_prompt) REGEXP 'D[01][89ABCDEF][0-9A-F]' THEN 'MATCH'
        ELSE 'no match'
    END AS hex_d0_d1_test
FROM sessions
WHERE warmup_prompt REGEXP '[^\\x00-\\x7F]'
LIMIT 5;

SELECT '' AS '';
SELECT '--- Collation of sessions.warmup_prompt column ---' AS '';
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sessions'
  AND COLUMN_NAME IN ('warmup_prompt','explore_content','challenge_prompt','reflect_prompt','title');

SELECT '' AS '';
SELECT '--- Connection charset when .sql runs ---' AS '';
SHOW VARIABLES LIKE 'character_set%';