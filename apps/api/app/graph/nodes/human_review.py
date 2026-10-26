from typing import Any, Literal

from langgraph.types import Command, interrupt
from pydantic import ValidationError

from app.graph.grounding import check_draft, check_summary
from app.graph.state import GraphState, evidence_map
from app.schemas import Draft, ReviewDecision


def review_request(state: GraphState) -> dict[str, Any]:
    """What the reviewer sees while the graph is paused. Plain JSON, so an API can pass it on."""
    draft = state["draft"]
    return {
        "revision": draft.revision,
        "summary": draft.summary,
        "bullets": [b.model_dump() for b in draft.bullets],
        "warnings": state.get("warnings", []) + draft.warnings,
        "coverage": [m.model_dump() for m in state["matches"]],
    }


def apply_edit(state: GraphState, decision: ReviewDecision) -> Draft:
    """Replace the summary and/or bullets, and run the same grounding checks as on a model draft."""
    draft = state["draft"]
    evidence = evidence_map(state)
    summary = draft.summary if decision.summary is None else decision.summary
    if decision.bullets is None:
        old_summary = check_summary(draft.summary, evidence)
        bullets, dropped = draft.bullets, [w for w in draft.warnings if w not in old_summary]
    else:  # the model's dropped-bullet warnings no longer apply
        bullets, dropped = check_draft(decision.bullets, evidence, {r.id for r in state["requirements"]})
    return Draft(
        summary=summary,
        bullets=bullets,
        warnings=dropped + check_summary(summary, evidence),
        revision=draft.revision,
    )


async def human_review(state: GraphState) -> Command[Literal["finalize", "draft_bullets", "human_review"]]:
    """Pause until the reviewer approves, edits, or asks for a revision.

    On resume LangGraph re-runs this node from the top and interrupt() returns the decision,
    so everything before it must be safe to repeat (it only reads state). Resume values are
    saved and replayed in order, so an invalid decision can't be raised as an error: it would
    be replayed on every later resume. Instead the node asks again, with the error attached.
    """
    request = review_request(state)
    while True:
        try:
            decision = ReviewDecision.model_validate(interrupt(request))
            break
        except ValidationError as e:
            request = {**request, "error": "; ".join(err["msg"] for err in e.errors())}
    if decision.action == "approve":
        return Command(goto="finalize")
    if decision.action == "revise":
        return Command(goto="draft_bullets", update={"feedback": decision.feedback})
    # Edits come back for review, so the reviewer sees any new flags before approving
    return Command(goto="human_review", update={"draft": apply_edit(state, decision)})
