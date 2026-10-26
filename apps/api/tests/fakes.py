from collections.abc import Callable
from typing import Any

from app.services.retrieval import Evidence


class FakeLLM:
    """Stands in for a chat model: returns a canned response per structured-output schema.

    A response can be a model instance or a function of the prompt messages. Every call is
    recorded as (schema name, messages), so tests can check what the graph sent.
    """

    def __init__(self, responses: dict[type, Any | Callable[[list], Any]]):
        self.responses = responses
        self.calls: list[tuple[str, list]] = []

    def with_structured_output(self, schema: type) -> "_Structured":
        return _Structured(self, schema)


class _Structured:
    def __init__(self, llm: FakeLLM, schema: type):
        self.llm, self.schema = llm, schema

    async def ainvoke(self, messages: list) -> Any:
        self.llm.calls.append((self.schema.__name__, messages))
        response = self.llm.responses[self.schema]
        return response(messages) if callable(response) else response


def evidence(chunk_id: str, content: str, context: str = "Engineer · Acme | 2022 – 2024") -> Evidence:
    return Evidence(
        chunk_id=chunk_id,
        filename="resume.md",
        section="Experience",
        context=context,
        heading=context,
        content=content,
        scores={"rrf": 0.03},
    )


def fixed_search(results: dict[str, list[Evidence]]):
    """A search function that returns canned hits per query (none for unknown queries)."""
    calls: list[list[str]] = []

    async def search(queries: list[str], k: int) -> list[list[Evidence]]:
        calls.append(list(queries))
        return [results.get(q, [])[:k] for q in queries]

    search.calls = calls  # type: ignore[attr-defined]
    return search
