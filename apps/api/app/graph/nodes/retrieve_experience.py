from app.graph.state import Deps, GraphState
from app.schemas import EvidenceItem
from app.services.retrieval import Evidence


def pooled(pool: dict[str, EvidenceItem], hit: Evidence) -> EvidenceItem:
    """The pool's item for a search hit, adding it with the next id (E1, E2, ...) if it's new."""
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
    return item


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
        by_requirement[req.id] = [pooled(pool, hit).id for hit in hits]
    return {"evidence": list(pool.values()), "evidence_by_requirement": by_requirement}
