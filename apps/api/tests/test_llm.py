import pytest
from langchain_core.runnables import RunnableLambda
from langchain_google_genai.chat_models import GoogleAPIError, GoogleRateLimitError

from app.services.llm import ChatWithFallback, daily_quota_reset


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


# Gemini's daily-quota 429, trimmed
DAILY_QUOTA = (
    "Error calling model 'gemini-3.6-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
    "{'error': {'code': 429, 'message': 'You exceeded your current quota. Please retry in 10h2m43s.', "
    "'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{"
    "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20'}]}, "
    "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '36163s'}]}}"
)
PER_MINUTE = DAILY_QUOTA.replace("PerDay", "PerMinute").replace("36163s", "20s")


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_daily_quota_errors_say_when_they_reset():
    assert daily_quota_reset(GoogleRateLimitError(DAILY_QUOTA)) == 36163
    assert daily_quota_reset(GoogleRateLimitError(PER_MINUTE)) is None
    assert daily_quota_reset(KeyError("unrelated")) is None


async def test_skips_the_main_model_until_its_daily_quota_resets():
    calls = []

    def exhausted(_):
        calls.append("main")
        raise GoogleRateLimitError(DAILY_QUOTA)

    clock = _Clock()
    llm = ChatWithFallback(_Model(exhausted), _Model(lambda _: "from fallback"), clock=clock)

    assert await llm.with_structured_output(dict).ainvoke("hi") == "from fallback"
    assert await llm.with_structured_output(dict).ainvoke("again") == "from fallback"
    assert calls == ["main"]  # the second call went straight to the fallback

    clock.now += 36163
    await llm.with_structured_output(dict).ainvoke("next day")
    assert calls == ["main", "main"]


async def test_a_per_minute_limit_does_not_skip_the_main_model():
    calls = []

    def limited(_):
        calls.append("main")
        raise GoogleRateLimitError(PER_MINUTE)

    llm = ChatWithFallback(_Model(limited), _Model(lambda _: "from fallback"), clock=_Clock())

    await llm.with_structured_output(dict).ainvoke("hi")
    await llm.with_structured_output(dict).ainvoke("again")
    assert calls == ["main", "main"]
