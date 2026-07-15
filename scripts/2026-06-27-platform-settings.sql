-- FreqLearn — Add platform_settings table for Admin Settings persistence
-- Run on server:
--   mysql freqlearn < scripts/2026-06-27-platform-settings.sql
--
-- Schema:
--   id INT PK AI
--   key_name VARCHAR(80) UNIQUE NOT NULL  -- the setting name (e.g., "platform_name", "default_language")
--   value TEXT                              -- the setting value (stored as text; cast as needed)
--   description VARCHAR(255)               -- human-readable description (shown in admin UI tooltip)
--   category ENUM('general','ai','scavenger','privacy')  -- groups settings in admin UI
--   updated_at DATETIME                     -- last updated
--   updated_by VARCHAR(80)                  -- admin user who updated (for audit; default 'admin')

CREATE TABLE IF NOT EXISTS platform_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_name VARCHAR(80) NOT NULL UNIQUE,
    value TEXT,
    description VARCHAR(255),
    category ENUM('general', 'ai', 'scavenger', 'privacy') DEFAULT 'general',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by VARCHAR(80) DEFAULT 'admin'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed initial values from current defaults
INSERT INTO platform_settings (key_name, value, description, category) VALUES
    ('platform_name', 'Surfing the Frequencies', 'Public-facing platform name shown in titles, headers', 'general'),
    ('admin_email', 'charbel@onehouse.top', 'Admin contact email', 'general'),
    ('default_language', 'en', 'Default language for new users (en/fr/es/vi/zh/ar/de/ru)', 'general'),
    ('ai_provider', 'groq', 'Primary AI provider: groq | anthropic | ollama | library', 'ai'),
    ('ai_monthly_budget', '10', 'Monthly API budget in USD (0 = unlimited)', 'ai'),
    ('min_library_sessions', '3', 'Min stored sessions before making new API call', 'ai'),
    ('scavenger_sender_name', '', 'Outreach sender name (used in emails)', 'scavenger'),
    ('scavenger_sender_email', '', 'Outreach sender email (used as From: address)', 'scavenger'),
    ('scavenger_auto_send', 'false', 'Auto-send approved emails (requires email provider setup)', 'scavenger'),
    ('require_email_verification', 'true', 'Require email verification on registration', 'privacy'),
    ('allow_learner_data_deletion', 'true', 'Allow learners to delete their own data', 'privacy'),
    ('show_learner_names_to_orgs', 'false', 'Show learner names to orgs before learner consent', 'privacy'),
    ('allow_anonymous_leckos', 'true', 'Allow anonymous LECKO contributions', 'privacy')
ON DUPLICATE KEY UPDATE updated_at = NOW();

SELECT '=== platform_settings table created and seeded ===' AS '';
SELECT category, COUNT(*) AS settings_count FROM platform_settings GROUP BY category;
SELECT 'Total settings:' AS info, COUNT(*) AS n FROM platform_settings;