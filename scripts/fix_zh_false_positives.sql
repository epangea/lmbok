-- FreqLearn — rollback the broken v4 zh tag, then fix CJK regex
-- Run on server:
--   mysql freqlearn < scripts/fix_zh_false_positives.sql
--
-- What v4 did wrong:
--   The CJK regex was 'E[4-9A-BC][0-9A-F][0-9A-F]'
--   which matches any 3-byte UTF-8 starting with E2..EC.
--   E2 = U+2010..U+2FFF = General Punctuation (em-dash, en-dash,
--   smart quotes, ellipsis, etc.) — these are common in well-typeset
--   English, NOT Chinese characters.
--   Result: 1,618 English rows got tagged 'zh' because they contain
--   em-dashes (—), en-dashes (–), curly quotes ("..."), etc.
--
-- Fix:
--   1. Restore those rows to 'en' (where the rest of their content is pure ASCII)
--   2. Tighten the CJK regex to leading bytes E4-E9 only (actual CJK blocks)
--   3. Re-run only the CJK UPDATE with the corrected regex
--   4. Re-run the 'und' tagger with a smarter filter that doesn't double-tag

-- Step 1: Reset rows that v4 wrongly tagged 'zh' back to 'en'
--         (only those whose remaining content is pure ASCII English)
UPDATE sessions
SET language = 'en'
WHERE language = 'zh'
  AND LENGTH(warmup_prompt)     = CHAR_LENGTH(warmup_prompt)
  AND LENGTH(explore_content)   = CHAR_LENGTH(explore_content)
  AND LENGTH(challenge_prompt)  = CHAR_LENGTH(challenge_prompt)
  AND LENGTH(reflect_prompt)    = CHAR_LENGTH(reflect_prompt);

-- Step 2: For rows still tagged 'zh' but NOT pure-ASCII, find out what they actually are
--         (these are real CJK — should stay 'zh' once we confirm)
SELECT 'Rows still tagged zh after reset:' AS '';
SELECT id, LEFT(warmup_prompt, 40) AS preview, HEX(LEFT(warmup_prompt, 20)) AS hex
FROM sessions WHERE language = 'zh' LIMIT 5;

-- Step 3: Re-run CJK detection with the FIXED regex
--         CJK Unified Ideographs: U+4E00..U+9FFF
--         UTF-8 leading bytes: E4..E9 (then 80..BF for second byte)
--         The previous regex was E[4-9A-BC] — too broad (caught E2 punctuation)
UPDATE sessions
SET language = 'zh'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP 'E[4-9][89ABCDEF][0-9A-F]'
     OR HEX(explore_content)  REGEXP 'E[4-9][89ABCDEF][0-9A-F]'
     OR HEX(challenge_prompt) REGEXP 'E[4-9][89ABCDEF][0-9A-F]'
     OR HEX(reflect_prompt)   REGEXP 'E[4-9][89ABCDEF][0-9A-F]'
  );

-- Step 4: Re-tag genuinely multi-byte non-CJK content as 'und'
--         (English with em-dashes, smart quotes, etc.)
--         Only touch rows still 'en' that have multi-byte content but
--         don't match any language regex
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
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;