-- FreqLearn — add language column to sessions + heuristic backfill
-- Run:  mysql freqlearn < /var/www/freqlearn/scripts/migrate_session_language.sql
-- Safe to re-run: idempotent (guarded by INFORMATION_SCHEMA checks).
-- Created: 2026-06-27 by openclaw agent.

-- ============================================================
-- 1. Add the column (idempotent)
-- ============================================================
SET @col_exists := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'sessions'
    AND COLUMN_NAME  = 'language'
);

SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE sessions ADD COLUMN language VARCHAR(10) NULL DEFAULT ''en'' AFTER created_at',
  'SELECT ''language column already exists — skipping ALTER'' AS note');

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================
-- 2. Backfill heuristic — order matters (more specific patterns first)
--    Use ICU-style regex via MariaDB (\\xNNNN) which works without
--    any external deps. Each UPDATE only touches rows still NULL/''.
-- ============================================================

-- 2a. Russian / Cyrillic (any Cyrillic character wins first — it's unambiguous)
UPDATE sessions
SET language = 'ru'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[\\x{0400}-\\x{04FF}]'
     OR explore_content   REGEXP '[\\x{0400}-\\x{04FF}]'
     OR challenge_prompt  REGEXP '[\\x{0400}-\\x{04FF}]'
     OR reflect_prompt    REGEXP '[\\x{0400}-\\x{04FF}]'
  );

-- 2b. Vietnamese (specific diacritics)
UPDATE sessions
SET language = 'vi'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
     OR explore_content   REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
     OR challenge_prompt  REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
     OR reflect_prompt    REGEXP '[ăâđêôơưĂÂĐÊÔƠƯ]'
  );

-- 2c. Arabic
UPDATE sessions
SET language = 'ar'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[\\x{0600}-\\x{06FF}]'
     OR explore_content   REGEXP '[\\x{0600}-\\x{06FF}]'
     OR challenge_prompt  REGEXP '[\\x{0600}-\\x{06FF}]'
     OR reflect_prompt    REGEXP '[\\x{0600}-\\x{06FF}]'
  );

-- 2d. Chinese / Japanese / Korean (CJK unified — collapsed to 'zh' for now;
--     if you ever need ja/ko distinction, split by Hiragana/Katakana ranges)
UPDATE sessions
SET language = 'zh'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[\\x{4E00}-\\x{9FFF}]'
     OR explore_content   REGEXP '[\\x{4E00}-\\x{9FFF}]'
     OR challenge_prompt  REGEXP '[\\x{4E00}-\\x{9FFF}]'
     OR reflect_prompt    REGEXP '[\\x{4E00}-\\x{9FFF}]'
  );

-- 2e. Spanish (ñ, ¿, ¡ are the most diagnostic)
UPDATE sessions
SET language = 'es'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[ñ¿¡]'
     OR explore_content   REGEXP '[ñ¿¡]'
     OR challenge_prompt  REGEXP '[ñ¿¡]'
     OR reflect_prompt    REGEXP '[ñ¿¡]'
  );

-- 2f. French (à, â, ç, é, è, ê, ë, î, ï, ô, ù, û, ü, œ)
UPDATE sessions
SET language = 'fr'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
     OR explore_content   REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
     OR challenge_prompt  REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
     OR reflect_prompt    REGEXP '[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]'
  );

-- 2g. German (ä, ö, ü, ß)
UPDATE sessions
SET language = 'de'
WHERE (language IS NULL OR language = '')
  AND (
        warmup_prompt     REGEXP '[äöüßÄÖÜ]'
     OR explore_content   REGEXP '[äöüßÄÖÜ]'
     OR challenge_prompt  REGEXP '[äöüßÄÖÜ]'
     OR reflect_prompt    REGEXP '[äöüßÄÖÜ]'
  );

-- 2h. Anything still NULL or empty → 'en' (pure ASCII, or unrecognizable)
UPDATE sessions SET language = 'en' WHERE language IS NULL OR language = '';

-- ============================================================
-- 3. Add an index so admin filtering is fast
-- ============================================================
SET @idx_exists := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'sessions'
    AND INDEX_NAME   = 'idx_sessions_language'
);

SET @ddl := IF(@idx_exists = 0,
  'CREATE INDEX idx_sessions_language ON sessions(language)',
  'SELECT ''idx_sessions_language already exists'' AS note');

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================
-- 4. Report — show the resulting distribution
-- ============================================================
SELECT language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;