import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def source_id_for(filename: str) -> str:
    """Stable id per file name, so re-ingesting a file replaces its chunks."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"copilot-source:{filename}"))


class Source(Base):
    """One ingested file: a resume, a project write-up, an article."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    # sha256 of the file, so unchanged files aren't re-embedded
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Run(Base):
    """One tailoring run. The graph state lives in LangGraph's checkpoint tables under the same id;
    this row is what lists and status checks read."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # running | awaiting_review | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")  # set once the posting is parsed
    company: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    # Usage across all segments: model calls, tokens, and time spent running (not waiting for review)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    work_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ExperienceChunk(Base):
    """One piece of evidence (usually a single resume bullet) plus where it came from."""

    __tablename__ = "experience_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Top-level resume section, e.g. "Experience" or "Technical Skills"
    section: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # Heading path above the chunk, e.g. "Senior Engineer · Acme (2022 – 2024)"
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Just the heading path (the role), without description lines; empty for top-level bullets
    heading: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(get_settings().embed_dim), nullable=False)
    # Context is searchable too: a bullet about "clinical reports" should match "healthcare"
    tsv = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', context || ' ' || content)", persisted=True)
    )

    __table_args__ = (
        Index("ix_experience_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_experience_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
