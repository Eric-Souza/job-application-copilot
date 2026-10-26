"""Usage counting for every run, plus Langfuse tracing when its keys are set.

Each segment of a run (start to review, a revision, a retry) is one trace; all of a run's traces
share a Langfuse session whose id is the run id, so the whole run reads as one timeline.
"""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.config import get_settings

log = logging.getLogger(__name__)


class UsageCounter(BaseCallbackHandler):
    """Adds up model calls and the tokens they report (failed calls report nothing)."""

    run_inline = True  # just counters; no need for a thread

    def __init__(self) -> None:
        self.calls = self.input_tokens = self.output_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.calls += 1
        for generations in response.generations:
            for generation in generations:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)


@dataclass
class Trace:
    usage: UsageCounter
    callbacks: list[BaseCallbackHandler] = field(default_factory=list)


@lru_cache
def langfuse_client():
    """The Langfuse client, or None when tracing is off."""
    settings = get_settings()
    if not settings.langfuse_configured:
        return None
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


@contextmanager
def traced(run_id: str, name: str) -> Iterator[Trace]:
    """Callbacks for one segment of a run: pass trace.callbacks in the graph config."""
    usage = UsageCounter()
    if langfuse_client() is None:
        yield Trace(usage, [usage])
        return
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    with propagate_attributes(session_id=run_id, trace_name=name):
        yield Trace(usage, [usage, CallbackHandler()])


async def session_url(run_id: str) -> str | None:
    """A link to the run's session in Langfuse, or None when tracing is off or Langfuse is unreachable."""
    client = langfuse_client()
    if client is None:
        return None
    try:
        # The project id comes from one API call, which the client caches
        project_id = await asyncio.to_thread(client._get_project_id)
    except Exception as exc:  # noqa: BLE001 -- a missing link must never break reading a run
        log.warning("Could not get the Langfuse project id: %s", str(exc).splitlines()[0][:200])
        return None
    if not project_id:
        return None
    return f"{get_settings().langfuse_host.rstrip('/')}/project/{project_id}/sessions/{run_id}"


def flush() -> None:
    """Send buffered traces; call before the process exits."""
    if client := langfuse_client():
        client.flush()
