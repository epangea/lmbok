-- 2026-06-28-session-ai-metadata.sql
-- Adds two AI-call metadata columns to the sessions table, and one
-- new platform_settings row for the in-memory circuit breaker toggle.
--
-- Storage philosophy: we do not log token counts, costs, or billing data.
-- We track the minimum needed for learning-research audit and for the
-- admin to see which AI provider/model answered which session.
--
-- This migration is idempotent: it can be re-run safely. It uses
-- IF NOT EXISTS-equivalent patterns via information_schema checks
-- where the DB engine supports them, and tolerates "duplicate column"
-- errors via the @silent flag in the app runner.
--
-- Run on server:
--   mysql freqlearn < scripts/2026-06-28-session-ai-metadata.sql
--
-- Rollback (if ever needed):
--   ALTER TABLE sessions DROP COLUMN model;
--   ALTER TABLE sessions DROP COLUMN latency_ms;
--   ALTER TABLE sessions DROP COLUMN assess_selected_index;
--   DELETE FROM platform_settings WHERE key_name = 'ai_circuit_breaker_enabled';
--   DELETE FROM platform_settings WHERE key_name = 'ai_include_prior_context';

-- ── sessions.model: which model answered this generation ──
-- Example values: 'llama-3.3-70b-versatile', 'llama-3.1-8b-instant',
-- 'library' (when served from DB cache after AI failure), 'ollama:llama3.1:8b'.
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'sessions'
      AND COLUMN_NAME  = 'model'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE sessions ADD COLUMN model VARCHAR(80) DEFAULT NULL AFTER engine_reasoning',
    'SELECT "sessions.model already exists, skipping" AS info'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ── sessions.latency_ms: wall-clock time of the AI call in ms ──
-- 0 for library-cached sessions. NULL for legacy rows predating this column.
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'sessions'
      AND COLUMN_NAME  = 'latency_ms'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE sessions ADD COLUMN latency_ms INT DEFAULT NULL AFTER model',
    'SELECT "sessions.latency_ms already exists, skipping" AS info'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ── sessions.assess_selected_index: which option the learner picked ──
-- 0-based index into assess_question.options. NULL if the learner didn't
-- reach the assess phase, or for legacy rows predating this column.
-- This lets the AI prompt see "learner picked A, correct was C" so it
-- can address the misconception that led to the wrong choice.
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'sessions'
      AND COLUMN_NAME  = 'assess_selected_index'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE sessions ADD COLUMN assess_selected_index TINYINT DEFAULT NULL AFTER assess_score',
    'SELECT "sessions.assess_selected_index already exists, skipping" AS info'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ── platform_settings: AI circuit breaker toggle ──
-- When 'true' (default): after 3 consecutive AI failures for a learner,
-- switch to library-first mode for 10 minutes, no AI attempt during window.
-- When 'false': on first AI failure, fall through to library immediately,
-- no threshold, no 10-minute window. Library is always tried as the
-- final fallback before 503 regardless of this setting.
INSERT INTO platform_settings (key_name, value, description, category) VALUES
    ('ai_circuit_breaker_enabled', 'true',
     'When enabled, in-memory circuit breaker gates AI calls after 3 consecutive failures (switches to library for 10 min). When disabled, falls to library immediately on any failure.',
     'ai'),
    ('ai_include_prior_context', 'true',
     'When enabled, the AI prompt includes a LEARNER CONTINUITY block listing the learner''s last 3 sessions for this art, so each generation builds on prior work rather than repeating themes.',
     'ai'),
    ('ai_library_recall_limit', '200',
     'How many of the learner''s recent sessions to scan when deduplicating library fallbacks. Higher = better dedup, slightly slower. 200 covers the vast majority of realistic use.',
     'ai')
ON DUPLICATE KEY UPDATE updated_at = NOW();

-- ── Verify ──
SELECT '=== Migration complete ===' AS '';
SELECT 'sessions.model'              AS column_name,
       COUNT(*)                     AS total_sessions,
       SUM(model IS NOT NULL)       AS rows_with_model,
       SUM(latency_ms IS NOT NULL)  AS rows_with_latency
FROM sessions
UNION ALL
SELECT 'platform_settings (new AI keys)' AS column_name,
       COUNT(*)                          AS total_sessions,
       SUM(category = 'ai')              AS rows_with_model,
       NULL                              AS rows_with_latency
FROM platform_settings
WHERE key_name IN ('ai_circuit_breaker_enabled', 'ai_include_prior_context', 'ai_library_recall_limit');
