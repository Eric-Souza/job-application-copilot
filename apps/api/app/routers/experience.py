from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.services.ingest import find_files, ingest_file, remove_missing
from app.services.retrieval import MODES, search_experience

router = APIRouter(prefix="/experience", tags=["experience"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/ingest")
async def ingest(db: Db, force: bool = False) -> dict[str, Any]:
    """Index the resume folder (data/resume/). Unchanged files are skipped, removed ones pruned."""
    files = find_files([Path(get_settings().resume_dir)])
    results = [asdict(await ingest_file(db, f, force=force)) for f in files]
    return {"files": results, "removed": await remove_missing(db, files)}


@router.get("/search")
async def search(
    db: Db,
    q: Annotated[str, Query(min_length=2)],
    k: Annotated[int, Query(ge=1, le=20)] = 5,
    mode: Annotated[str | None, Query(pattern=f"^({'|'.join(MODES)})$")] = None,
) -> list[dict[str, Any]]:
    return [asdict(e) for e in await search_experience(db, q, k=k, mode=mode)]
