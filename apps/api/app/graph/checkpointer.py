"""Where paused and finished runs are saved, so a run survives restarts and resumes by thread id.

LangGraph stores a checkpoint after every step. The state holds Pydantic models, and its
msgpack serializer only rebuilds classes it's told about, so ours are listed explicitly.
"""

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel
from sqlalchemy.engine import make_url

from app import schemas
from app.config import get_settings

STATE_TYPES = [
    (cls.__module__, cls.__name__)
    for _, cls in inspect.getmembers(schemas, inspect.isclass)
    if issubclass(cls, BaseModel) and cls.__module__ == schemas.__name__
]


def serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)


def psycopg_url(database_url: str) -> str:
    """postgresql+psycopg://... (SQLAlchemy) -> postgresql://... (plain psycopg)."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def postgres_checkpointer(
    database_url: str | None = None, max_connections: int = 5
) -> AsyncIterator[AsyncPostgresSaver]:
    """Checkpoints in the app's Postgres database. Creates LangGraph's tables on first use.

    Uses a pool, so the API can serve several runs at once; the CLI just uses one connection.
    """
    url = psycopg_url(database_url or get_settings().database_url)
    # The settings AsyncPostgresSaver.from_conn_string uses for its single connection
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    async with AsyncConnectionPool(url, min_size=1, max_size=max_connections, kwargs=kwargs) as pool:
        saver = AsyncPostgresSaver(conn=pool, serde=serializer())
        await saver.setup()
        yield saver
