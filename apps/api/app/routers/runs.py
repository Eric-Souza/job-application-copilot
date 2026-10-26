import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from app.schemas import ReviewDecision
from app.services.runs import RunConflict, RunManager, RunSummary, RunView

router = APIRouter(prefix="/runs", tags=["runs"])


class StartRun(BaseModel):
    posting: str = Field(min_length=50, max_length=30_000, description="The job posting text")


def manager(request: Request) -> RunManager:
    return request.app.state.runs


async def _found(runs: RunManager, run_id: str) -> RunView:
    view = await runs.get(run_id)
    if view is None:
        raise HTTPException(404, "No run with that id.")
    return view


@router.post("", status_code=202)
async def start_run(body: StartRun, request: Request) -> RunSummary:
    """Start tailoring. Follow progress at /runs/{id}/events."""
    return await manager(request).start(body.posting)


@router.get("")
async def list_runs(request: Request) -> list[RunSummary]:
    return await manager(request).list_runs()


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> RunView:
    return await _found(manager(request), run_id)


async def _act(request: Request, run_id: str, action) -> RunView:
    runs = manager(request)
    try:
        await action(runs)
    except KeyError:
        raise HTTPException(404, "No run with that id.") from None
    except RunConflict as e:
        raise HTTPException(409, str(e)) from None
    return await _found(runs, run_id)


@router.post("/{run_id}/review", status_code=202)
async def review_run(run_id: str, decision: ReviewDecision, request: Request) -> RunView:
    """Approve, revise, or edit the paused draft. The run continues in the background."""
    return await _act(request, run_id, lambda runs: runs.review(run_id, decision))


@router.post("/{run_id}/retry", status_code=202)
async def retry_run(run_id: str, request: Request) -> RunView:
    """Continue a failed run from the last step that completed."""
    return await _act(request, run_id, lambda runs: runs.retry(run_id))


@router.get("/{run_id}/events")
async def run_events(run_id: str, request: Request) -> EventSourceResponse:
    """Server-sent events: `status` (the run as it is now), then `step` as each step starts and
    `node` as it finishes, and one of `review`, `done`, or `error` when the run pauses or stops.
    The stream closes then; open it again after sending a review decision or a retry."""
    runs = manager(request)
    await _found(runs, run_id)

    async def stream():
        async for event in runs.events(run_id):
            yield {"event": event["event"], "data": json.dumps(event["data"], default=str)}

    return EventSourceResponse(stream())
