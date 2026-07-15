-- FreqLearn — properly backfill sessions.language (v4, HEX-byte, character-set-safe)
-- Run on server:
--   mysql freqlearn < scripts/redetect_session_languages_v4.sql
--
-- Run AFTER diag_hex_session_languages_v2.sql confirms the hex patterns match.
--
-- Why v4 and not v3:
--   - The diag showed that filtering by `REGEXP '[^\\x00-\\x7F]'` was unreliable
--     on this MariaDB (utf8mb3 connection, utf8mb4 columns).
--   - Filtering by `LENGTH(col) > CHAR_LENGTH(col)` is collation-independent
--     and always finds multi-byte content correctly.
--   - HEX(col) for matching byte ranges is also collation-independent.
--
-- Strategy:
--   1. Filter rows that actually have multi-byte content (not pure ASCII)
--   2. Match UTF-8 byte ranges via HEX() for Cyrillic / Arabic / CJK
--   3. Match literal UTF-8 sequences for Vietnamese diacritics
--   4. Tag anything left as 'und' (undetermined) for manual review

-- Set the connection charset so we're consistent end-to-end.
-- (This is a no-op for the column data, but it makes HEX() output predictable.)
SET NAMES utf8mb4;

-- ============================================================
-- 1. Russian / Cyrillic — UTF-8 bytes D0/D1 80-BF (U+0400-U+04FF)
-- ============================================================
UPDATE sessions
SET language = 'ru'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP 'D[01][89ABCDEF][0-9A-F]'
     OR HEX(explore_content)  REGEXP 'D[01][89ABCDEF][0-9A-F]'
     OR HEX(challenge_prompt) REGEXP 'D[01][89ABCDEF][0-9A-F]'
     OR HEX(reflect_prompt)   REGEXP 'D[01][89ABCDEF][0-9A-F]'
  );

-- ============================================================
-- 2. Vietnamese diacritics — specific UTF-8 byte pairs
--    Covers: ă â đ ê ô ơ ư + their uppercase variants
--    UTF-8: 0xC4 0x83=ă, 0xC4 0x91=đ, 0xC6 0xA1=ạ, 0xC6 0xB0=ư,
--           0xC3 0xA2=â, 0xC3 0xAA=ê, 0xC3 0xB4=ô, 0xC3 0x9A=ơ,
--           and the tilde/dot-below sequences
-- ============================================================
UPDATE sessions
SET language = 'vi'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP '(C3A2|C3AA|C3B4|C3BA|C483|C491|C49B|C49D|C6A1|C6A3|C6A5|C6A7|C6A9|C6AD|C6AF|C6B1|C6B3|C6B5|C6B7|C6B9|C6BB|C6BD|C6BF|C482|C490|C49A|C49C|C6A0|C6A2|C6A4|C6A6|C6A8|C6AC|C6AE|C6B0|C6B2|C6B4|C6B6|C6B8|C6BA|C6BC|C6BE)'
     OR HEX(explore_content)  REGEXP '(C3A2|C3AA|C3B4|C3BA|C483|C491|C49B|C49D|C6A1|C6A3|C6A5|C6A7|C6A9|C6AD|C6AF|C6B1|C6B3|C6B5|C6B7|C6B9|C6BB|C6BD|C6BF|C482|C490|C49A|C49C|C6A0|C6A2|C6A4|C6A6|C6A8|C6AC|C6AE|C6B0|C6B2|C6B4|C6B6|C6B8|C6BA|C6BC|C6BE)'
     OR HEX(challenge_prompt) REGEXP '(C3A2|C3AA|C3B4|C3BA|C483|C491|C49B|C49D|C6A1|C6A3|C6A5|C6A7|C6A9|C6AD|C6AF|C6B1|C6B3|C6B5|C6B7|C6B9|C6BB|C6BD|C6BF|C482|C490|C49A|C49C|C6A0|C6A2|C6A4|C6A6|C6A8|C6AC|C6AE|C6B0|C6B2|C6B4|C6B6|C6B8|C6BA|C6BC|C6BE)'
     OR HEX(reflect_prompt)   REGEXP '(C3A2|C3AA|C3B4|C3BA|C483|C491|C49B|C49D|C6A1|C6A3|C6A5|C6A7|C6A9|C6AD|C6AF|C6B1|C6B3|C6B5|C6B7|C6B9|C6BB|C6BD|C6BF|C482|C490|C49A|C49C|C6A0|C6A2|C6A4|C6A6|C6A8|C6AC|C6AE|C6B0|C6B2|C6B4|C6B6|C6B8|C6BA|C6BC|C6BE)'
  );

-- ============================================================
-- 3. Arabic — D8/D9 80-BF (U+0600-U+06FF)
-- ============================================================
UPDATE sessions
SET language = 'ar'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP 'D[89][89ABCDEF][0-9A-F]'
     OR HEX(explore_content)  REGEXP 'D[89][89ABCDEF][0-9A-F]'
     OR HEX(challenge_prompt) REGEXP 'D[89][89ABCDEF][0-9A-F]'
     OR HEX(reflect_prompt)   REGEXP 'D[89][89ABCDEF][0-9A-F]'
  );

-- ============================================================
-- 4. Chinese / CJK — E4..E9 prefix bytes (U+4E00-U+9FFF block)
--    Any 3-byte UTF-8 starting E4-E9 falls in the CJK Unified Ideographs
--    range or related blocks (Hiragana, Katakana, Hangul).
--    We use a generous pattern; tag as 'zh' (could split zh/ja/ko later).
-- ============================================================
UPDATE sessions
SET language = 'zh'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP 'E[4-9A-BC][0-9A-F][0-9A-F]'
     OR HEX(explore_content)  REGEXP 'E[4-9A-BC][0-9A-F][0-9A-F]'
     OR HEX(challenge_prompt) REGEXP 'E[4-9A-BC][0-9A-F][0-9A-F]'
     OR HEX(reflect_prompt)   REGEXP 'E[4-9A-BC][0-9A-F][0-9A-F]'
  );

-- ============================================================
-- 5. French — literal accented chars (worked in v1)
-- ============================================================
UPDATE sessions
SET language = 'fr'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
     OR explore_content   REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
     OR challenge_prompt  REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
     OR reflect_prompt    REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
  );

-- ============================================================
-- 6. Spanish
-- ============================================================
UPDATE sessions
SET language = 'es'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[ñ¿¡]'
     OR explore_content   REGEXP '[ñ¿¡]'
     OR challenge_prompt  REGEXP '[ñ¿¡]'
     OR reflect_prompt    REGEXP '[ñ¿¡]'
  );

-- ============================================================
-- 7. German
-- ============================================================
UPDATE sessions
SET language = 'de'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[äöüßÄÖÜ]'
     OR explore_content   REGEXP '[äöüßÄÖÜ]'
     OR challenge_prompt  REGEXP '[äöüßÄÖÜ]'
     OR reflect_prompt    REGEXP '[äöüßÄÖÜ]'
  );

-- ============================================================
-- 8. Tag any remaining 'en' rows with multi-byte content as 'und'
--    so we don't silently lose them
-- ============================================================
UPDATE sessions
SET language = 'und'
WHERE language = 'en'
  AND (
        LENGTH(warmup_prompt)     > CHAR_LENGTH(warmup_prompt)
     OR LENGTH(explore_content)   > CHAR_LENGTH(explore_content)
     OR LENGTH(challenge_prompt)  > CHAR_LENGTH(challenge_prompt)
     OR LENGTH(reflect_prompt)    > CHAR_LENGTH(reflect_prompt)
  );

-- ============================================================
-- 9. Final distribution
-- ============================================================
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;