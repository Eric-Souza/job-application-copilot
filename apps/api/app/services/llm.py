from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.config import get_settings


def _require_key() -> str:
    settings = get_settings()
    if not settings.gemini_configured:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env at the repo root.")
    return settings.gemini_api_key


@lru_cache
def get_chat_model(model: str | None = None) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model or get_settings().gemini_chat_model,
        google_api_key=_require_key(),
        temperature=0.2,
    )


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
