"""Search the experience index: vector, keyword, or hybrid (both, merged with RRF)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.llm import embed_queries
from app.services.retrieval.search import keyword_search, reciprocal_rank_fusion, vector_search
from app.services.retrieval.types import Evidence

MODES = ("vector", "keyword", "hybrid")

__all__ = ["MODES", "Evidence", "search_experience", "search_many"]


async def _search(
    db: AsyncSession, query: str, embedding: list[float] | None, k: int, mode: str
) -> list[Evidence]:
    settings = get_settings()
    n = settings.retrieval_candidates
    if mode == "vector":
        return (await vector_search(db, embedding, k)) if embedding else []
    if mode == "keyword":
        return await keyword_search(db, query, k)
    lists = [await vector_search(db, embedding, n)] if embedding else []
    lists.append(await keyword_search(db, query, n))
    return reciprocal_rank_fusion(lists, k=settings.rrf_k)[:k]


async def search_many(
    db: AsyncSession, queries: list[str], k: int = 5, mode: str | None = None
) -> list[list[Evidence]]:
    """Search for several queries, with all their embeddings in one batched request."""
    mode = mode or get_settings().retrieval_mode
    if mode not in MODES:
        raise ValueError(f"Unknown retrieval mode {mode!r}; use one of {', '.join(MODES)}")
    embeddings = await embed_queries(queries) if mode != "keyword" else [None] * len(queries)
    return [await _search(db, q, e, k, mode) for q, e in zip(queries, embeddings, strict=True)]


async def search_experience(
    db: AsyncSession, query: str, k: int = 5, mode: str | None = None
) -> list[Evidence]:
    return (await search_many(db, [query], k=k, mode=mode))[0]
