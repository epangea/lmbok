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
