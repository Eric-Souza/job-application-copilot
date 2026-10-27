from collections.abc import AsyncIterator, Callable
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

    def with_structured_output(self, schema: type | dict, **kwargs: Any) -> "_Structured":
        if isinstance(schema, dict):  # a JSON schema: answers with the response's dict, like Gemini
            model = next(k for k in self.responses if getattr(k, "__name__", "") == schema["title"])
            return _Structured(self, model, schema["title"], as_dict=True)
        return _Structured(self, schema, schema.__name__)

    def bind_tools(self, tools: list) -> "_Structured":
        """Tool-calling turns answer with responses["tools"] (recorded in calls as "tools"): an
        AIMessage, or a function of the messages returning one. Without it, no tools are called."""
        return _Structured(self, "tools", "tools")


class _Structured:
    def __init__(self, llm: FakeLLM, key: Any, name: str, as_dict: bool = False):
        self.llm, self.key, self.name, self.as_dict = llm, key, name, as_dict

    async def ainvoke(self, messages: list) -> Any:
        self.llm.calls.append((self.name, list(messages)))
        callbacks = AsyncCallbackManager.configure(ensure_config().get("callbacks"))
        (run,) = await callbacks.on_chat_model_start({"name": "fake"}, [convert_to_messages(messages)])
        if self.key == "tools" and "tools" not in self.llm.responses:
            result = AIMessage(content="done")
        else:
            response = self.llm.responses[self.key]
            result = response(messages) if callable(response) else response
        message = AIMessage(content="", usage_metadata=FakeLLM.USAGE)
        await run.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))
        return result.model_dump() if self.as_dict else result

    async def astream(self, messages: list) -> AsyncIterator[Any]:
        """The response in two chunks, like a stream: half of its first field, then all of it."""
        result = await self.ainvoke(messages)
        if isinstance(result, dict) and result:
            key, value = next(iter(result.items()))
            yield {key: value[: len(value) // 2] if isinstance(value, str) else value}
        yield result


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
