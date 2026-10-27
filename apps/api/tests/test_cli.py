"""The CLI's review loop: quitting saves the run, and resuming asks for the review straight away."""

import uuid

from app import cli
from app.graph.builder import build_graph
from app.graph.state import Deps
from app.schemas import DraftSpec, MatchReport, PostingAnalysis
from tests.fakes import FakeLLM, fixed_search, memory_saver
from tests.test_graph import ANALYSIS, DRAFT, HITS, good_matches


def answers(monkeypatch, *replies: str):
    queue = list(replies)
    monkeypatch.setattr("builtins.input", lambda _prompt="": queue.pop(0))
    return queue


async def test_quit_then_resume_and_approve(monkeypatch, capsys):
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph = build_graph(
        Deps(llm=llm, search=fixed_search(HITS), research_rounds=0), checkpointer=memory_saver()
    )
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    answers(monkeypatch, "q")
    assert await cli._drive(graph, config, {"posting": "..."}, auto_approve=False) is None
    assert "Draft 1" in capsys.readouterr().out

    answers(monkeypatch, "x", "a")  # an unknown choice asks again
    state = await cli._drive(graph, config, None, auto_approve=False, run=False)

    assert state["result"].bullets[0].text == DRAFT.bullets[0].text
    assert len(llm.calls) == 3  # resuming didn't rerun anything before the review


async def test_revise_asks_for_feedback(monkeypatch):
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph = build_graph(
        Deps(llm=llm, search=fixed_search(HITS), research_rounds=0), checkpointer=memory_saver()
    )
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    answers(monkeypatch, "r", "", "r", "Shorter, please.", "a")  # empty feedback is ignored
    state = await cli._drive(graph, config, {"posting": "..."}, auto_approve=False)

    assert state["draft"].revision == 2
    assert llm.calls[-1][1][1].content.endswith("Reviewer feedback:\nShorter, please.")


async def test_auto_approve_never_prompts(monkeypatch):
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})
    graph = build_graph(
        Deps(llm=llm, search=fixed_search(HITS), research_rounds=0), checkpointer=memory_saver()
    )
    answers(monkeypatch)  # any prompt would fail on an empty queue

    state = await cli._drive(graph, {"configurable": {"thread_id": "yes"}}, {"posting": "..."}, True)

    assert "result" in state
