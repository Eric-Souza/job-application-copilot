"""Test setup: point the app at a separate `<db>_test` database before anything imports app.db."""

import asyncio
import os
import sys

import psycopg
import pytest
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings

if sys.platform == "win32":
    # psycopg's async mode can't run on the default Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_base_url = make_url(Settings().database_url)
TEST_DB = f"{_base_url.database}_test"
os.environ["DATABASE_URL"] = _base_url.set(database=TEST_DB).render_as_string(hide_password=False)
# Never send test runs to Langfuse, even when .env has keys
os.environ["LANGFUSE_PUBLIC_KEY"] = os.environ["LANGFUSE_SECRET_KEY"] = ""
get_settings.cache_clear()

EMBED_DIM = get_settings().embed_dim


def _create_test_database() -> None:
    conninfo = _base_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(conninfo, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


@pytest.fixture(scope="session", autouse=True)
async def database():
    _create_test_database()
    from app.db import Base, engine, init_db

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db():
    from sqlalchemy import delete

    from app.db import AsyncSessionLocal
    from app.models import Source

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Source))  # chunks cascade
        await session.commit()
        yield session


def axis_vector(*weights: tuple[int, float]) -> list[float]:
    """An embedding with weight on chosen axes, for predictable cosine similarity."""
    vec = [0.0] * EMBED_DIM
    for axis, weight in weights:
        vec[axis] = weight
    return vec
