-- FreqLearn — properly backfill sessions.language (v3, HEX-byte based)
-- Run on server:
--   mysql freqlearn < scripts/redetect_session_languages_v3.sql
--
-- Why v3: MariaDB's REGEXP character classes ([А-Яа-я]) DO NOT reliably
-- match Cyrillic when the column collation differs from the connection
-- collation. v3 uses HEX() on the column and matches UTF-8 byte patterns,
-- which is collation-independent and works on every MariaDB version.
--
-- UTF-8 byte ranges we use:
--   Cyrillic (U+0400-U+04FF)  → bytes 0xD0 0x80 .. 0xD1 0xBF
--   Vietnamese diacritics (U+0080-U+04FF) → bytes 0xC3 0xA2, 0xC3 0xAA,
--                                          0xC3 0xB4, 0xC4 0x83, 0xC4 0x91,
--                                          0xC6 0xA1, 0xC6 0xB0
--   CJK Unified (U+4E00-U+9FFF) → bytes 0xE4 0xB8 0x80 .. 0xE9 0xBF 0xBF
--     (prefix bytes 0xE4..0xE9 followed by 0xB8..0xBF or 0x80..0xBF)
--   Arabic   (U+0600-U+06FF) → bytes 0xD8 0x80 .. 0xDB 0xBF
--   Greek    (U+0370-U+03FF) → bytes 0xCD 0xB0 .. 0xCF 0xBF
--
-- Safe to re-run: each UPDATE only touches rows still tagged 'en'.

-- ============================================================
-- 1. Russian / Cyrillic — D0/D1 followed by 80-BF
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
-- 2. Vietnamese diacritics — specific 2-byte sequences
--    These 7 patterns cover ă â đ ê ô ơ ư + uppercase variants.
--    We list them as exact byte pairs in the HEX output.
-- ============================================================
UPDATE sessions
SET language = 'vi'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP '(C3A2|C3AA|C3B4|C483|C491|C6A1|C6B0|C382|C38A|C394|C394|C398|C39A|C39E|C3A6|C3B4|C482|C490|C4A0|C4AE|C4B0|C6A0|C6AF|C682|C68A|C692|C69A|C6A1|C6B0|C382|C38A|C394|C398|C39A|C39E|C3A6)'
     OR HEX(explore_content)  REGEXP '(C3A2|C3AA|C3B4|C483|C491|C6A1|C6B0|C382|C38A|C394|C394|C398|C39A|C39E|C3A6|C3B4|C482|C490|C4A0|C4AE|C4B0|C6A0|C6AF|C682|C68A|C692|C69A|C6A1|C6B0|C382|C38A|C394|C398|C39A|C39E|C3A6)'
     OR HEX(challenge_prompt) REGEXP '(C3A2|C3AA|C3B4|C483|C491|C6A1|C6B0|C382|C38A|C394|C394|C398|C39A|C39E|C3A6|C3B4|C482|C490|C4A0|C4AE|C4B0|C6A0|C6AF|C682|C68A|C692|C69A|C6A1|C6B0|C382|C38A|C394|C398|C39A|C39E|C3A6)'
     OR HEX(reflect_prompt)   REGEXP '(C3A2|C3AA|C3B4|C483|C491|C6A1|C6B0|C382|C38A|C394|C394|C398|C39A|C39E|C3A6|C3B4|C482|C490|C4A0|C4AE|C4B0|C6A0|C6AF|C682|C68A|C692|C69A|C6A1|C6B0|C382|C38A|C394|C398|C39A|C39E|C3A6)'
  );

-- ============================================================
-- 3. Arabic — D8/D9 followed by 80-BF (U+0600-U+06FF)
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
-- 4. Chinese / CJK — E4..E9 prefix bytes (U+4000-U+9FFF)
--    Pattern: E[4-9B] followed by [8B][0-9A-F] or [0-9A-F]{2}
--    Simplified: any 3-byte UTF-8 sequence starting E4-E9
-- ============================================================
UPDATE sessions
SET language = 'zh'
WHERE language = 'en'
  AND (
        HEX(warmup_prompt)    REGEXP 'E[4-9B][0-9A-F][0-9A-F]'
     OR HEX(explore_content)  REGEXP 'E[4-9B][0-9A-F][0-9A-F]'
     OR HEX(challenge_prompt) REGEXP 'E[4-9B][0-9A-F][0-9A-F]'
     OR HEX(reflect_prompt)   REGEXP 'E[4-9B][0-9A-F][0-9A-F]'
  );

-- ============================================================
-- 5. French (literal accented chars — same as v1, still works)
--    Already caught 6 rows in v1; gate on language='en' so we don't
--    touch anything already correctly tagged.
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
-- 8. Anything still tagged 'en' but with non-ASCII content gets
--    tagged 'und' (undetermined) so we can find these and triage
--    manually instead of silently losing them.
-- ============================================================
UPDATE sessions
SET language = 'und'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[^\\x00-\\x7F]'
     OR explore_content   REGEXP '[^\\x00-\\x7F]'
     OR challenge_prompt  REGEXP '[^\\x00-\\x7F]'
     OR reflect_prompt    REGEXP '[^\\x00-\\x7F]'
  );

-- ============================================================
-- 9. Report — final distribution
-- ============================================================
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;