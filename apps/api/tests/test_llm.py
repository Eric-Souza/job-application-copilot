import pytest
from langchain_core.runnables import RunnableLambda
from langchain_google_genai.chat_models import GoogleAPIError, GoogleRateLimitError

from app.services.llm import ChatWithFallback


class _Model:
    def __init__(self, fn):
        self.fn = fn

    def with_structured_output(self, schema):
        return RunnableLambda(self.fn)


def _overloaded(_):
    raise GoogleAPIError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "high demand"}})


async def test_falls_back_when_the_main_model_errors():
    llm = ChatWithFallback(_Model(_overloaded), _Model(lambda _: "from fallback"))

    assert await llm.with_structured_output(dict).ainvoke("hi") == "from fallback"


async def test_falls_back_when_the_main_models_quota_runs_out():
    def exhausted(_):
        raise GoogleRateLimitError("Error calling model 'gemini-3.6-flash' (RESOURCE_EXHAUSTED): 429")

    llm = ChatWithFallback(_Model(exhausted), _Model(lambda _: "from fallback"))

    assert await llm.with_structured_output(dict).ainvoke("hi") == "from fallback"


async def test_other_errors_are_not_hidden_by_the_fallback():
    def bug(_):
        raise KeyError("a bug in our code")

    llm = ChatWithFallback(_Model(bug), _Model(lambda _: "from fallback"))

    with pytest.raises(KeyError):
        await llm.with_structured_output(dict).ainvoke("hi")


async def test_no_fallback_configured():
    llm = ChatWithFallback(_Model(lambda _: "main"))

    assert await llm.with_structured_output(dict).ainvoke("hi") == "main"
