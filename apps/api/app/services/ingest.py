"""Index resume files into pgvector: chunk, embed, and replace the file's previous chunks."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExperienceChunk, Source, source_id_for
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
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    source_id = source_id_for(path.name)
    source = await db.get(Source, source_id)
    if source and source.content_hash == content_hash and not force:
        return IngestResult(path.name, source.chunk_count, skipped=True)

    chunks = load_chunks(path)
    if not chunks:
        raise ValueError(f"No text found in {path.name}")
    embeddings = await embed_documents([c.embed_text for c in chunks])

    if source is None:
        source = Source(id=source_id, filename=path.name, content_hash=content_hash)
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
            content=c.content,
            embedding=e,
        )
        for i, (c, e) in enumerate(zip(chunks, embeddings, strict=True))
    )
    await db.commit()
    return IngestResult(path.name, len(chunks), skipped=False)


async def remove_missing(db: AsyncSession, keep: list[Path]) -> list[str]:
    """Delete sources whose files are gone, so a removed write-up stops showing up as evidence."""
    names = {p.name for p in keep}
    stale = [s for s in (await db.execute(select(Source))).scalars() if s.filename not in names]
    for s in stale:
        await db.delete(s)
    await db.commit()
    return [s.filename for s in stale]
