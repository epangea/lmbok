-- P26: Server-side dedup for polis_discussions comment upvotes
-- Run: mysql freqlearn < migrate_disc_upvotes.sql
--
-- Types matched to actual DB:
--   learner_id  INT UNSIGNED  — matches learners.id (int(10) unsigned)
--   comment_id  INT           — matches polis_discussions.id (int(11))

CREATE TABLE IF NOT EXISTS polis_discussion_upvotes (
  learner_id  INT UNSIGNED NOT NULL,
  comment_id  INT          NOT NULL,
  created_at  DATETIME DEFAULT current_timestamp(),
  PRIMARY KEY (learner_id, comment_id),
  FOREIGN KEY (learner_id) REFERENCES learners(id)          ON DELETE CASCADE,
  FOREIGN KEY (comment_id) REFERENCES polis_discussions(id) ON DELETE CASCADE
);
