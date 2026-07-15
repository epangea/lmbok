-- P26: Server-side dedup for polis_discussions comment upvotes
-- Run BEFORE deploying polis9_12.py
--
-- Verify table structure first:
--   DESCRIBE polis_discussions;
-- Expected: id (PK), referendum_id, learner_id, parent_id, body, upvotes, created_at
--
-- Run:
--   mysql -u freqlearn -p freqlearn < migrate_disc_upvotes.sql
--
-- NOTE: The previously staged /home/claude/migrate_polis_upvotes.sql references
-- polis_threads which is not used by the current Polis implementation.
-- Do NOT run that file. Use this one instead.

CREATE TABLE IF NOT EXISTS polis_discussion_upvotes (
  learner_id  INT NOT NULL,
  comment_id  INT NOT NULL,
  created_at  DATETIME DEFAULT current_timestamp(),
  PRIMARY KEY (learner_id, comment_id),
  FOREIGN KEY (learner_id) REFERENCES learners(id)          ON DELETE CASCADE,
  FOREIGN KEY (comment_id) REFERENCES polis_discussions(id) ON DELETE CASCADE
);
