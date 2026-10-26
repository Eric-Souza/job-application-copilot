from langchain_core.messages import HumanMessage, SystemMessage

from app.graph import prompts
from app.graph.grounding import check_draft
from app.graph.state import Deps, GraphState, evidence_map
from app.schemas import Draft, DraftSpec


async def draft_bullets(state: GraphState, deps: Deps) -> GraphState:
    """Draft tailored bullets from covered requirements, then grounding-check them."""
    evidence = evidence_map(state)
    draft: DraftSpec = await deps.llm.with_structured_output(DraftSpec).ainvoke(
        [
            SystemMessage(prompts.DRAFT_SYSTEM),
            HumanMessage(
                prompts.draft_user(state["analysis"], state["requirements"], state["matches"], evidence)
            ),
        ]
    )
    bullets, warnings = check_draft(draft.bullets, evidence, {r.id for r in state["requirements"]})
    return {"draft": Draft(summary=draft.summary, bullets=bullets), "warnings": warnings}
