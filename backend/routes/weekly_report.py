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

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from mail import send_mail

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


async def main() -> None:
    db_url = _load_db_url()
    engine = create_async_engine(db_url, pool_size=5)
    async with engine.begin() as conn:
        learners = (await conn.execute(text("""
            SELECT l.id, l.username, l.display_name, l.email
            FROM learners l
            JOIN learner_streaks ls ON ls.learner_id = l.id
            WHERE ls.last_activity_date >= NOW() - INTERVAL :days DAY
        """), {"days": WINDOW_DAYS})).mappings().all()

        log.info("Found %d active learners in last %d days", len(learners), WINDOW_DAYS)

        for row in learners:
            lid = row["id"]
            email = row["email"]
            if not email:
                continue

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

            subject = f"Your Weekly Waves, {name}"
            body = (
                f"Hi {name},\n\n"
                f"The frequencies you surfed this past week:\n\n"
                f"  Sessions started : {int(stats['session_count'] or 0)}\n"
                f"  Sessions completed: {int(stats['completed'] or 0)}\n"
                f"  XP earned        : {int(stats['total_xp'] or 0)}\n"
                f"  Minutes learned  : {int(stats['total_minutes'] or 0)}\n"
                f"  Favorite arts    : {top_arts}\n\n"
                "Keep surfing the frequencies!\n\n"
                "Building Ourselves, in Our House!\n"
            )

            try:
                send_mail(
                    to=email,
                    subject=subject,
                    body=body,
                    reply_to=REPLY_TO,
                )
                log.info("Sent report to %s (%s)", name, email)
            except Exception as exc:
                log.warning("Failed to send report to %s: %s", email, exc)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
