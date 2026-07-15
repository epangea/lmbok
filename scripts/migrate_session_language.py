#!/usr/bin/env python3
"""
Migration: Add `language` column to sessions table.
- Backfills existing sessions heuristically based on warmup_prompt content
- Sets default to 'en' for future sessions
Run: python migrate_session_language.py
"""

import re
import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Async MariaDB connection (same as main.py)
DB_USER = os.getenv("DB_USER", "freqlearn")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "freqlearn")

DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def detect_language(text: str) -> str:
    """Heuristically detect language from session content."""
    if not text:
        return "en"
    
    text = text[:500]  # Sample first 500 chars for speed
    
    # Common character ranges for major non-English languages
    if re.search(r"[\u0400-\u04FF]", text):  # Cyrillic (Russian)
        return "ru"
    if re.search(r"[\u00C0-\u024F]", text):  # Extended Latin (French, Spanish, German accents)
        # More specific checks
        if re.search(r"[éèêëÉÈÊËàâÀÂùûÙÛçÇ]", text):
            return "fr"
        if re.search(r"[äöüÄÖÜß]", text):
            return "de"
        if re.search(r"[ñÑ¿¡]", text):
            return "es"
        if re.search(r"[\u00C0-\u00FF]", text):  # Vietnamese, etc. accents
            return "vi"  # Default extended Latin to Vietnamese
    
    return "en"


async def migrate():
    async with engine.begin() as conn:
        # Check if column exists
        result = await conn.execute(text("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'sessions' AND COLUMN_NAME = 'language'
        """), {"db": DB_NAME})
        if not result.fetchone():
            print("Adding language column to sessions table...")
            await conn.execute(text("""
                ALTER TABLE sessions 
                ADD COLUMN language VARCHAR(5) DEFAULT 'en' 
                AFTER created_at
            """))
            await conn.commit()
            print("Column added.")
        else:
            print("language column already exists.")
    
    # Backfill existing sessions
    async with async_session() as session:
        # Get sessions missing language or with NULL
        result = await session.execute(text("""
            SELECT id, warmup_prompt, explore_content 
            FROM sessions 
            WHERE language IS NULL OR language = ''
        """))
        rows = result.fetchall()
        
        updated = 0
        for row in rows:
            sid, warmup, explore = row
            lang = detect_language((warmup or "") + (explore or ""))
            await session.execute(
                text("UPDATE sessions SET language = :lang WHERE id = :sid"),
                {"lang": lang, "sid": sid}
            )
            updated += 1
            if updated % 100 == 0:
                print(f"  Processed {updated} sessions...")
        
        await session.commit()
        print(f"Backfilled {updated} sessions with detected language.")
    
    await engine.dispose()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())