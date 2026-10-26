from sqlalchemy import Select, column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExperienceChunk, Source
from app.services.retrieval.types import Evidence


def _base(*extra) -> Select:
    return select(ExperienceChunk, Source.filename, *extra).join(
        Source, Source.id == ExperienceChunk.source_id
    )


def _to_evidence(chunk: ExperienceChunk, filename: str, scores: dict[str, float]) -> Evidence:
    return Evidence(
        chunk_id=chunk.id,
        filename=filename,
        section=chunk.section,
        context=chunk.context,
        content=chunk.content,
        scores=scores,
    )


async def vector_search(db: AsyncSession, query_embedding: list[float], limit: int) -> list[Evidence]:
    """Nearest chunks by cosine distance (HNSW index)."""
    distance = ExperienceChunk.embedding.cosine_distance(query_embedding)
    rows = (await db.execute(_base(distance.label("distance")).order_by(distance).limit(limit))).all()
    return [_to_evidence(c, f, {"vector": 1.0 - float(d)}) for c, f, d in rows]


def or_tsquery(query: str):
    """OR the query's lexemes, parsed exactly like the chunks were.

    websearch_to_tsquery ANDs every term, so a full requirement like "5+ years building
    REST APIs in Python" would only match a chunk containing all of those words.
    Running the query through to_tsvector('english', ...) gives the same stemming and
    stopwords as the chunks, and ts_rank_cd ranks chunks sharing more lexemes higher.
    """
    lexemes = func.unnest(func.to_tsvector("english", query)).table_valued("lexeme", "positions", "weights")
    return (
        select(
            func.to_tsquery(
                "simple",
                func.coalesce(func.string_agg(func.quote_literal(column("lexeme")), " | "), ""),
            )
        )
        .select_from(lexemes)
        .scalar_subquery()
    )


async def keyword_search(db: AsyncSession, query: str, limit: int) -> list[Evidence]:
    """Postgres full-text search over the generated tsvector column."""
    if not query.strip():
        return []
    tsquery = or_tsquery(query)
    rank = func.ts_rank_cd(ExperienceChunk.tsv, tsquery)
    stmt = (
        _base(rank.label("rank"))
        .where(ExperienceChunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [_to_evidence(c, f, {"keyword": float(r)}) for c, f, r in rows]


def reciprocal_rank_fusion(result_lists: list[list[Evidence]], k: int = 60) -> list[Evidence]:
    """Merge ranked lists with Reciprocal Rank Fusion: score = sum(1 / (k + rank)).

    RRF only uses ranks, so it combines cosine similarity and ts_rank_cd without
    normalizing their different scales.
    """
    fused: dict[str, Evidence] = {}
    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            merged = fused.get(item.chunk_id)
            if merged is None:
                merged = Evidence(
                    chunk_id=item.chunk_id,
                    filename=item.filename,
                    section=item.section,
                    context=item.context,
                    content=item.content,
                    scores={"rrf": 0.0},
                )
                fused[item.chunk_id] = merged
            merged.scores.update(item.scores)
            merged.scores["rrf"] += 1.0 / (k + rank)
    return sorted(fused.values(), key=lambda e: e.scores["rrf"], reverse=True)
