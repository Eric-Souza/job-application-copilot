import logging
import re
import time
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.config import get_settings

log = logging.getLogger(__name__)


def _require_key() -> str:
    settings = get_settings()
    if not settings.gemini_configured:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env at the repo root.")
    return settings.gemini_api_key


# Errors another model might not hit: overload, its own quota, timeouts. Auth and bad-request
# errors would fail on the fallback too, so they surface instead.
FALLBACK_ON = (ModelAPIError, ModelRateLimitError, ModelTimeoutError, ModelConnectionError)

_TRANSIENT = ("429", "500", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")


def is_transient(exc: Exception) -> bool:
    """Errors worth retrying: overload (503), rate limits (429), and timeouts."""
    return any(marker in str(exc) for marker in _TRANSIENT)


_RETRY_DELAY = re.compile(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s")


def daily_quota_reset(exc: BaseException) -> float | None:
    """Seconds until a used-up daily quota resets, or None if this isn't a daily-quota error.

    Gemini's 429 names the quota (e.g. GenerateRequestsPerDayPerProjectPerModel-FreeTier) and
    says when to retry. Per-minute limits clear on their own, so they don't count.
    """
    text = str(exc)
    if "RESOURCE_EXHAUSTED" not in text or "PerDay" not in text:
        return None
    match = _RETRY_DELAY.search(text)
    return float(match.group(1)) if match else 3600.0


@lru_cache
def get_chat_model(model: str | None = None) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model or get_settings().gemini_chat_model,
        google_api_key=_require_key(),
        # Fail fast inside the client; the graph's RetryPolicy retries whole nodes with backoff
        max_retries=1,
    )


class ChatWithFallback:
    """The main chat model, falling back to a lighter one when Gemini errors.

    The free tier's flash model regularly answers 503 "high demand" for minutes at a time,
    while the lite model (with a larger quota) keeps working. Once the main model's daily quota
    is used up, it's skipped until the quota resets instead of failing first on every call.
    Nodes only call with_structured_output and bind_tools, so those are the methods this needs.
    """

    def __init__(self, primary, fallback=None, clock=time.monotonic):
        self.primary, self.fallback, self.clock = primary, fallback, clock
        self.primary_resumes_at = 0.0  # clock time; the main model is skipped until then

    def with_structured_output(self, schema):
        return self._wrap(lambda model: model.with_structured_output(schema))

    def bind_tools(self, tools):
        return self._wrap(lambda model: model.bind_tools(tools))

    def _wrap(self, make):
        runnable = make(self.primary)
        if self.fallback is None:
            return runnable
        fallback = make(self.fallback)
        if self.clock() < self.primary_resumes_at:
            return fallback
        watched = runnable.with_config(callbacks=[_QuotaWatcher(self)])
        return watched.with_fallbacks([fallback], exceptions_to_handle=FALLBACK_ON)

    def skip_primary(self, seconds: float) -> None:
        if self.clock() >= self.primary_resumes_at:
            hours, minutes = divmod(round(seconds / 60), 60)
            log.warning(
                "The main model's daily quota is used up; using the fallback for %dh %dm", hours, minutes
            )
        self.primary_resumes_at = max(self.primary_resumes_at, self.clock() + seconds)


class _QuotaWatcher(BaseCallbackHandler):
    """Sees the main model's errors (before the fallback hides them) and spots a used-up daily quota."""

    run_inline = True

    def __init__(self, llm: ChatWithFallback):
        self.llm = llm

    def _check(self, error: BaseException) -> None:
        if (seconds := daily_quota_reset(error)) is not None:
            self.llm.skip_primary(seconds)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self._check(error)

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        self._check(error)


def get_agent_llm() -> ChatWithFallback:
    settings = get_settings()
    fallback = settings.gemini_fallback_model
    return ChatWithFallback(get_chat_model(), get_chat_model(fallback) if fallback else None)


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=settings.gemini_embed_model.removeprefix("models/"),
        google_api_key=_require_key(),
        output_dimensionality=settings.embed_dim,
    )


async def embed_documents(texts: list[str]) -> list[list[float]]:
    return await get_embeddings().aembed_documents(texts, task_type="RETRIEVAL_DOCUMENT")


async def embed_queries(texts: list[str]) -> list[list[float]]:
    """Embed several queries in one batched request (one per job requirement, for example)."""
    if not texts:
        return []
    return await get_embeddings().aembed_documents(texts, task_type="RETRIEVAL_QUERY")
