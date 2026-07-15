-- FreqLearn — fix zh false positives v5 (anchored to actual CJK byte patterns)
-- Run on server:
--   mysql freqlearn < scripts/fix_zh_false_positives_v5.sql
--
-- Why v4 and the previous "fix" still over-tagged:
--   My regex was 'E[4-9][89ABCDEF][0-9A-F]' which matches any 3-byte UTF-8
--   starting with E4-E9. But that catches:
--     - Em-dashes E2 80 93 (E2 is in [4-9A-BC] but ALSO em-dashes when
--       the row has another E[4-9] byte elsewhere)
--     - Smart quotes E2 80 9C/9D
--     - Math symbols E2 88 92 (minus sign)
--     - General Punctuation block E2 80 xx
--   Real CJK characters have a specific pattern: 3 bytes starting E4-E9
--   where byte 2 is B8-BF (since CJK code points are U+4000+, which means
--   the second UTF-8 byte is always >= 0xB8).
--
-- Fix: require byte 2 to be in B8-BF range (i.e., the code point is >= U+4000).
--   Pattern: E[4-9] B[89ABCDEF] [0-9A-F]
--
-- Step 1: Rollback the broken zh tags from v4/fix_v1
--         (reset rows where warmup_prompt starts with ASCII to 'en')
UPDATE sessions
SET language = 'en'
WHERE language = 'zh'
  AND warmup_prompt REGEXP '^[A-Za-z0-9 ,.;:!?''"-]'
  AND LENGTH(warmup_prompt) > CHAR_LENGTH(warmup_prompt);

-- Step 2: Show what's STILL tagged zh (those should be real CJK now)
SELECT '=== Rows still zh after rollback (should be empty or near-empty) ===' AS '';
SELECT id, LEFT(warmup_prompt, 60) AS preview, HEX(LEFT(warmup_prompt, 25)) AS hex
FROM sessions WHERE language = 'zh' LIMIT 10;

-- Step 3: Re-run CJK detection with the TIGHT regex
--         Real CJK 3-byte UTF-8: E[4-9] B[89ABCDEF] [0-9A-F]
UPDATE sessions
SET language = 'zh'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP 'E[4-9]B[89ABCDEF][0-9A-F]'
     OR HEX(explore_content)  REGEXP 'E[4-9]B[89ABCDEF][0-9A-F]'
     OR HEX(challenge_prompt) REGEXP 'E[4-9]B[89ABCDEF][0-9A-F]'
     OR HEX(reflect_prompt)   REGEXP 'E[4-9]B[89ABCDEF][0-9A-F]'
  );

-- Step 4: Re-tag any still-'en' multi-byte content as 'und'
--         (em-dashes, smart quotes, accented proper nouns — English typography)
UPDATE sessions
SET language = 'und'
WHERE language = 'en'
  AND (
        LENGTH(warmup_prompt)     > CHAR_LENGTH(warmup_prompt)
     OR LENGTH(explore_content)   > CHAR_LENGTH(explore_content)
     OR LENGTH(challenge_prompt)  > CHAR_LENGTH(challenge_prompt)
     OR LENGTH(reflect_prompt)    > CHAR_LENGTH(reflect_prompt)
  );

-- Step 5: Final report
SELECT '=== Final distribution ===' AS '';
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;