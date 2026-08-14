# ============================================================
# FreqLearn Backend — db.py
# Async SQLAlchemy + MariaDB (via aiomysql)
# ============================================================

import os

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Load from environment — never hardcode credentials
DB_USER     = os.getenv("DB_USER",     "freqlearn")
DB_PASSWORD = os.getenv("DB_PASSWORD", "changeme")
DB_HOST     = os.getenv("DB_HOST",     "127.0.0.1")
DB_PORT     = os.getenv("DB_PORT",     "3306")
DB_NAME     = os.getenv("DB_NAME",     "freqlearn")

DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # set True during development to see SQL
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # reconnect if MariaDB dropped the connection
    pool_recycle=1800,   # 2026-08-13: proactively replace connections older than
                          # 30 min. pool_pre_ping alone doesn't cover a known
                          # aiomysql edge case where a stale connection's own
                          # ping check raises RuntimeError("...the handler is
                          # closed") instead of the exception type SQLAlchemy's
                          # pre-ping recovery logic catches. See PROJECT.md
                          # PART 30. Confirm this is comfortably under MariaDB's
                          # actual wait_timeout (SHOW VARIABLES LIKE
                          # 'wait_timeout';) before/after deploying.
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

# Dependency — inject into route handlers with FastAPI's Depends()
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
