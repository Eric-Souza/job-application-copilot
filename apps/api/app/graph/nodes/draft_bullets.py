from langchain_core.messages import HumanMessage, SystemMessage

from app.graph import prompts
from app.graph.grounding import check_draft, check_summary
from app.graph.state import Deps, GraphState, evidence_map
from app.schemas import Draft, DraftSpec


async def draft_bullets(state: GraphState, deps: Deps) -> GraphState:
    """Draft tailored bullets from covered requirements, then grounding-check them.

    After a "revise" review, the previous draft and the feedback are added to the prompt.
    """
    evidence = evidence_map(state)
    system = prompts.DRAFT_SYSTEM
    user = prompts.draft_user(state["analysis"], state["requirements"], state["matches"], evidence)
    previous, feedback = state.get("draft"), state.get("feedback", "")
    if previous and feedback:
        system += "\n\n" + prompts.REVISE_SYSTEM
        user += "\n\n" + prompts.revise_user(previous, feedback)

    draft: DraftSpec = await deps.llm.with_structured_output(DraftSpec).ainvoke(
        [SystemMessage(system), HumanMessage(user)]
    )
    bullets, dropped = check_draft(draft.bullets, evidence, {r.id for r in state["requirements"]})
    return {
        "draft": Draft(
            summary=draft.summary,
            bullets=bullets,
            warnings=dropped + check_summary(draft.summary, evidence),
            revision=previous.revision + 1 if previous else 1,
        ),
        "feedback": "",
    }
