"""The HTTP API: start runs, follow them over SSE, and send review decisions.

uvicorn app.main:app --loop app.db:LOOP_FACTORY --port 8000

(--loop matters on Windows only: psycopg's async mode needs the selector event loop.)
"""

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.graph.builder import build_graph, default_deps
from app.graph.checkpointer import postgres_checkpointer
from app.graph.state import Deps
from app.routers import experience, runs
from app.services import tracing
from app.services.runs import RunManager


def create_app(deps: Deps | None = None, checkpointer=None) -> FastAPI:
    """Tests pass a fake LLM and an in-memory checkpointer; the server uses Gemini and Postgres."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            saver = checkpointer or await stack.enter_async_context(postgres_checkpointer())
            await init_db()
            manager = RunManager(build_graph(deps or default_deps(), checkpointer=saver), AsyncSessionLocal)
            await manager.recover()
            app.state.runs = manager
            yield
            await manager.shutdown()
            tracing.flush()

    app = FastAPI(title="Job Application Copilot", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(runs.router)
    app.include_router(experience.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
