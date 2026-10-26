"""Wire the nodes into a LangGraph StateGraph.

parse_posting -> retrieve_experience -> match_requirements -> draft_bullets -> finalize
                                                      \\________(nothing covered)______/
"""

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.db import AsyncSessionLocal
from app.graph.nodes import draft_bullets, finalize, match_requirements, parse_posting, retrieve_experience
from app.graph.state import Deps, GraphState
from app.services.llm import get_agent_llm, is_transient
from app.services.retrieval import search_many


async def search_index(queries: list[str], k: int):
    async with AsyncSessionLocal() as db:
        return await search_many(db, queries, k=k)


def default_deps() -> Deps:
    return Deps(llm=get_agent_llm(), search=search_index)


# Gemini's free tier returns 503 "high demand" now and then; waiting 10s, then 20s, usually clears it
LLM_RETRY = RetryPolicy(initial_interval=10, backoff_factor=2, max_attempts=3, retry_on=is_transient)


def after_match(state: GraphState) -> str:
    """Skip drafting when no requirement has any evidence: there's nothing honest to write."""
    if any(m.coverage != "missing" for m in state["matches"]):
        return "draft_bullets"
    return "finalize"


def build_graph(deps: Deps | None = None, checkpointer=None):
    deps = deps or default_deps()
    graph = StateGraph(GraphState)
    graph.add_node("parse_posting", partial(parse_posting, deps=deps), retry_policy=LLM_RETRY)
    graph.add_node("retrieve_experience", partial(retrieve_experience, deps=deps))
    graph.add_node("match_requirements", partial(match_requirements, deps=deps), retry_policy=LLM_RETRY)
    graph.add_node("draft_bullets", partial(draft_bullets, deps=deps), retry_policy=LLM_RETRY)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "parse_posting")
    graph.add_edge("parse_posting", "retrieve_experience")
    graph.add_edge("retrieve_experience", "match_requirements")
    graph.add_conditional_edges("match_requirements", after_match, ["draft_bullets", "finalize"])
    graph.add_edge("draft_bullets", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
