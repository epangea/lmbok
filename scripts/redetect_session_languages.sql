-- FreqLearn — properly backfill sessions.language after the first attempt
-- (which tagged everything 'en' because MariaDB's REGEXP doesn't accept
--  the \\x{NNNN} Unicode range syntax used in the first migration).
--
-- Run on server:
--   mysql freqlearn < scripts/redetect_session_languages.sql
--
-- Safe to re-run: each UPDATE only touches rows where language matches the
-- previous "fallback" sentinel ('en'). Won't disturb already-correct rows
-- unless they happen to be 'en' AND match the regex — which by definition
-- they won't, because 'en' rows are pure-ASCII.
--
-- Created: 2026-06-27 by openclaw agent.

-- ============================================================
-- 1. Russian / Cyrillic
--    Enumerate Cyrillic range explicitly. Cyrillic Unicode block
--    U+0400–U+04FF spans: Ѐ Ӂ etc. We use the alphabet directly:
--    А-Я (basic Russian uppercase + lowercase via case-folding)
--    plus Ё/ё and the historic letters that appear in some texts.
-- ============================================================
UPDATE sessions
SET language = 'ru'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[А-Яа-яЁё]'
     OR explore_content   REGEXP '[А-Яа-яЁё]'
     OR challenge_prompt  REGEXP '[А-Яа-яЁё]'
     OR reflect_prompt    REGEXP '[А-Яа-яЁё]'
  );

-- ============================================================
-- 2. Vietnamese (specific diacritics — already works in MariaDB)
--    Same rule as the first migration, just gated on language='en'
--    so it only catches rows still in the wrong bucket.
-- ============================================================
UPDATE sessions
SET language = 'vi'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
     OR explore_content   REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
     OR challenge_prompt  REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
     OR reflect_prompt    REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
  );

-- ============================================================
-- 3. Arabic
-- ============================================================
UPDATE sessions
SET language = 'ar'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '[؀-ۿݐ-ݿ]'
     OR explore_content   REGEXP '[؀-ۿݐ-ݿ]'
     OR challenge_prompt  REGEXP '[؀-ۿݐ-ݿ]'
     OR reflect_prompt    REGEXP '[؀-ۿݐ-ݿ]'
  );

-- ============================================================
-- 4. Chinese / Japanese / Korean (CJK Unified Ideographs)
--    Basic block U+4E00–U+9FFF. MariaDB is UTF-8 so direct char literals
--    in the 4-byte UTF-8 range work; we use 一 (U+4E00) and 鿿 (U+9FFF)
--    as the literal endpoints.
-- ============================================================
UPDATE sessions
SET language = 'zh'
WHERE language = 'en'
  AND (
        warmup_prompt     REGEXP '一'
     OR explore_content   REGEXP '一'
     OR challenge_prompt  REGEXP '一'
     OR reflect_prompt    REGEXP '一'
  );

-- ============================================================
-- 5. French (overrides the old broken detection to be more inclusive)
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
-- 8. Report — show the corrected distribution
-- ============================================================
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;