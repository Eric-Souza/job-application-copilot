import operator
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app.schemas import Draft, EvidenceItem, Match, PostingAnalysis, Requirement, Search, TailoredResume
from app.services.retrieval import Evidence

SearchFn = Callable[[list[str], int], Awaitable[list[list[Evidence]]]]


class GraphState(TypedDict, total=False):
    posting: str
    analysis: PostingAnalysis
    requirements: list[Requirement]
    evidence: list[EvidenceItem]  # deduplicated pool, ids E1..En
    evidence_by_requirement: dict[str, list[str]]  # requirement id -> evidence ids, best first
    matches: list[Match]
    searches: list[Search]  # set once research_gaps has run, even if it searched nothing
    draft: Draft
    feedback: str  # the reviewer's last "revise" request, used by the next draft
    # Problems found while validating LLM output, shown to the user at the end
    warnings: Annotated[list[str], operator.add]
    result: TailoredResume


@dataclass
class Deps:
    """What the nodes need from outside the graph, injectable for tests."""

    llm: Any  # a LangChain chat model (anything with with_structured_output)
    search: SearchFn
    evidence_per_requirement: int = 4
    # Model turns research_gaps may spend calling the search tool; 0 skips the step
    research_rounds: int = 2


def evidence_map(state: GraphState) -> dict[str, EvidenceItem]:
    return {e.id: e for e in state.get("evidence", [])}
