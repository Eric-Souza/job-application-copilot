"""The full graph with a fake LLM: routing, id handling, and validation of what the LLM returns."""

from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REPO_ROOT
from app.graph.builder import build_graph
from app.graph.state import Deps
from app.schemas import BulletSpec, DraftSpec, Match, MatchReport, PostingAnalysis, RequirementSpec
from app.services import ingest
from app.services.ingest import ingest_file
from app.services.retrieval import search_many
from tests.conftest import axis_vector
from tests.fakes import FakeLLM, evidence, fixed_search, memory_saver

ANALYSIS = PostingAnalysis(
    title="Senior Backend Engineer",
    company="Northwind",
    seniority="Senior",
    summary="Builds payment services.",
    requirements=[
        RequirementSpec(text="Go", kind="must", category="skill"),
        RequirementSpec(text="Kubernetes", kind="nice", category="skill"),
        RequirementSpec(text="go", kind="must", category="skill"),  # duplicate, different case
        RequirementSpec(text="Rust", kind="must", category="skill"),
    ],
)
HITS = {
    "Go": [evidence("c1", "Designed a payments API in Go."), evidence("c2", "Wrote Go CLIs.")],
    "Kubernetes": [evidence("c2", "Wrote Go CLIs."), evidence("c3", "Ran Kubernetes with Helm.")],
}


async def run(llm: FakeLLM, search=None):
    """Run the graph to the end, approving the draft if it pauses for review."""
    graph = build_graph(
        Deps(llm=llm, search=search or fixed_search(HITS), research_rounds=0), checkpointer=memory_saver()
    )
    config = {"configurable": {"thread_id": "test"}}
    state = await graph.ainvoke({"posting": "Senior Backend Engineer at Northwind..."}, config)
    if "__interrupt__" in state:
        state = await graph.ainvoke(Command(resume={"action": "approve"}), config)
    return state


def good_matches(_messages) -> MatchReport:
    return MatchReport(
        matches=[
            Match(requirement_id="R1", coverage="strong", evidence_ids=["E1", "E2"], rationale="Go APIs."),
            Match(requirement_id="R2", coverage="partial", evidence_ids=["E3"], rationale="Helm."),
            Match(requirement_id="R3", coverage="missing", evidence_ids=[], rationale="No Rust."),
        ]
    )


DRAFT = DraftSpec(
    summary="Backend engineer who builds payment APIs in Go.",
    bullets=[
        BulletSpec(text="Designed a Go payments API.", requirement_ids=["R1"], evidence_ids=["E1"]),
        BulletSpec(text="Ran Kubernetes with Helm.", requirement_ids=["R2"], evidence_ids=["E3"]),
    ],
)


async def test_happy_path_assigns_ids_pools_evidence_and_renders():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})

    state = await run(llm)

    assert [(r.id, r.text) for r in state["requirements"]] == [
        ("R1", "Go"),
        ("R2", "Kubernetes"),
        ("R3", "Rust"),
    ]
    # c2 is a hit for both requirements but appears once in the pool
    assert [e.chunk_id for e in state["evidence"]] == ["c1", "c2", "c3"]
    assert state["evidence_by_requirement"] == {"R1": ["E1", "E2"], "R2": ["E2", "E3"], "R3": []}
    assert [name for name, _ in llm.calls] == ["PostingAnalysis", "MatchReport", "DraftSpec"]

    result = state["result"]
    assert result.coverage == {"strong": 1, "partial": 1, "missing": 1}
    assert result.gaps == ["Rust"]
    assert len(result.bullets) == 2
    assert "| R3 | Rust | must | missing | - |" in result.markdown
    assert "## Gaps (must-haves with no evidence)\n\n- Rust" in result.markdown


async def test_match_prompt_lists_each_requirements_evidence():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})

    await run(llm)

    prompt = llm.calls[1][1][1].content
    assert (
        "R1 [must] Go\n  [E1] (Experience > Engineer · Acme | 2022 – 2024) Designed a payments API in Go."
        in prompt
    )
    assert "R3 [must] Rust\n  (no evidence found)" in prompt


async def test_draft_prompt_hides_gaps_from_covered_requirements():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})

    await run(llm)

    prompt = llm.calls[2][1][1].content
    covered, gaps = prompt.split("Gaps (don't claim these):")
    assert "R1 [must, strong] Go <- E1, E2" in covered
    assert "Rust" not in covered
    assert gaps.strip() == "- Rust"


async def test_draft_groups_evidence_and_bullets_by_role():
    hits = {
        "Go": [evidence("c1", "Designed a payments API in Go.", "Engineer · Acme | 2022 – 2024")],
        "Kubernetes": [evidence("c3", "Ran Kubernetes with Helm.", "SRE · Orbit | 2024 – now")],
    }
    draft = DraftSpec(
        summary="Backend engineer.",
        bullets=[
            BulletSpec(text="Ran Kubernetes with Helm.", requirement_ids=["R2"], evidence_ids=["E2"]),
            BulletSpec(text="Designed a Go payments API.", requirement_ids=["R1"], evidence_ids=["E1"]),
        ],
    )

    def matches(_messages):
        return MatchReport(
            matches=[
                Match(requirement_id="R1", coverage="strong", evidence_ids=["E1"], rationale="."),
                Match(requirement_id="R2", coverage="strong", evidence_ids=["E2"], rationale="."),
                Match(requirement_id="R3", coverage="missing", evidence_ids=[], rationale="."),
            ]
        )

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: matches, DraftSpec: draft})
    result = (await run(llm, search=fixed_search(hits)))["result"]

    prompt = llm.calls[2][1][1].content
    assert "### Engineer · Acme | 2022 – 2024\n[E1]" in prompt
    assert "### SRE · Orbit | 2024 – now\n[E2]" in prompt
    assert "### SRE · Orbit | 2024 – now\n\n- Ran Kubernetes with Helm." in result.markdown
    assert "### Engineer · Acme | 2022 – 2024\n\n- Designed a Go payments API." in result.markdown


async def test_invalid_llm_matches_are_corrected():
    def sloppy(_messages):
        return MatchReport(
            matches=[
                Match(requirement_id="R1", coverage="strong", evidence_ids=["E1", "E99"], rationale="."),
                Match(requirement_id="R1", coverage="missing", evidence_ids=[], rationale="repeat"),
                Match(requirement_id="R2", coverage="strong", evidence_ids=["E42"], rationale="."),
                # R3 is never assessed
            ]
        )

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: sloppy, DraftSpec: DRAFT})
    state = await run(llm)

    by_req = {m.requirement_id: m for m in state["matches"]}
    assert (by_req["R1"].coverage, by_req["R1"].evidence_ids) == ("strong", ["E1"])
    assert by_req["R2"].coverage == "missing"
    assert by_req["R3"].coverage == "missing"
    assert state["result"].warnings[:2] == [
        "R2 was marked strong without valid evidence; marked missing.",
        "R3 wasn't assessed by the model; marked missing.",
    ]


async def test_nothing_covered_skips_drafting():
    def none_covered(_messages):
        return MatchReport(
            matches=[
                Match(requirement_id=f"R{i}", coverage="missing", evidence_ids=[], rationale=".")
                for i in (1, 2, 3)
            ]
        )

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: none_covered})
    state = await run(llm)

    assert [name for name, _ in llm.calls] == ["PostingAnalysis", "MatchReport"]
    assert state["result"].bullets == []
    assert state["result"].gaps == ["Go", "Rust"]


async def test_ungrounded_draft_is_checked_before_finalize():
    draft = DraftSpec(
        summary="Engineer with 12 years of Go.",
        bullets=[
            BulletSpec(
                text="Designed a Go payments API used by 5,000 merchants.",
                requirement_ids=["R1"],
                evidence_ids=["E1"],
            ),
            BulletSpec(text="Shipped Rust services.", requirement_ids=["R3"], evidence_ids=["E50"]),
        ],
    )
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: draft})
    result = (await run(llm))["result"]

    assert [b.text for b in result.bullets] == ["Designed a Go payments API used by 5,000 merchants."]
    assert result.bullets[0].flags == ["numbers not in the cited evidence: 5000"]
    assert "Dropped a bullet (no valid evidence): 'Shipped Rust services.'" in result.warnings
    assert "The summary has numbers not in the evidence: 12" in result.warnings
    assert "  - Check: numbers not in the cited evidence: 5000" in result.markdown


async def test_runs_against_the_real_index(db: AsyncSession, monkeypatch):
    """Retrieval through Postgres (keyword mode, so no embeddings are needed at query time)."""

    async def fake_embed(texts):
        return [axis_vector((0, 1.0)) for _ in texts]

    monkeypatch.setattr(ingest, "embed_documents", fake_embed)
    await ingest_file(db, REPO_ROOT / "data" / "samples" / "sample-resume.md")

    async def keyword_search(queries, k):
        return await search_many(db, queries, k=k, mode="keyword")

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    state = await run(llm, search=keyword_search)

    go_evidence = [e.content for e in state["evidence"] if e.id in state["evidence_by_requirement"]["R1"]]
    assert any("payments API in Go" in c for c in go_evidence)
    assert state["evidence_by_requirement"]["R3"] == []  # no Rust in the sample resume


async def test_transient_llm_errors_are_retried(monkeypatch):
    from app.graph import builder

    monkeypatch.setattr(builder, "LLM_RETRY", builder.LLM_RETRY._replace(initial_interval=0.01))
    attempts = []

    def flaky(_messages):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")
        return good_matches(_messages)

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: flaky, DraftSpec: DRAFT})
    state = await run(llm)

    assert len(attempts) == 2
    assert state["result"].coverage["strong"] == 1


def test_only_transient_errors_count():
    from app.services.llm import is_transient

    assert is_transient(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert not is_transient(ValueError("Invalid JSON in structured output"))
