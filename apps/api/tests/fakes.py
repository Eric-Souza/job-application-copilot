from collections.abc import Callable
from typing import Any, ClassVar

from langchain_core.callbacks.manager import AsyncCallbackManager
from langchain_core.messages import AIMessage, convert_to_messages
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables.config import ensure_config
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.checkpointer import serializer
from app.services.retrieval import Evidence


class FakeLLM:
    """Stands in for a chat model: returns a canned response per structured-output schema.

    A response can be a model instance or a function of the prompt messages. Every call is
    recorded as (schema name, messages), so tests can check what the graph sent. Like a real chat
    model, each call reports its token usage to the callbacks in the current config.
    """

    USAGE: ClassVar[dict[str, int]] = {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200}

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
        callbacks = AsyncCallbackManager.configure(ensure_config().get("callbacks"))
        (run,) = await callbacks.on_chat_model_start({"name": "fake"}, [convert_to_messages(messages)])
        response = self.llm.responses[self.schema]
        result = response(messages) if callable(response) else response
        message = AIMessage(content="", usage_metadata=FakeLLM.USAGE)
        await run.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))
        return result


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


def memory_saver() -> InMemorySaver:
    """An in-memory checkpointer with the app's serializer, so state round-trips like in Postgres."""
    return InMemorySaver(serde=serializer())
