-- Diagnostic: see what non-ASCII content actually exists in sessions
-- Run on server:  mysql freqlearn < scripts/diag_session_languages.sql

SELECT 'sample warmup_prompts (first 200 chars of any with non-ASCII):' AS '';
SELECT id, LEFT(warmup_prompt, 200) AS warmup_preview
FROM sessions
WHERE warmup_prompt REGEXP '[^[:ascii:]]'
LIMIT 5;

SELECT '' AS '';
SELECT 'language distribution:' AS '';
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS n
FROM sessions
GROUP BY language
ORDER BY n DESC;

SELECT '' AS '';
SELECT 'any sessions where warmup contains Cyrillic chars (hex-encoded to make sure):' AS '';
SELECT id, HEX(LEFT(warmup_prompt, 50)) AS hex_preview
FROM sessions
WHERE warmup_prompt REGEXP '[^[:ascii:]]'
LIMIT 3;