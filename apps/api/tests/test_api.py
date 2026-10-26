"""The HTTP API with a fake LLM: run lifecycle, review decisions, retries, and the SSE stream."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REPO_ROOT
from app.db import AsyncSessionLocal
from app.graph.state import Deps
from app.main import create_app
from app.models import Run
from app.schemas import DraftSpec, MatchReport, PostingAnalysis
from app.services import ingest
from app.services.ingest import ingest_file
from app.services.runs import RESTARTED
from tests.conftest import axis_vector
from tests.fakes import FakeLLM, fixed_search, memory_saver
from tests.test_graph import ANALYSIS, DRAFT, HITS, good_matches

POSTING = "Senior Backend Engineer at Northwind. " * 3


@asynccontextmanager
async def api(llm: FakeLLM | None = None, search=None):
    """The app with its lifespan running, plus a client and the run manager."""
    llm = llm or FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    app = create_app(Deps(llm=llm, search=search or fixed_search(HITS)), checkpointer=memory_saver())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.runs


async def started(client, runs) -> str:
    response = await client.post("/runs", json={"posting": POSTING})
    assert response.status_code == 202
    run_id = response.json()["id"]
    await runs.wait(run_id)
    return run_id


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


async def test_run_pauses_for_review_then_finishes_on_approve():
    async with api() as (client, runs):
        run_id = await started(client, runs)

        run = (await client.get(f"/runs/{run_id}")).json()
        assert run["status"] == "awaiting_review"
        assert (run["title"], run["company"]) == ("Senior Backend Engineer", "Northwind")
        assert [b["text"] for b in run["review"]["bullets"]] == [b.text for b in DRAFT.bullets]
        assert run["result"] is None
        assert run_id in [r["id"] for r in (await client.get("/runs")).json()]

        response = await client.post(f"/runs/{run_id}/review", json={"action": "approve"})
        assert response.status_code == 202
        await runs.wait(run_id)

        run = (await client.get(f"/runs/{run_id}")).json()
        assert run["status"] == "done"
        assert run["review"] is None
        assert run["result"]["coverage"] == {"strong": 1, "partial": 1, "missing": 1}


async def test_revise_through_the_api():
    async with api() as (client, runs):
        run_id = await started(client, runs)

        await client.post(f"/runs/{run_id}/review", json={"action": "revise", "feedback": "Shorter."})
        await runs.wait(run_id)

        run = (await client.get(f"/runs/{run_id}")).json()
        assert (run["status"], run["review"]["revision"]) == ("awaiting_review", 2)


async def test_review_is_validated_and_only_allowed_while_paused():
    async with api() as (client, runs):
        run_id = await started(client, runs)

        bad = await client.post(f"/runs/{run_id}/review", json={"action": "revise"})
        assert bad.status_code == 422  # rejected before it reaches the graph

        await client.post(f"/runs/{run_id}/review", json={"action": "approve"})
        await runs.wait(run_id)
        again = await client.post(f"/runs/{run_id}/review", json={"action": "approve"})
        assert again.status_code == 409
        assert again.json()["detail"] == "The run is done, not awaiting review."

        missing = await client.post(f"/runs/{uuid.uuid4()}/review", json={"action": "approve"})
        assert missing.status_code == 404
        assert (await client.get(f"/runs/{uuid.uuid4()}")).status_code == 404
        assert (await client.post("/runs", json={"posting": "too short"})).status_code == 422


async def test_failed_run_retries_from_the_failed_step():
    attempts = []

    def flaky_draft(_messages):
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("Invalid JSON in structured output\nmore detail")  # not retried in-graph
        return DRAFT

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: flaky_draft})
    async with api(llm) as (client, runs):
        run_id = await started(client, runs)
        run = (await client.get(f"/runs/{run_id}")).json()
        assert (run["status"], run["error"]) == ("failed", "Invalid JSON in structured output")

        assert (await client.post(f"/runs/{run_id}/retry")).status_code == 202
        await runs.wait(run_id)

        run = (await client.get(f"/runs/{run_id}")).json()
        assert (run["status"], run["error"]) == ("awaiting_review", None)
        assert [name for name, _ in llm.calls] == ["PostingAnalysis", "MatchReport", "DraftSpec", "DraftSpec"]
        assert (await client.post(f"/runs/{run_id}/retry")).status_code == 409


async def test_runs_interrupted_by_a_restart_are_marked_failed():
    run_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        db.add(Run(id=run_id, status="running", title="Left running"))
        await db.commit()

    async with api() as (client, _):
        run = (await client.get(f"/runs/{run_id}")).json()

    assert (run["status"], run["error"]) == ("failed", RESTARTED)


async def test_events_stream_steps_then_the_review():
    gate = asyncio.Event()
    search = fixed_search(HITS)

    async def gated_search(queries, k):
        await gate.wait()  # hold the run until the stream is subscribed
        return await search(queries, k)

    async with api(search=gated_search) as (client, runs):
        run_id = (await client.post("/runs", json={"posting": POSTING})).json()["id"]
        stream = asyncio.create_task(client.get(f"/runs/{run_id}/events"))
        while not runs._subscribers.get(run_id):
            await asyncio.sleep(0.01)
        gate.set()
        response = await asyncio.wait_for(stream, timeout=10)

        assert response.headers["content-type"].startswith("text/event-stream")
        events = sse_events(response.text)
        assert events[0][0] == "status"
        assert events[0][1]["status"] == "running"
        nodes = [(data["node"], data["detail"]) for name, data in events if name == "node"]
        assert nodes == [
            ("parse_posting", "3 requirements"),
            ("retrieve_experience", "3 pieces of evidence"),
            ("match_requirements", "1 strong, 1 partial, 1 missing"),
            ("draft_bullets", "draft 1: 2 bullets"),
        ]
        assert events[-1][0] == "review"
        assert events[-1][1]["revision"] == 1

        # A run that isn't running sends its status and closes
        events = sse_events((await client.get(f"/runs/{run_id}/events")).text)
        assert [(name, data["status"]) for name, data in events] == [("status", "awaiting_review")]


async def test_experience_search(db: AsyncSession, monkeypatch):
    async def fake_embed(texts):
        return [axis_vector((0, 1.0)) for _ in texts]

    monkeypatch.setattr(ingest, "embed_documents", fake_embed)
    await ingest_file(db, REPO_ROOT / "data" / "samples" / "sample-resume.md")

    async with api() as (client, _):
        response = await client.get("/experience/search", params={"q": "payments Go", "mode": "keyword"})
        assert response.status_code == 200
        assert any("Go" in hit["content"] for hit in response.json())
        bad = await client.get("/experience/search", params={"q": "Go", "mode": "fuzzy"})
        assert bad.status_code == 422
