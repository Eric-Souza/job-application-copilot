"""Usage counting from real chat-model callbacks, and tracing staying off without Langfuse keys."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.services import tracing
from app.services.tracing import UsageCounter


def _model(*usages: dict | None) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter(AIMessage(content="ok", usage_metadata=u) for u in usages))


async def test_counts_calls_and_tokens():
    model = _model(
        {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        {"input_tokens": 80, "output_tokens": 10, "total_tokens": 90},
    )
    usage = UsageCounter()

    await model.ainvoke("hi", config={"callbacks": [usage]})
    await model.ainvoke("again", config={"callbacks": [usage]})

    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (2, 200, 40)


async def test_a_model_that_reports_no_usage_still_counts_as_a_call():
    usage = UsageCounter()

    await _model(None).ainvoke("hi", config={"callbacks": [usage]})

    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (1, 0, 0)


async def test_without_langfuse_keys_only_usage_is_collected(monkeypatch):
    monkeypatch.setattr(tracing, "langfuse_client", lambda: None)

    with tracing.traced("run-1", "start") as trace:
        assert trace.callbacks == [trace.usage]
    assert await tracing.session_url("run-1") is None
