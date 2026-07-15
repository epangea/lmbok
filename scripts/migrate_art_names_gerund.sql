-- ============================================================
-- FreqLearn — migrate_art_names_gerund.sql
-- Renames all 15 arts to gerund form as per "To Be Human"
-- by Charbel Haddad. Slugs unchanged (referenced by sessions).
-- Run: mysql -u freqlearn -p freqlearn < migrate_art_names_gerund.sql
-- ============================================================

-- Arts of Being
UPDATE arts SET name = 'Moving'       WHERE slug = 'move';
UPDATE arts SET name = 'Eating'       WHERE slug = 'eat';
UPDATE arts SET name = 'Feeling'      WHERE slug = 'feel';
UPDATE arts SET name = 'Noticing'     WHERE slug = 'notice';
UPDATE arts SET name = 'Expressing'   WHERE slug = 'express';

-- Arts of Becoming
UPDATE arts SET name = 'Living'       WHERE slug = 'live';
UPDATE arts SET name = 'Listening'    WHERE slug = 'listen';
UPDATE arts SET name = 'Giving'       WHERE slug = 'give';
UPDATE arts SET name = 'Receiving'    WHERE slug = 'receive';
UPDATE arts SET name = 'Collaborating' WHERE slug = 'collaborate';

-- Arts of Connecting
UPDATE arts SET name = 'Understanding' WHERE slug = 'understand';
UPDATE arts SET name = 'Respecting'   WHERE slug = 'respect';
UPDATE arts SET name = 'Building'     WHERE slug = 'build';
UPDATE arts SET name = 'Growing'      WHERE slug = 'grow';
UPDATE arts SET name = 'Consuming'    WHERE slug = 'consume';

-- Verify
SELECT slug, name FROM arts ORDER BY sort_order;
