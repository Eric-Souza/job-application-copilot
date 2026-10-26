from langchain_core.messages import HumanMessage, SystemMessage

from app.graph import prompts
from app.graph.state import Deps, GraphState, evidence_map
from app.schemas import Match, MatchReport


async def match_requirements(state: GraphState, deps: Deps) -> GraphState:
    """Judge coverage per requirement, then make the LLM's answer consistent with the data."""
    requirements = state["requirements"]
    evidence = evidence_map(state)
    report: MatchReport = await deps.llm.with_structured_output(MatchReport).ainvoke(
        [
            SystemMessage(prompts.MATCH_SYSTEM),
            HumanMessage(prompts.match_user(requirements, state["evidence_by_requirement"], evidence)),
        ]
    )

    by_req: dict[str, Match] = {}
    for m in report.matches:
        by_req.setdefault(m.requirement_id, m)  # keep the first if one is repeated

    matches, warnings = [], []
    for r in requirements:
        m = by_req.get(r.id)
        if m is None:
            warnings.append(f"{r.id} wasn't assessed by the model; marked missing.")
            m = Match(requirement_id=r.id, coverage="missing", evidence_ids=[], rationale="Not assessed.")
        valid = [e for e in dict.fromkeys(m.evidence_ids) if e in evidence]
        if m.coverage != "missing" and not valid:
            warnings.append(f"{r.id} was marked {m.coverage} without valid evidence; marked missing.")
            m = m.model_copy(update={"coverage": "missing"})
        matches.append(m.model_copy(update={"evidence_ids": valid}))
    return {"matches": matches, "warnings": warnings}
