"""Run the agent in the background for the API, and fan its progress out to SSE subscribers.

A run executes in segments: from the start (or a review decision, or a retry) until it pauses
for review, finishes, or fails. Each segment is an asyncio task. Every step is checkpointed by
LangGraph, so a segment that dies with the process can be retried from the last completed step.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from langgraph.types import Command
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Run
from app.schemas import Draft, ReviewDecision, TailoredResume
from app.services import tracing

log = logging.getLogger(__name__)

RunStatus = Literal["running", "awaiting_review", "done", "failed"]
RESTARTED = "The server restarted during this run. Retry to continue from the last completed step."


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: RunStatus
    title: str
    company: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class Step(BaseModel):
    node: str
    detail: str


class Usage(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0  # time spent running, not waiting for review


class RunView(RunSummary):
    usage: Usage = Usage()
    trace_url: str | None = None  # the run's session in Langfuse, when tracing is on
    steps: list[Step] = []  # the steps that have produced their output so far
    next_step: str | None = None  # running now, waiting (human_review), or the one that failed
    review: dict[str, Any] | None = None  # the paused draft, while awaiting review
    result: TailoredResume | None = None  # once done


# The state key each step writes, so finished steps can be read back from a checkpoint
STEP_OUTPUTS = {
    "parse_posting": "requirements",
    "retrieve_experience": "evidence",
    "match_requirements": "matches",
    "draft_bullets": "draft",
    "finalize": "result",
}


class RunConflict(Exception):
    """The run isn't in a state that allows this action (e.g. reviewing a run that's still going)."""


def describe(node: str, changes: dict[str, Any]) -> str:
    """A one-line summary of what a step produced, for the live view."""
    if node == "parse_posting":
        return f"{len(changes['requirements'])} requirements"
    if node == "retrieve_experience":
        return f"{len(changes['evidence'])} pieces of evidence"
    if node == "match_requirements":
        counts = {
            c: sum(m.coverage == c for m in changes["matches"]) for c in ("strong", "partial", "missing")
        }
        return ", ".join(f"{n} {c}" for c, n in counts.items())
    if node == "draft_bullets":
        draft: Draft = changes["draft"]
        return f"draft {draft.revision}: {len(draft.bullets)} bullets"
    return ""


def short_error(exc: Exception) -> str:
    """Provider errors can be pages long; keep the first line."""
    first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    return first[:300]


class RunManager:
    def __init__(self, graph, sessions: async_sessionmaker[AsyncSession]):
        self.graph, self.sessions = graph, sessions
        self._tasks: dict[str, asyncio.Task] = {}  # the running segment per run
        # Each subscriber belongs to the segment it subscribed during, so a segment that's ending
        # can't close (or feed) the stream of the segment that follows it
        self._subscribers: dict[str, dict[asyncio.Queue, asyncio.Task]] = defaultdict(dict)

    # --- actions -------------------------------------------------------------------------

    async def start(self, posting: str) -> RunSummary:
        run = Run(id=str(uuid.uuid4()), status="running", title="")
        async with self.sessions() as db:
            db.add(run)
            await db.commit()
        self._launch(run.id, {"posting": posting})
        return RunSummary.model_validate(run)

    async def review(self, run_id: str, decision: ReviewDecision) -> None:
        await self._transition(run_id, "awaiting_review")
        self._launch(run_id, Command(resume=decision.model_dump()))

    async def retry(self, run_id: str) -> None:
        """Continue a failed run from its last checkpoint (astream with no input does that)."""
        await self._transition(run_id, "failed")
        self._launch(run_id, None)

    # --- reads ---------------------------------------------------------------------------

    async def list_runs(self, limit: int = 50) -> list[RunSummary]:
        async with self.sessions() as db:
            rows = await db.scalars(select(Run).order_by(Run.created_at.desc()).limit(limit))
            return [RunSummary.model_validate(r) for r in rows]

    async def get(self, run_id: str) -> RunView | None:
        async with self.sessions() as db:
            run = await db.get(Run, run_id)
        if run is None:
            return None
        view = RunView.model_validate(run)
        view.usage = Usage(
            llm_calls=run.llm_calls,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            seconds=round(run.work_seconds, 1),
        )
        view.trace_url = await tracing.session_url(run_id)
        snapshot = await self.graph.aget_state(self._config(run_id))
        values = snapshot.values
        view.steps = [
            Step(node=node, detail=describe(node, values))
            for node, key in STEP_OUTPUTS.items()
            if key in values
        ]
        view.next_step = snapshot.next[0] if snapshot.next else None
        if run.status == "awaiting_review" and snapshot.interrupts:
            view.review = snapshot.interrupts[0].value
        if run.status == "done":
            view.result = snapshot.values.get("result")
        return view

    async def events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        """The run's current state, then live events until this segment ends.

        Subscribes before reading the state, so no event is missed between the two.
        """
        queue: asyncio.Queue = asyncio.Queue()
        segment = self._tasks.get(run_id)
        if segment:
            self._subscribers[run_id][queue] = segment
        try:
            view = await self.get(run_id)
            if view is None:
                return
            yield {"event": "status", "data": view.model_dump(mode="json")}
            if segment is None:
                return
            while (event := await queue.get()) is not None:
                yield event
        finally:
            subscribers = self._subscribers.get(run_id, {})
            subscribers.pop(queue, None)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    async def wait(self, run_id: str) -> None:
        """Wait for the current segment to end (used by tests and shutdown)."""
        if task := self._tasks.get(run_id):
            await asyncio.wait([task])

    # --- lifecycle -----------------------------------------------------------------------

    async def recover(self) -> int:
        """Mark runs that were mid-segment when the process died as failed, so they can be retried."""
        async with self.sessions() as db:
            result = await db.execute(
                update(Run).where(Run.status == "running").values(status="failed", error=RESTARTED)
            )
            await db.commit()
        return result.rowcount

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())  # each one removes itself as it ends
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- internals -----------------------------------------------------------------------

    @staticmethod
    def _config(run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    async def _transition(self, run_id: str, required: RunStatus) -> None:
        """Atomically move a run from `required` to running, so two requests can't both resume it."""
        async with self.sessions() as db:
            result = await db.execute(
                update(Run)
                .where(Run.id == run_id, Run.status == required)
                .values(status="running", error=None)
            )
            await db.commit()
            if result.rowcount == 0:
                run = await db.get(Run, run_id)
                if run is None:
                    raise KeyError(run_id)
                raise RunConflict(
                    f"The run is {run.status.replace('_', ' ')}, not {required.replace('_', ' ')}."
                )

    def _launch(self, run_id: str, payload) -> None:
        self._tasks[run_id] = asyncio.create_task(self._execute(run_id, payload), name=f"run-{run_id}")

    async def _set(self, run_id: str, **values) -> None:
        async with self.sessions() as db:
            await db.execute(update(Run).where(Run.id == run_id).values(**values))
            await db.commit()

    def _publish(self, run_id: str, event: dict[str, Any] | None) -> None:
        """Send an event to the current segment's subscribers (only called from that segment)."""
        segment = asyncio.current_task()
        for queue, subscribed_to in self._subscribers.get(run_id, {}).items():
            if subscribed_to is segment:
                queue.put_nowait(event)

    async def _execute(self, run_id: str, payload) -> None:
        segment = "start" if isinstance(payload, dict) else "retry" if payload is None else "review"
        with tracing.traced(run_id, segment) as trace:
            await self._stream(run_id, payload, trace)

    async def _stream(self, run_id: str, payload, trace: tracing.Trace) -> None:
        config = {**self._config(run_id), "callbacks": trace.callbacks}
        started = time.perf_counter()

        def spent() -> dict[str, Any]:
            """This segment's usage, added to the run's totals with the final status update."""
            return {
                "llm_calls": Run.llm_calls + trace.usage.calls,
                "input_tokens": Run.input_tokens + trace.usage.input_tokens,
                "output_tokens": Run.output_tokens + trace.usage.output_tokens,
                "work_seconds": Run.work_seconds + (time.perf_counter() - started),
            }

        try:
            async for mode, chunk in self.graph.astream(payload, config, stream_mode=["tasks", "updates"]):
                if mode == "tasks":
                    if "input" in chunk:  # a step starting (the finish event carries its result instead)
                        data = {"node": chunk["name"], "elapsed": round(time.perf_counter() - started, 1)}
                        self._publish(run_id, {"event": "step", "data": data})
                    continue
                for node, node_update in chunk.items():
                    if node == "__interrupt__":
                        continue
                    node_update = node_update or {}  # nodes that only route (Command) update nothing
                    if node == "parse_posting":
                        analysis = node_update["analysis"]
                        await self._set(run_id, title=analysis.title, company=analysis.company)
                    data = {
                        "node": node,
                        "elapsed": round(time.perf_counter() - started, 1),
                        "detail": describe(node, node_update),
                    }
                    self._publish(run_id, {"event": "node", "data": data})

            snapshot = await self.graph.aget_state(config)
            if snapshot.interrupts:
                await self._set(run_id, status="awaiting_review", **spent())
                self._publish(run_id, {"event": "review", "data": snapshot.interrupts[0].value})
            else:
                await self._set(run_id, status="done", **spent())
                result = snapshot.values["result"].model_dump(mode="json")
                self._publish(run_id, {"event": "done", "data": result})
        except asyncio.CancelledError:
            raise  # shutdown: the row stays "running", and recover() marks it on the next start
        except Exception as exc:
            log.exception("Run %s failed", run_id)
            message = short_error(exc)
            await self._set(run_id, status="failed", error=message, **spent())
            self._publish(run_id, {"event": "error", "data": {"message": message}})
        finally:
            # Both in one step, with no await between: a new subscriber either gets the None
            # or finds no running segment
            if self._tasks.get(run_id) is asyncio.current_task():
                del self._tasks[run_id]
            self._publish(run_id, None)  # ends this segment's streams
