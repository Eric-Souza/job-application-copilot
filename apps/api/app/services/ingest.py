"""Index resume files, or the profile MCP server's resume, into pgvector: chunk, embed, replace old chunks."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ExperienceChunk, Source, source_id_for
from app.services import profile_mcp
from app.services.chunking import TextChunk, chunk_markdown, chunk_plain_text
from app.services.llm import embed_documents

SUPPORTED = {".md", ".markdown", ".txt", ".pdf"}


@dataclass
class IngestResult:
    filename: str
    chunks: int
    skipped: bool  # unchanged since the last ingest, so nothing was re-embedded


def load_chunks(path: Path) -> list[TextChunk]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return chunk_markdown(path.read_text(encoding="utf-8"))
    if suffix == ".pdf":
        text = "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return chunk_plain_text(text.strip(), label=path.stem)


def find_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED))
        elif p.suffix.lower() in SUPPORTED:
            files.append(p)
    # README files explain the folder, they aren't experience
    return [f for f in files if f.stem.lower() != "readme"]


async def ingest_file(db: AsyncSession, path: Path, force: bool = False) -> IngestResult:
    return await _ingest(db, path.name, path.read_bytes(), lambda: load_chunks(path), force)


async def ingest_markdown(db: AsyncSession, name: str, text: str, force: bool = False) -> IngestResult:
    """Index Markdown that didn't come from a file (the profile MCP server's resume)."""
    return await _ingest(db, name, text.encode("utf-8"), lambda: chunk_markdown(text), force)


async def ingest_configured(db: AsyncSession, force: bool = False) -> tuple[list[IngestResult], list[str]]:
    """Index the configured experience source and prune everything else.

    That's the resume from the profile MCP server when PROFILE_MCP is set, otherwise the
    files in data/resume/. Returns the results and the names of the removed sources.
    """
    settings = get_settings()
    if settings.profile_mcp.strip():
        text = await profile_mcp.read_resume(settings.profile_mcp.strip())
        results = [await ingest_markdown(db, profile_mcp.SOURCE_NAME, text, force=force)]
    else:
        files = find_files([Path(settings.resume_dir)])
        results = [await ingest_file(db, f, force=force) for f in files]
    return results, await remove_missing(db, [r.filename for r in results])


async def _ingest(
    db: AsyncSession, name: str, raw: bytes, load: Callable[[], list[TextChunk]], force: bool
) -> IngestResult:
    content_hash = hashlib.sha256(raw).hexdigest()
    source_id = source_id_for(name)
    source = await db.get(Source, source_id)
    if source and source.content_hash == content_hash and not force:
        return IngestResult(name, source.chunk_count, skipped=True)

    chunks = load()
    if not chunks:
        raise ValueError(f"No text found in {name}")
    embeddings = await embed_documents([c.embed_text for c in chunks])

    if source is None:
        source = Source(id=source_id, filename=name, content_hash=content_hash)
        db.add(source)
    source.content_hash = content_hash
    source.chunk_count = len(chunks)
    await db.flush()

    await db.execute(delete(ExperienceChunk).where(ExperienceChunk.source_id == source_id))
    db.add_all(
        ExperienceChunk(
            id=f"{source_id}_{i}",
            source_id=source_id,
            chunk_index=i,
            section=c.section,
            context=c.context,
            heading=c.heading,
            content=c.content,
            embedding=e,
        )
        for i, (c, e) in enumerate(zip(chunks, embeddings, strict=True))
    )
    await db.commit()
    return IngestResult(name, len(chunks), skipped=False)


async def remove_missing(db: AsyncSession, keep: list[str]) -> list[str]:
    """Delete sources not in `keep` (by name), so a removed write-up stops showing up as evidence."""
    names = set(keep)
    stale = [s for s in (await db.execute(select(Source))).scalars() if s.filename not in names]
    for s in stale:
        await db.delete(s)
    await db.commit()
    return [s.filename for s in stale]
