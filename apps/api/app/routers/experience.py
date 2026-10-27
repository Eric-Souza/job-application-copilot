from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.ingest import ingest_configured
from app.services.retrieval import MODES, search_experience

router = APIRouter(prefix="/experience", tags=["experience"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/ingest")
async def ingest(db: Db, force: bool = False) -> dict[str, Any]:
    """Index data/resume/, or the profile MCP server's resume if PROFILE_MCP is set.

    Unchanged sources are skipped, removed ones pruned.
    """
    results, removed = await ingest_configured(db, force=force)
    return {"files": [asdict(r) for r in results], "removed": removed}


@router.get("/search")
async def search(
    db: Db,
    q: Annotated[str, Query(min_length=2)],
    k: Annotated[int, Query(ge=1, le=20)] = 5,
    mode: Annotated[str | None, Query(pattern=f"^({'|'.join(MODES)})$")] = None,
) -> list[dict[str, Any]]:
    return [asdict(e) for e in await search_experience(db, q, k=k, mode=mode)]
