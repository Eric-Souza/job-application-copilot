from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.graph import prompts
from app.graph.nodes.retrieve_experience import pooled
from app.graph.state import Deps, GraphState, evidence_map
from app.schemas import Requirement, Search, SearchExperience

MAX_SEARCHES_PER_TURN = 8


def weak_requirements(state: GraphState) -> list[Requirement]:
    """Requirements the first search didn't cover strongly: worth another look in other words."""
    coverage = {m.requirement_id: m.coverage for m in state["matches"]}
    return [r for r in state["requirements"] if coverage.get(r.id) != "strong"]


async def research_gaps(state: GraphState, deps: Deps) -> GraphState:
    """Let the model search the experience index itself for weakly covered requirements.

    The first search used each requirement's own words, and resumes often say the same thing
    differently (a related tool, the task instead of the skill, the domain in a job title).
    The model gets a search tool and up to `research_rounds` turns: it calls the tool, sees
    the results, and can try again. New hits join the evidence pool, and match_requirements
    judges again with them. The model never decides coverage here, it only finds evidence.
    """
    weak = {r.id: r for r in weak_requirements(state)}
    pool = {e.chunk_id: e for e in state["evidence"]}
    by_requirement = {req: list(ids) for req, ids in state["evidence_by_requirement"].items()}
    searches: list[Search] = []

    model = deps.llm.bind_tools([SearchExperience])
    messages: list[BaseMessage] = [
        SystemMessage(prompts.RESEARCH_SYSTEM),
        HumanMessage(prompts.research_user(list(weak.values()), state["matches"], evidence_map(state))),
    ]
    for _ in range(deps.research_rounds):
        reply = await model.ainvoke(messages)
        if not reply.tool_calls:
            break
        messages.append(reply)

        answers: dict[str, str] = {}  # tool call id -> what the model is told
        valid: list[tuple[str, str, str]] = []  # (call id, requirement id, query)
        for call in reply.tool_calls:
            req_id, query = _arguments(call["args"])
            if len(valid) >= MAX_SEARCHES_PER_TURN:
                answers[call["id"]] = f"Skipped: at most {MAX_SEARCHES_PER_TURN} searches at a time."
            elif req_id not in weak:
                answers[call["id"]] = f"Unknown requirement {req_id!r}. Search for one of: {', '.join(weak)}."
            elif not query:
                answers[call["id"]] = "The query is empty."
            else:
                valid.append((call["id"], req_id, query))

        # One batched search (one embedding request) for the whole turn
        results = await deps.search([q for _, _, q in valid], deps.evidence_per_requirement) if valid else []
        for (call_id, req_id, query), hits in zip(valid, results, strict=True):
            linked = by_requirement.setdefault(req_id, [])
            found = []
            for hit in hits:
                item = pooled(pool, hit)
                if item.id not in linked:
                    linked.append(item.id)
                    found.append(item.id)
            searches.append(Search(requirement_id=req_id, query=query, found=found))
            lines = [pool[h.chunk_id].prompt_line() for h in hits]
            answers[call_id] = "\n".join(lines) or "No results."
        # Every call gets an answer, in order: the model API rejects a turn with one missing
        messages += [
            ToolMessage(answers[c["id"]], tool_call_id=c["id"], name=c["name"]) for c in reply.tool_calls
        ]

    return {"evidence": list(pool.values()), "evidence_by_requirement": by_requirement, "searches": searches}


def _arguments(args: dict[str, Any]) -> tuple[str, str]:
    return str(args.get("requirement_id", "")).strip(), str(args.get("query", "")).strip()
