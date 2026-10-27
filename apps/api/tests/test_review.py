"""Human review: the graph pauses on a draft, and approve / revise / edit route it from there."""

import uuid

import pytest
from langgraph.types import Command
from pydantic import ValidationError

from app.graph.builder import build_graph
from app.graph.checkpointer import postgres_checkpointer, serializer
from app.graph.state import Deps
from app.schemas import BulletSpec, Draft, DraftSpec, MatchReport, PostingAnalysis, ReviewDecision
from tests.fakes import FakeLLM, fixed_search, memory_saver
from tests.test_graph import ANALYSIS, DRAFT, HITS, good_matches

POSTING = {"posting": "Senior Backend Engineer at Northwind..."}


def drafts(*specs: DraftSpec):
    """A draft response per call: the first draft, then one per revision."""
    queue = list(specs)
    return lambda _messages: queue.pop(0)


def start(llm: FakeLLM, checkpointer=None):
    graph = build_graph(
        Deps(llm=llm, search=fixed_search(HITS), research_rounds=0),
        checkpointer=checkpointer or memory_saver(),
    )
    return graph, {"configurable": {"thread_id": str(uuid.uuid4())}}


def paused_on(state) -> dict:
    (pending,) = state["__interrupt__"]
    return pending.value


async def test_pauses_on_the_draft_until_reviewed():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph, config = start(llm)

    state = await graph.ainvoke(POSTING, config)

    assert "result" not in state
    request = paused_on(state)
    assert request["revision"] == 1
    assert request["summary"] == DRAFT.summary
    assert [b["text"] for b in request["bullets"]] == [b.text for b in DRAFT.bullets]
    assert [m["coverage"] for m in request["coverage"]] == ["strong", "partial", "missing"]
    assert [r["id"] for r in request["requirements"]] == ["R1", "R2", "R3"]
    assert {e["id"] for e in request["evidence"]} >= {e for b in DRAFT.bullets for e in b.evidence_ids}
    assert (await graph.aget_state(config)).next == ("human_review",)

    state = await graph.ainvoke(Command(resume={"action": "approve"}), config)
    assert [b.text for b in state["result"].bullets] == [b.text for b in DRAFT.bullets]


async def test_revise_redrafts_with_the_feedback_and_previous_draft():
    shorter = DraftSpec(
        summary="Go backend engineer.",
        bullets=[BulletSpec(text="Built a Go payments API.", requirement_ids=["R1"], evidence_ids=["E1"])],
    )
    first = DRAFT.model_copy(
        update={"bullets": DRAFT.bullets + [BulletSpec(text="Ghost.", requirement_ids=[], evidence_ids=[])]}
    )
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: drafts(first, shorter)})
    graph, config = start(llm)
    state = await graph.ainvoke(POSTING, config)
    assert paused_on(state)["warnings"] == ["Dropped a bullet (no valid evidence): 'Ghost.'"]

    state = await graph.ainvoke(Command(resume={"action": "revise", "feedback": "Only the Go work."}), config)

    request = paused_on(state)
    assert request["revision"] == 2
    assert [b["text"] for b in request["bullets"]] == ["Built a Go payments API."]
    assert request["warnings"] == []  # the first draft's warnings went with it
    system, user = llm.calls[-1][1]
    assert "asked for changes" in system.content
    assert "Your previous draft:\n\nSummary: Backend engineer who builds payment APIs in Go." in user.content
    assert "- Designed a Go payments API. (E1)" in user.content
    assert user.content.endswith("Reviewer feedback:\nOnly the Go work.")
    assert state["feedback"] == ""


async def test_edits_are_grounding_checked_and_reviewed_again():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph, config = start(llm)
    await graph.ainvoke(POSTING, config)

    edit = {
        "action": "edit",
        "summary": "Engineer with 9 years of Go.",
        "bullets": [
            {
                "text": "Designed a Go payments API for 300 banks.",
                "requirement_ids": ["R1"],
                "evidence_ids": ["E1"],
            },
            {"text": "Led a Rust rewrite.", "requirement_ids": ["R3"], "evidence_ids": []},
        ],
    }
    state = await graph.ainvoke(Command(resume=edit), config)

    request = paused_on(state)  # back to review, not finalized
    assert [b["text"] for b in request["bullets"]] == ["Designed a Go payments API for 300 banks."]
    assert request["bullets"][0]["flags"] == ["numbers not in the cited evidence: 300"]
    assert request["warnings"] == [
        "Dropped a bullet (no valid evidence): 'Led a Rust rewrite.'",
        "The summary has numbers not in the evidence: 9",
    ]
    assert len(llm.calls) == 3  # editing doesn't call the model

    result = (await graph.ainvoke(Command(resume={"action": "approve"}), config))["result"]
    assert result.summary == "Engineer with 9 years of Go."
    assert "  - Check: numbers not in the cited evidence: 300" in result.markdown


async def test_summary_only_edit_keeps_the_bullets():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph, config = start(llm)
    await graph.ainvoke(POSTING, config)

    state = await graph.ainvoke(Command(resume={"action": "edit", "summary": "Go engineer."}), config)

    request = paused_on(state)
    assert request["summary"] == "Go engineer."
    assert [b["text"] for b in request["bullets"]] == [b.text for b in DRAFT.bullets]


async def test_invalid_decision_asks_again_with_the_error():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph, config = start(llm)
    await graph.ainvoke(POSTING, config)

    state = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    request = paused_on(state)
    assert request["error"] == "Value error, revise needs feedback"
    assert request["summary"] == DRAFT.summary

    # The bad decision isn't replayed: the next one is used
    state = await graph.ainvoke(Command(resume={"action": "approve"}), config)
    assert "result" in state
    assert len(llm.calls) == 3


def test_decisions_need_what_their_action_uses():
    with pytest.raises(ValidationError, match="edit needs a summary or bullets"):
        ReviewDecision(action="edit")
    assert ReviewDecision(action="edit", bullets=[]).bullets == []  # removing every bullet is an edit


async def test_run_resumes_after_a_restart_from_postgres():
    """Pause with one checkpointer connection, then finish with a fresh graph and connection."""
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    async with postgres_checkpointer() as saver:
        graph, config = start(llm, saver)
        await graph.ainvoke(POSTING, config)

    async with postgres_checkpointer() as saver:
        graph, _ = start(FakeLLM({}), saver)  # a new process: nothing in memory
        snapshot = await graph.aget_state(config)
        assert snapshot.next == ("human_review",)
        assert isinstance(snapshot.values["draft"], Draft)  # Pydantic models survive the round trip
        state = await graph.ainvoke(Command(resume={"action": "approve"}), config)

    assert state["result"].coverage == {"strong": 1, "partial": 1, "missing": 1}


def test_serializer_allows_every_state_model():
    serde = serializer()
    draft = Draft(summary="s", bullets=[], warnings=["w"], revision=2)
    assert serde.loads_typed(serde.dumps_typed({"draft": draft}))["draft"] == draft
    for cls in (ANALYSIS, *DRAFT.bullets):
        assert serde.loads_typed(serde.dumps_typed(cls)) == cls
