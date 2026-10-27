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
    # Model turns the agent may spend searching again for weakly covered requirements; 0 turns it off
    research_rounds: int = 2

    resume_dir: str = str(REPO_ROOT / "data" / "resume")
    # Optional: index the resume from the profile MCP server instead of resume_dir. A command
    # that starts it over stdio ("node ../profile-mcp-server/dist/index.js") or an http(s) URL
    profile_mcp: str = ""

    # Origins allowed to call the API from a browser (the Vite dev server by default)
    cors_origins: list[str] = ["http://localhost:5173"]

    # Langfuse tracing (optional): every run's steps, prompts, tokens and latency. Off when the keys are empty
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key.strip() and self.langfuse_secret_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
