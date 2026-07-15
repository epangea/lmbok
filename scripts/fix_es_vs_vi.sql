-- FreqLearn — fix Spanish mis-tagged as Vietnamese + Vietnamese over-matching
-- Run on server AFTER fix_zh_false_positives_v5.sql:
--   mysql freqlearn < scripts/fix_es_vs_vi.sql
--
-- Background:
--   The Vietnamese regex uses Latin-1 supplement chars (ă â đ ê ô ơ ư)
--   which are ALSO common in Spanish/Italian/French/Portuguese/Romanian.
--   Result: Spanish sessions with accents (á é í ó ú ñ) get tagged vi
--   because the regex matched é/í/ó instead of a Vietnamese diacritic.
--
-- Fix strategy:
--   1. Add proper Spanish detection: [áéíóúÁÉÍÓÚüÜ] (Spanish-specific vowels)
--   2. Add proper Portuguese detection: [ãõÃÕ] (Portuguese tildes)
--   3. Re-tag: anything tagged 'vi' but matches Spanish/Portuguese chars
--      AND has no Vietnamese-specific markers should be re-tagged.
--
-- Vietnamese-specific markers (NOT shared with Spanish/Portuguese):
--   ă (U+0103)        → E1 BA 83
--   ơ (U+01A1)        → C6 A1
--   ư (U+01B0)        → C6 B0
--   đ (U+0111)        → C4 91
--   ầ (U+1EA7)        → E1 BA A7
--   ế (U+1EBF)        → E1 BA BF
--   ổ (U+1ED5)        → E1 BB 95
--   ử (U+1EE7)        → E1 BB B7
--   ự (U+1EF1)        → E1 BB B1
--
-- Spanish-specific markers (NOT in Vietnamese):
--   ñ (U+00F1)        → C3 B1
--   ¿ (U+00BF)        → C2 BF
--   ¡ (U+00A1)        → C2 A1
--   á (U+00E1)        → C3 A1 (also in Vietnamese? not a Vietnamese diacritic)
--
-- This is tricky. The clearest distinguishing markers:
--   - Vietnamese has ư/ơ/đ (NOT in Spanish/Portuguese)
--   - Spanish/Portuguese has ñ (NOT in Vietnamese)
--
-- Approach:
--   1. If a row has ư or ơ or đ → definitely Vietnamese (keep vi)
--   2. If a row has ñ or ¿ or ¡ → definitely Spanish (re-tag to es)
--   3. If a row has both → Vietnamese (most likely)
--   4. If a row has only "shared" Latin chars (á é í ó ú etc.) → ambiguous,
--      default to checking the rest of the content for hints

-- Step 1: Find rows currently tagged 'vi' but with Spanish-specific markers
SELECT '=== Rows tagged vi but containing Spanish markers (ñ ¿ ¡) ===' AS '';
SELECT id, LEFT(warmup_prompt, 60) AS preview
FROM sessions
WHERE language = 'vi'
  AND (
        warmup_prompt     REGEXP '[ñ¿¡]'
     OR explore_content   REGEXP '[ñ¿¡]'
     OR challenge_prompt  REGEXP '[ñ¿¡]'
     OR reflect_prompt    REGEXP '[ñ¿¡]'
  )
LIMIT 10;

-- Step 2: Re-tag those to Spanish
UPDATE sessions
SET language = 'es'
WHERE language = 'vi'
  AND (
        warmup_prompt     REGEXP '[ñ¿¡]'
     OR explore_content   REGEXP '[ñ¿¡]'
     OR challenge_prompt  REGEXP '[ñ¿¡]'
     OR reflect_prompt    REGEXP '[ñ¿¡]'
  );

-- Step 3: For rows still tagged 'vi' but NOT containing Vietnamese-specific
--         markers (ư ơ đ), look for Portuguese markers
--         Portuguese-specific: ã (U+00E3), õ (U+00F5)
UPDATE sessions
SET language = 'pt'
WHERE language = 'vi'
  AND NOT (
        warmup_prompt     REGEXP '[ăÂđĐêÊôÔơƠưƯ]'
     OR explore_content   REGEXP '[ăÂđĐêÊôÔơƠưƯ]'
     OR challenge_prompt  REGEXP '[ăÂđĐêÊôÔơƠưƯ]'
     OR reflect_prompt    REGEXP '[ăÂđĐêÊôÔơƠưƯ]'
  )
  AND (
        warmup_prompt     REGEXP '[ãõÃÕ]'
     OR explore_content   REGEXP '[ãõÃÕ]'
     OR challenge_prompt  REGEXP '[ãõÃÕ]'
     OR reflect_prompt    REGEXP '[ãõÃÕ]'
  );

-- Step 4: Final report
SELECT '=== Final distribution after es/pt cleanup ===' AS '';
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;