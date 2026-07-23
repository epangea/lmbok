-- ============================================================
-- 2026-07-23 — add sessions.assess_companion_verdict (P40)
--
-- Why: P40 replaces the assess phase's red/coral "wrong answer" flag
-- with a Socratic AI companion conversation (new endpoint
-- POST /api/generate/assess-companion, mirrors the existing
-- /generate/scaffold pattern). When the learner engages the
-- companion and it concludes their reasoning holds up (or that more
-- than one answer is legitimately acceptable), it can silently raise
-- assess_score AND leave a short written verdict summary here —
-- consumed by prior_session_context.py's LEARNER CONTINUITY block so
-- future sessions know *why* a "wrong" pick was actually accepted,
-- not just that the score was high.
--
-- Storing a short AI-written summary, not the raw transcript
-- (privacy/size — same pattern as the Digital Avatar Story, which
-- summarizes rather than stores raw conversation history).
--
-- Purely additive, nullable column. Safe to run any time; existing
-- rows are unaffected (NULL = no companion conversation happened,
-- which is true for every row before this migration and for any
-- session where the learner answered correctly or skipped the
-- companion in favor of the self-rating fallback).
-- ============================================================

-- ---- PART A: read-only preflight — confirm current state before altering ----
DESCRIBE sessions;

-- ---- PART B: the actual change ----
ALTER TABLE sessions
    ADD COLUMN assess_companion_verdict JSON NULL
    AFTER assess_selected_index;

-- ---- Verify ----
DESCRIBE sessions;
