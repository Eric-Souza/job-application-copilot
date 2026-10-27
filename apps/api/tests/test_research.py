"""research_gaps: the model searches again, in its own words, for weakly covered requirements."""

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from app.graph.builder import build_graph
from app.graph.state import Deps
from app.schemas import DraftSpec, Match, MatchReport, PostingAnalysis, Search
from app.services.runs import describe
from tests.fakes import FakeLLM, evidence, fixed_search, memory_saver
from tests.test_graph import ANALYSIS, DRAFT, HITS, good_matches

RUST = evidence("c4", "Rewrote the parser in Rust.", context="Engineer · Initech | 2020 – 2022")


def call(id_: str, requirement_id: str, query: str) -> dict:
    return {"name": "SearchExperience", "args": {"requirement_id": requirement_id, "query": query}, "id": id_}


def turns(*replies: AIMessage):
    """A tools response that gives one reply per model turn, then "done"."""
    replies = list(replies)
    return lambda _messages: replies.pop(0) if replies else AIMessage(content="done")


async def run(llm: FakeLLM, hits=None, rounds: int = 2):
    search = fixed_search(hits or {**HITS, "systems programming": [RUST], "Helm charts": HITS["Kubernetes"]})
    graph = build_graph(Deps(llm=llm, search=search, research_rounds=rounds), checkpointer=memory_saver())
    config = {"configurable": {"thread_id": "test"}}
    state = await graph.ainvoke({"posting": "Senior Backend Engineer at Northwind..."}, config)
    if "__interrupt__" in state:
        state = await graph.ainvoke(Command(resume={"action": "approve"}), config)
    return state, search


def rematch(messages) -> MatchReport:
    """The second match sees the evidence research found, and uses it."""
    report = good_matches(messages)
    if "[E4]" in messages[-1].content:
        report.matches[2] = Match(
            requirement_id="R3", coverage="partial", evidence_ids=["E4"], rationale="Rust."
        )
    return report


async def test_new_evidence_is_pooled_and_matched_again():
    first = AIMessage(
        content="",
        tool_calls=[
            call("a", "R3", "systems programming"),
            call("b", "R9", "anything"),  # not a weak requirement
            call("c", "R2", "  "),
        ],
    )
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: rematch, DraftSpec: DRAFT, "tools": turns(first)})

    state, search = await run(llm)

    assert [name for name, _ in llm.calls] == [
        "PostingAnalysis",
        "MatchReport",
        "tools",
        "tools",
        "MatchReport",
        "DraftSpec",
    ]
    # Only the weak requirements (R2 partial, R3 missing) are offered, with what was found
    research_prompt = llm.calls[2][1][1].content
    assert "R2 [nice, partial] Kubernetes" in research_prompt and "R3 [must, missing] Rust" in research_prompt
    assert "R1" not in research_prompt
    # One batched search for the turn's valid calls
    assert search.calls[-1] == ["systems programming"]
    # Every call is answered, in order, so the model can correct itself on the next turn
    answers = [m for m in llm.calls[3][1] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in answers] == ["a", "b", "c"]
    assert "[E4]" in answers[0].content and "Rust" in answers[0].content
    assert answers[1].content.startswith("Unknown requirement 'R9'")
    assert answers[2].content == "The query is empty."

    assert state["searches"] == [Search(requirement_id="R3", query="systems programming", found=["E4"])]
    assert state["evidence_by_requirement"]["R3"] == ["E4"]
    assert [e.chunk_id for e in state["evidence"]] == ["c1", "c2", "c3", "c4"]
    assert state["result"].gaps == []  # Rust is partial now
    assert describe("research_gaps", state) == "1 search, 1 more piece of evidence"


async def test_searches_that_find_nothing_new_go_straight_to_drafting():
    # Helm charts finds c2 and c3, which R2 already has
    llm = FakeLLM(
        {
            PostingAnalysis: ANALYSIS,
            MatchReport: good_matches,
            DraftSpec: DRAFT,
            "tools": turns(AIMessage(content="", tool_calls=[call("a", "R2", "Helm charts")])),
        }
    )

    state, _ = await run(llm)

    assert [name for name, _ in llm.calls] == [
        "PostingAnalysis",
        "MatchReport",
        "tools",
        "tools",
        "DraftSpec",
    ]
    assert state["searches"] == [Search(requirement_id="R2", query="Helm charts", found=[])]
    assert state["result"].gaps == ["Rust"]


async def test_research_stops_after_its_rounds():
    def always(_messages):
        return AIMessage(content="", tool_calls=[call("a", "R3", "systems programming")])

    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: rematch, DraftSpec: DRAFT, "tools": always})

    state, _ = await run(llm, rounds=3)

    assert [name for name, _ in llm.calls].count("tools") == 3
    # The same search again finds nothing new for R3
    assert [s.found for s in state["searches"]] == [["E4"], [], []]


async def test_no_research_when_everything_is_strong():
    strong = MatchReport(
        matches=[
            Match(requirement_id=r, coverage="strong", evidence_ids=["E1"], rationale="Yes.")
            for r in ("R1", "R2", "R3")
        ]
    )
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: strong, DraftSpec: DRAFT})

    state, _ = await run(llm)

    assert "tools" not in [name for name, _ in llm.calls]
    assert "searches" not in state


async def test_a_model_that_wants_no_searches():
    llm = FakeLLM({PostingAnalysis: ANALYSIS, MatchReport: good_matches, DraftSpec: DRAFT})

    state, _ = await run(llm)

    assert [name for name, _ in llm.calls] == ["PostingAnalysis", "MatchReport", "tools", "DraftSpec"]
    assert state["searches"] == []
    assert describe("research_gaps", state) == "no searches needed"
