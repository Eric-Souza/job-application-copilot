from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# This file lives in apps/api/app/
API_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = API_ROOT.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(API_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.6-flash"
    # Used when the chat model errors (the free tier's flash model is often overloaded); "" disables
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    gemini_embed_model: str = "gemini-embedding-001"
    # gemini-embedding-001 supports reduced output sizes; 768 keeps the HNSW index small
    embed_dim: int = 768

    # Postgres + pgvector (docker-compose.yml at the repo root)
    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5435/copilot"

    # Retrieval: "vector", "keyword", or "hybrid" (both, merged with Reciprocal Rank Fusion)
    retrieval_mode: str = "hybrid"
    retrieval_candidates: int = 20
    rrf_k: int = 60

    resume_dir: str = str(REPO_ROOT / "data" / "resume")

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
