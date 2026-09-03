#!/usr/bin/env python3
"""
FreqLearn — weekly learner report mailer.

Enqueues a personalized weekly snapshot for every learner who used the
platform in the last 7 days. Designed to be triggered from cron.

Usage:
    python scripts/weekly_report.py

Environment (from backend/.env or system env):
    DATABASE_URL        — asyncpg DSN
    FREQLEARN_MAIL_FROM   — sender address
    FREQLEARN_MAIL_REPLY_TO — reply-to address
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

# Ensure backend package is importable when run as script from project root
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from mail import send_mail, unsubscribe_link, append_unsubscribe_footer
import ai_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("weekly_report")

WINDOW_DAYS = 7
FROM = os.getenv("FREQLEARN_MAIL_FROM", "epangea.info@gmail.com")
REPLY_TO = os.getenv("FREQLEARN_MAIL_REPLY_TO", "epangea.info@gmail.com")

DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT     = os.getenv("DB_PORT", "3306")
DB_NAME     = os.getenv("DB_NAME", "freqlearn")
DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)


def _load_db_url() -> str:
    """Return DATABASE_URL from env, falling back to backend/.env."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # Build from individual DB_* vars (matches db.py convention)
    db_user     = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host     = os.getenv("DB_HOST", "127.0.0.1")
    db_port     = os.getenv("DB_PORT", "3306")
    db_name     = os.getenv("DB_NAME", "freqlearn")
    url = (
        f"mysql+aiomysql://{db_user}:{db_password}"
        f"@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
    )
    if all([db_user, db_host, db_name]):
        return url
    # Last resort: parse backend/.env for DB_* or DATABASE_URL
    fallback = Path(__file__).resolve().parent.parent / ".env"
    if fallback.is_file():
        env_vars = {}
        for line in fallback.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env_vars[k.strip()] = v.strip().strip('"').strip("'")
        # Try pre-built URL first
        if "DATABASE_URL" in env_vars and env_vars["DATABASE_URL"]:
            return env_vars["DATABASE_URL"]
        # Try building from parts
        db_user     = env_vars.get("DB_USER", "root")
        db_password = env_vars.get("DB_PASSWORD", "")
        db_host     = env_vars.get("DB_HOST", "127.0.0.1")
        db_port     = env_vars.get("DB_PORT", "3306")
        db_name     = env_vars.get("DB_NAME", "freqlearn")
        if db_user and db_host and db_name:
            return (
                f"mysql+aiomysql://{db_user}:{db_password}"
                f"@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
            )
    raise RuntimeError("DATABASE_URL not set — weekly report cannot run")


async def _weekly_story_paragraph(session_local, name: str, story_rows) -> str | None:
    """Freshly distil this week's session challenge/reflect answers (and any
    resolved companion verdicts) into a short "this week's growth" paragraph
    for the email. Deliberately NOT persisted to learners.learner_profile —
    that's My Story's own accumulated distillation (see
    generate.py::update_learner_profile); this is a one-off summary of just
    this week, generated fresh each send. Returns None (fail-soft) if there's
    nothing to say or the AI call fails, so the stats-only email still sends.
    """
    if not story_rows:
        return None

    lines = []
    for r in story_rows:
        if r["title"]:
            lines.append(f"SESSION: {r['title']}")
        if r["challenge_prompt"] and r["challenge_response"]:
            lines.append(f"CHALLENGE Q: {r['challenge_prompt']}\nCHALLENGE A: {r['challenge_response']}")
        if r["reflect_prompt"] and r["reflect_response"]:
            lines.append(f"REFLECT Q: {r['reflect_prompt']}\nREFLECT A: {r['reflect_response']}")
        verdict = r["assess_companion_verdict"]
        if verdict and isinstance(verdict, dict) and verdict.get("summary"):
            lines.append(f"COMPANION DISCUSSION: {verdict['summary']}")
    transcript = "\n\n".join(lines).strip()
    if not transcript:
        return None

    prompt = f"""You write a short, warm "this week's growth" paragraph for {name}'s weekly learning-progress email, based on what they actually explored, wrote, and discussed this week on the Surfing the Frequencies platform.

THIS WEEK'S SESSION CONTENT:
{transcript}

Write 2–4 sentences, second person ("you"), grounded in the specific substance above — not generic encouragement, and not a restatement of session titles or stats (those are shown elsewhere in the email). No preamble, no heading, just the paragraph itself."""

    try:
        async with session_local() as db:
            ai_resp = await ai_client.ai_complete(
                "weekly_story",
                db=db,
                prompt=prompt,
                tier="large",
                response_format="text",
                max_tokens=220,
                temperature=0.6,
            )
        return ai_resp.content.strip() or None
    except Exception as exc:
        log.warning("Weekly story paragraph failed for %s: %s", name, exc)
        return None


async def main() -> None:
    db_url = _load_db_url()
    engine = create_async_engine(db_url, pool_size=5)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # Shared by every row written in this run, so a re-run of the same
    # week upserts instead of duplicating (see UNIQUE(learner_id, week_start)
    # on weekly_stories).
    week_start = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).date()

    async with engine.begin() as conn:
        # Deliberately NOT filtered by weekly_report_opt_out — that flag
        # only gates the email send below; every active learner still gets
        # their weekly_stories row so opting out of the email doesn't mean
        # opting out of having your own progress recorded.
        learners = (await conn.execute(text("""
            SELECT l.id, l.username, l.display_name, l.email,
                   COALESCE(lp.weekly_report_opt_out, 0) AS opted_out
            FROM learners l
            JOIN learner_streaks ls ON ls.learner_id = l.id
            LEFT JOIN learner_preferences lp ON lp.learner_id = l.id
            WHERE ls.last_activity_date >= NOW() - INTERVAL :days DAY
        """), {"days": WINDOW_DAYS})).mappings().all()

        log.info("Found %d active learners in last %d days", len(learners), WINDOW_DAYS)

        for row in learners:
            lid = row["id"]
            email = row["email"]

            stats = (await conn.execute(text("""
                SELECT
                    COALESCE(SUM(s.xp_earned), 0)        AS total_xp,
                    COALESCE(SUM(s.duration_seconds), 0)  AS total_minutes,
                    COUNT(*)                              AS session_count,
                    SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    MAX(s.started_at)                     AS last_session
                FROM sessions s
                WHERE s.learner_id = :lid
                  AND s.created_at >= NOW() - INTERVAL :days DAY
            """), {"lid": lid, "days": WINDOW_DAYS})).mappings().first()

            art_rows = (await conn.execute(text("""
                SELECT a.slug, COUNT(*) AS cnt
                FROM sessions s
                JOIN arts a ON a.id = s.art_id
                WHERE s.learner_id = :lid
                  AND s.status = 'completed'
                  AND s.created_at >= NOW() - INTERVAL :days DAY
                GROUP BY a.id, a.slug
                ORDER BY cnt DESC
                LIMIT 5
            """), {"lid": lid, "days": WINDOW_DAYS})).mappings().all()

            top_arts = ", ".join(r["slug"] for r in art_rows) or "—"
            name = row["display_name"] or row["username"]

            story_rows = (await conn.execute(text("""
                SELECT s.title, s.challenge_prompt, s.challenge_response,
                       s.reflect_prompt, s.reflect_response, s.assess_companion_verdict
                FROM sessions s
                WHERE s.learner_id = :lid
                  AND s.status = 'completed'
                  AND s.created_at >= NOW() - INTERVAL :days DAY
                  AND (
                        (s.challenge_response IS NOT NULL AND s.challenge_response != '')
                     OR (s.reflect_response   IS NOT NULL AND s.reflect_response   != '')
                     OR s.assess_companion_verdict IS NOT NULL
                  )
                ORDER BY s.created_at ASC
            """), {"lid": lid, "days": WINDOW_DAYS})).mappings().all()

            story_paragraph = await _weekly_story_paragraph(SessionLocal, name, story_rows)

            if story_paragraph:
                await conn.execute(text("""
                    INSERT INTO weekly_stories (learner_id, week_start, paragraph)
                    VALUES (:lid, :week_start, :paragraph)
                    ON DUPLICATE KEY UPDATE paragraph = VALUES(paragraph)
                """), {"lid": lid, "week_start": week_start, "paragraph": story_paragraph})

            # Email send is gated on opt-out + a valid address; the
            # weekly_stories row above was already written regardless.
            if row["opted_out"] or not email:
                continue

            subject = f"Your Weekly Waves, {name}"
            body = (
                f"Hi {name},\n\n"
                f"The frequencies you surfed this past week:\n\n"
                f"  Sessions started : {int(stats['session_count'] or 0)}\n"
                f"  Sessions completed: {int(stats['completed'] or 0)}\n"
                f"  XP earned        : {int(stats['total_xp'] or 0)}\n"
                f"  Minutes learned  : {int(stats['total_minutes'] or 0)}\n"
                f"  Favorite arts    : {top_arts}\n\n"
                + (f"This week's growth:\n{story_paragraph}\n\n" if story_paragraph else "")
                + "Keep surfing the frequencies!\n\n"
                "Building Ourselves, in Our House!\n"
            )

            # Own permanent opt-out (LearnerPreferences.weekly_report_opt_out),
            # split from the admin newsletter's newsletter_opt_out (2026-08-29)
            # so a learner can drop one without losing the other.
            # kind="weekly_report" is what makes the unsubscribe link/token
            # flip the right flag (see mail._unsubscribe_token) -- without
            # it this would silently flip newsletter_opt_out instead.
            unsub_url = unsubscribe_link(lid, email, kind="weekly_report")
            body = append_unsubscribe_footer(body, unsub_url)

            try:
                send_mail(
                    to=email,
                    subject=subject,
                    body=body,
                    reply_to=REPLY_TO,
                    list_unsubscribe_url=unsub_url,
                )
                log.info("Sent report to %s (%s)", name, email)
            except Exception as exc:
                log.warning("Failed to send report to %s: %s", email, exc)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
