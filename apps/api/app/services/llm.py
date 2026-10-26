from functools import lru_cache

from langchain_core.exceptions import ModelAPIError
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.config import get_settings


def _require_key() -> str:
    settings = get_settings()
    if not settings.gemini_configured:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env at the repo root.")
    return settings.gemini_api_key


_TRANSIENT = ("429", "500", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")


def is_transient(exc: Exception) -> bool:
    """Errors worth retrying: overload (503), rate limits (429), and timeouts."""
    return any(marker in str(exc) for marker in _TRANSIENT)


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
    while the lite model (with a larger quota) keeps working. Nodes only call
    with_structured_output, so that's the only method this needs.
    """

    def __init__(self, primary, fallback=None):
        self.primary, self.fallback = primary, fallback

    def with_structured_output(self, schema):
        runnable = self.primary.with_structured_output(schema)
        if self.fallback is None:
            return runnable
        return runnable.with_fallbacks(
            [self.fallback.with_structured_output(schema)], exceptions_to_handle=(ModelAPIError,)
        )


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
