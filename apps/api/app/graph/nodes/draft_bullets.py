from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.graph import prompts
from app.graph.grounding import check_draft, check_summary
from app.graph.state import Deps, GraphState, evidence_map
from app.schemas import Draft, DraftSpec


async def draft_bullets(state: GraphState, deps: Deps) -> GraphState:
    """Draft tailored bullets from covered requirements, then grounding-check them.

    After a "revise" review, the previous draft and the feedback are added to the prompt.
    The draft is streamed as it's written: each partial version goes to the graph's custom
    stream (shown live in the UI), and only the complete one is validated and checked.
    """
    evidence = evidence_map(state)
    system = prompts.DRAFT_SYSTEM
    user = prompts.draft_user(state["analysis"], state["requirements"], state["matches"], evidence)
    previous, feedback = state.get("draft"), state.get("feedback", "")
    if previous and feedback:
        system += "\n\n" + prompts.REVISE_SYSTEM
        user += "\n\n" + prompts.revise_user(previous, feedback)

    revision = previous.revision + 1 if previous else 1
    # A JSON schema rather than the model class, so the stream yields partial dicts as tokens arrive
    model = deps.llm.with_structured_output(DraftSpec.model_json_schema(), method="json_schema")
    write = get_stream_writer()
    partial: dict[str, Any] = {}
    async for partial in model.astream([SystemMessage(system), HumanMessage(user)]):
        write({"draft": preview(partial, revision)})
    draft = DraftSpec.model_validate(partial)
    bullets, dropped = check_draft(draft.bullets, evidence, {r.id for r in state["requirements"]})
    return {
        "draft": Draft(
            summary=draft.summary,
            bullets=bullets,
            warnings=dropped + check_summary(draft.summary, evidence),
            revision=revision,
        ),
        "feedback": "",
    }


def preview(partial: dict[str, Any], revision: int) -> dict[str, Any]:
    """The text written so far. A partial bullet may not have its ids yet, so only text is sent."""
    bullets = [b.get("text", "") for b in partial.get("bullets", []) if isinstance(b, dict)]
    return {"revision": revision, "summary": partial.get("summary", ""), "bullets": [b for b in bullets if b]}
