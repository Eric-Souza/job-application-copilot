from langchain_core.messages import HumanMessage, SystemMessage

from app.graph import prompts
from app.graph.state import Deps, GraphState
from app.schemas import PostingAnalysis, Requirement

MAX_REQUIREMENTS = 20


async def parse_posting(state: GraphState, deps: Deps) -> GraphState:
    """Turn the posting into structured requirements with stable ids."""
    analysis: PostingAnalysis = await deps.llm.with_structured_output(PostingAnalysis).ainvoke(
        [SystemMessage(prompts.PARSE_SYSTEM), HumanMessage(prompts.parse_user(state["posting"]))]
    )
    specs, seen = [], set()
    for r in analysis.requirements:
        key = r.text.strip().lower()
        if key and key not in seen:  # drop exact duplicates
            seen.add(key)
            specs.append(r)
    warnings = []
    if len(specs) > MAX_REQUIREMENTS:
        warnings.append(f"The posting has {len(specs)} requirements; kept the first {MAX_REQUIREMENTS}.")
        specs = specs[:MAX_REQUIREMENTS]
    requirements = [Requirement(id=f"R{i}", **s.model_dump()) for i, s in enumerate(specs, start=1)]
    return {"analysis": analysis, "requirements": requirements, "warnings": warnings}
