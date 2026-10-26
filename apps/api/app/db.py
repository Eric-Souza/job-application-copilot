import asyncio
import sys
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

# psycopg's async mode can't run on Windows' default Proactor event loop
LOOP_FACTORY = asyncio.SelectorEventLoop if sys.platform == "win32" else None


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


RUN_USAGE_COLUMNS = [
    "llm_calls INTEGER NOT NULL DEFAULT 0",
    "input_tokens INTEGER NOT NULL DEFAULT 0",
    "output_tokens INTEGER NOT NULL DEFAULT 0",
    "work_seconds DOUBLE PRECISION NOT NULL DEFAULT 0",
]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # create_all doesn't add columns to existing tables; these came after the runs table
        for column in RUN_USAGE_COLUMNS:
            await conn.execute(text(f"ALTER TABLE runs ADD COLUMN IF NOT EXISTS {column}"))
