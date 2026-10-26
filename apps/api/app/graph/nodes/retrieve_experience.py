from app.graph.state import Deps, GraphState
from app.schemas import EvidenceItem


async def retrieve_experience(state: GraphState, deps: Deps) -> GraphState:
    """Search the experience index once per requirement and pool the results.

    The same bullet often supports several requirements, so evidence is deduplicated
    into one pool with short ids (E1, E2, ...) that the LLM cites.
    """
    requirements = state["requirements"]
    results = await deps.search([r.text for r in requirements], deps.evidence_per_requirement)

    pool: dict[str, EvidenceItem] = {}  # chunk id -> item
    by_requirement: dict[str, list[str]] = {}
    for req, hits in zip(requirements, results, strict=True):
        ids = []
        for hit in hits:
            item = pool.get(hit.chunk_id)
            if item is None:
                item = EvidenceItem(
                    id=f"E{len(pool) + 1}",
                    chunk_id=hit.chunk_id,
                    section=hit.section,
                    context=hit.context,
                    heading=hit.heading,
                    content=hit.content,
                    score=hit.score,
                )
                pool[hit.chunk_id] = item
            ids.append(item.id)
        by_requirement[req.id] = ids
    return {"evidence": list(pool.values()), "evidence_by_requirement": by_requirement}
