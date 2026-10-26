import shutil

import pytest
from sqlalchemy import func, select

from app.config import REPO_ROOT
from app.models import ExperienceChunk, Source
from app.services import ingest
from app.services.ingest import find_files, ingest_file, remove_missing
from tests.conftest import axis_vector

SAMPLE = REPO_ROOT / "data" / "samples" / "sample-resume.md"


@pytest.fixture
def embed_calls(monkeypatch):
    calls: list[int] = []

    async def fake_embed(texts):
        calls.append(len(texts))
        return [axis_vector((i % 8, 1.0)) for i in range(len(texts))]

    monkeypatch.setattr(ingest, "embed_documents", fake_embed)
    return calls


async def _chunk_count(db) -> int:
    return (await db.execute(select(func.count()).select_from(ExperienceChunk))).scalar_one()


async def test_ingest_indexes_every_chunk(db, embed_calls):
    result = await ingest_file(db, SAMPLE)

    assert (result.chunks, result.skipped) == (13, False)
    assert embed_calls == [13]
    assert await _chunk_count(db) == 13
    chunk = (
        await db.execute(
            select(ExperienceChunk).where(ExperienceChunk.content.like("Designed an idempotent%"))
        )
    ).scalar_one()
    assert chunk.section == "Experience"
    assert chunk.context == "Backend Engineer · Paylane (fintech) | Jan 2020 – Feb 2023"


async def test_unchanged_file_is_not_re_embedded(db, embed_calls):
    await ingest_file(db, SAMPLE)
    result = await ingest_file(db, SAMPLE)

    assert result.skipped
    assert embed_calls == [13]


async def test_changed_file_replaces_its_chunks(db, embed_calls, tmp_path):
    path = tmp_path / "resume.md"
    path.write_text("## Experience\n### Engineer · A\n- One\n- Two\n", encoding="utf-8")
    await ingest_file(db, path)
    path.write_text("## Experience\n### Engineer · A\n- Only one now\n", encoding="utf-8")
    result = await ingest_file(db, path)

    assert (result.chunks, result.skipped) == (1, False)
    assert await _chunk_count(db) == 1


async def test_removed_files_are_pruned(db, embed_calls, tmp_path):
    shutil.copy(SAMPLE, tmp_path / "a.md")
    shutil.copy(SAMPLE, tmp_path / "b.md")
    for f in find_files([tmp_path]):
        await ingest_file(db, f)
    (tmp_path / "b.md").unlink()

    removed = await remove_missing(db, find_files([tmp_path]))

    assert removed == ["b.md"]
    assert (await db.execute(select(Source.filename))).scalars().all() == ["a.md"]
    assert await _chunk_count(db) == 13


def test_find_files_skips_readme_and_unsupported(tmp_path):
    for name in ("README.md", "resume.md", "notes.txt", "photo.png"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    assert [f.name for f in find_files([tmp_path])] == ["notes.txt", "resume.md"]
