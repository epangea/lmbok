-- FreqLearn — properly reclassify the 157 'vi' rows
-- Run AFTER diag_vietnamese_overcount.sql confirms the overcount:
--   mysql freqlearn < scripts/fix_vietnamese_overcount.sql
--
-- Logic:
--   - Vietnamese-specific markers: bytes C6 B0 (ư), C6 A1 (ơ), C4 91 (đ), C4 83 (ă)
--   - Spanish-specific: [ñ¿¡] in warmup/explore
--   - Portuguese-specific: [ãõÃÕ] in warmup/explore
--   - Rows with Vietnamese markers stay 'vi'
--   - Rows with Spanish markers (and no Vietnamese markers) → 'es'
--   - Rows with Portuguese markers (and no Vietnamese markers) → 'pt'
--   - Rows with none of the above → probably misclassified; tag 'und' for review

SET NAMES utf8mb4;

-- Step 1: Re-tag vi → es (Spanish disambiguator)
UPDATE sessions
SET language = 'es'
WHERE language = 'vi'
  AND NOT (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(challenge_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(reflect_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
  )
  AND (
        warmup_prompt REGEXP '[ñ¿¡]'
     OR explore_content REGEXP '[ñ¿¡]'
     OR challenge_prompt REGEXP '[ñ¿¡]'
     OR reflect_prompt REGEXP '[ñ¿¡]'
  );

-- Step 2: Re-tag vi → pt (Portuguese disambiguator)
UPDATE sessions
SET language = 'pt'
WHERE language = 'vi'
  AND NOT (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(challenge_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(reflect_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
  )
  AND (
        warmup_prompt REGEXP '[ãõÃÕ]'
     OR explore_content REGEXP '[ãõÃÕ]'
     OR challenge_prompt REGEXP '[ãõÃÕ]'
     OR reflect_prompt REGEXP '[ãõÃÕ]'
  );

-- Step 3: Re-tag remaining vi → 'und' if no Vietnamese markers at all
-- (these are likely English-with-accents or another language entirely)
UPDATE sessions
SET language = 'und'
WHERE language = 'vi'
  AND NOT (
        HEX(warmup_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(explore_content) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(challenge_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
     OR HEX(reflect_prompt) REGEXP 'C6B0|C6A1|C491|C483|C482|C490|C49B|C49D|C6A0|C6AF'
  );

-- Step 4: Final distribution
SELECT '=== Final distribution after Vietnamese reclassification ===' AS '';
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS session_count
FROM sessions
GROUP BY language
ORDER BY session_count DESC;