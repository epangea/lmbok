-- ============================================================
-- FreqLearn — fix_session_art_names.sql
-- Replaces infinitive art name references baked into pre-seeded
-- session content with the correct gerund form from the paper.
-- Safe to run multiple times (NOT LIKE guard prevents double-replace).
-- Run: mysql -u freqlearn -p freqlearn < fix_session_art_names.sql
-- ============================================================

-- ── assess_question JSON field ────────────────────────────────
-- MariaDB JSON_SET + REPLACE approach for each art name.

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Understand', 'art of Understanding'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Understand%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Understanding%';

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Build', 'art of Building'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Build%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Building%';

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Grow', 'art of Growing'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Grow%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Growing%';

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Consume', 'art of Consuming'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Consume%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Consuming%';

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Respect', 'art of Respecting'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Respect%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Respecting%';

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Receive', 'art of Receiving'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Receive%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Receiving%';

UPDATE sessions SET assess_question = JSON_SET(assess_question, '$.question',
  REPLACE(JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')), 'art of Collaborate', 'art of Collaborating'))
WHERE JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Collaborate%'
  AND JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) NOT LIKE '%art of Collaborating%';

-- ── Plain text fields ─────────────────────────────────────────
UPDATE sessions SET explore_content  = REPLACE(explore_content,  'art of Understand',  'art of Understanding')  WHERE explore_content  LIKE '%art of Understand%'  AND explore_content  NOT LIKE '%art of Understanding%';
UPDATE sessions SET warmup_prompt    = REPLACE(warmup_prompt,    'art of Understand',  'art of Understanding')  WHERE warmup_prompt    LIKE '%art of Understand%'  AND warmup_prompt    NOT LIKE '%art of Understanding%';
UPDATE sessions SET challenge_prompt = REPLACE(challenge_prompt, 'art of Understand',  'art of Understanding')  WHERE challenge_prompt LIKE '%art of Understand%'  AND challenge_prompt NOT LIKE '%art of Understanding%';
UPDATE sessions SET reflect_prompt   = REPLACE(reflect_prompt,   'art of Understand',  'art of Understanding')  WHERE reflect_prompt   LIKE '%art of Understand%'  AND reflect_prompt   NOT LIKE '%art of Understanding%';
UPDATE sessions SET title            = REPLACE(title,            'Art of Understand',  'Art of Understanding')  WHERE title            LIKE '%Art of Understand%'   AND title            NOT LIKE '%Art of Understanding%';

UPDATE sessions SET explore_content  = REPLACE(explore_content,  'art of Build',  'art of Building')  WHERE explore_content  LIKE '%art of Build%'  AND explore_content  NOT LIKE '%art of Building%';
UPDATE sessions SET explore_content  = REPLACE(explore_content,  'art of Grow',   'art of Growing')   WHERE explore_content  LIKE '%art of Grow%'   AND explore_content  NOT LIKE '%art of Growing%';
UPDATE sessions SET explore_content  = REPLACE(explore_content,  'art of Consume','art of Consuming') WHERE explore_content  LIKE '%art of Consume%' AND explore_content NOT LIKE '%art of Consuming%';
UPDATE sessions SET explore_content  = REPLACE(explore_content,  'art of Respect','art of Respecting')WHERE explore_content  LIKE '%art of Respect%' AND explore_content NOT LIKE '%art of Respecting%';

-- ── Verify ────────────────────────────────────────────────────
SELECT COUNT(*) AS remaining_stale
FROM sessions
WHERE warmup_prompt    LIKE '%art of Understand%'
   OR explore_content  LIKE '%art of Understand%'
   OR JSON_UNQUOTE(JSON_EXTRACT(assess_question, '$.question')) LIKE '%art of Understand%';
