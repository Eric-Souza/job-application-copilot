"""Retrieval against real Postgres, with hand-made embeddings so rankings are predictable."""

import pytest

from app.models import ExperienceChunk, Source, source_id_for
from app.services import retrieval
from app.services.retrieval import search_experience, search_many
from app.services.retrieval.search import keyword_search, vector_search
from tests.conftest import axis_vector

# axis 0 = "frontend", axis 1 = "payments", axis 2 = "infrastructure"
ROWS = [
    (
        "Experience",
        "Frontend Engineer · Shopfront",
        "Built a checkout UI in React and TypeScript.",
        [(0, 1.0)],
    ),
    (
        "Experience",
        "Backend Engineer · Paylane (fintech)",
        "Designed an idempotent payments API in Go.",
        [(1, 1.0)],
    ),
    (
        "Experience",
        "Platform Engineer · Clinico (healthcare)",
        "Ran Kubernetes clusters with Helm and Terraform.",
        [(2, 1.0), (1, 0.2)],
    ),
    ("Technical Skills", "", "Infrastructure: AWS, Kubernetes, Docker", [(2, 0.9), (0, 0.3)]),
]


@pytest.fixture
async def indexed(db):
    sid = source_id_for("resume.md")
    db.add(Source(id=sid, filename="resume.md", content_hash="x", chunk_count=len(ROWS)))
    await db.flush()
    db.add_all(
        ExperienceChunk(
            id=f"{sid}_{i}",
            source_id=sid,
            chunk_index=i,
            section=section,
            context=context,
            content=content,
            embedding=axis_vector(*axes),
        )
        for i, (section, context, content, axes) in enumerate(ROWS)
    )
    await db.commit()
    return db


async def test_vector_search_ranks_by_cosine(indexed):
    results = await vector_search(indexed, axis_vector((2, 1.0)), limit=2)

    assert [r.content for r in results] == [ROWS[2][2], ROWS[3][2]]
    assert results[0].filename == "resume.md"
    assert results[0].scores["vector"] > results[1].scores["vector"]


async def test_keyword_search_matches_on_context(indexed):
    # "healthcare" only appears in the role heading, never in a bullet
    results = await keyword_search(indexed, "experience in healthcare", limit=5)

    assert [r.content for r in results] == [ROWS[2][2]]


async def test_keyword_search_ors_terms_instead_of_requiring_all(indexed):
    results = await keyword_search(indexed, "Kubernetes and a payments background", limit=5)

    assert {r.content for r in results} == {ROWS[1][2], ROWS[2][2], ROWS[3][2]}


async def test_hybrid_rewards_chunks_found_by_both(indexed, monkeypatch):
    async def fake_embed(texts):
        return [axis_vector((2, 1.0)) for _ in texts]

    monkeypatch.setattr(retrieval, "embed_queries", fake_embed)
    results = await search_experience(indexed, "Terraform", k=3, mode="hybrid")

    # Only the Clinico bullet mentions Terraform, and it's also the closest vector
    assert results[0].content == ROWS[2][2]
    assert {"vector", "keyword", "rrf"} <= results[0].scores.keys()
    assert "keyword" not in results[1].scores


async def test_search_many_embeds_all_queries_in_one_call(indexed, monkeypatch):
    calls = []

    async def fake_embed(texts):
        calls.append(list(texts))
        return [axis_vector((0, 1.0)), axis_vector((1, 1.0))]

    monkeypatch.setattr(retrieval, "embed_queries", fake_embed)
    results = await search_many(indexed, ["React UI", "payments"], k=1, mode="vector")

    assert calls == [["React UI", "payments"]]
    assert [r[0].content for r in results] == [ROWS[0][2], ROWS[1][2]]


async def test_unknown_mode_is_rejected(indexed):
    with pytest.raises(ValueError, match="Unknown retrieval mode"):
        await search_experience(indexed, "x", mode="rerank")
