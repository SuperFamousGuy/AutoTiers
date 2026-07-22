"""Public player lookup. Powers the client-side (localStorage) favorites picker.

Anonymous, and capped: `?q=` substring search returns at most 25 rows and
`/batch` accepts at most 20 ids. There is no unbounded full-table dump
endpoint — the old anonymous `GET /players` was removed as a scrape/DoS
surface (#807); these caps are what keep this endpoint from reintroducing
that risk now that per-user auth is gone entirely (v1 accounts teardown).
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.player import Player

router = APIRouter(prefix="/players", tags=["players-search"])

_RESULT_CAP = 25


def _escape_like(s: str) -> str:
    """Escape LIKE metacharacters so a user query matches literally.

    Without this, ``%`` and ``_`` in ``q`` act as wildcards: ``%`` matches
    the whole table and ``a_e`` matches ``ace``/``ape``. Backslash is escaped
    first so it doesn't double-escape the ``%``/``_`` replacements, and it is
    passed as the ``escape=`` char to ``.like()`` below.
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PlayerSearchResult(BaseModel):
    id: str
    name: str
    position: str
    team: str | None
    espn_id: str | None

    model_config = {"from_attributes": True}


@router.get("/batch", response_model=list[PlayerSearchResult])
async def batch_players(
    ids: Annotated[str, Query(min_length=1, max_length=400)],
    db: AsyncSession = Depends(get_db),
) -> list[PlayerSearchResult]:
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="No valid IDs provided.")
    if len(id_list) > 20:
        raise HTTPException(status_code=400, detail="Too many IDs (max 20).")
    rows = (await db.scalars(
        select(Player).where(Player.id.in_(id_list))
    )).all()
    by_id = {r.id: r for r in rows}
    return [PlayerSearchResult.model_validate(by_id[i]) for i in id_list if i in by_id]


@router.get("/search", response_model=list[PlayerSearchResult])
async def search_players(
    q: Annotated[str, Query(min_length=1, max_length=80)],
    db: AsyncSession = Depends(get_db),
) -> list[PlayerSearchResult]:
    """Case-insensitive substring match on Player.name. Returns up to 25 rows."""
    q_clean = q.strip()
    if not q_clean:
        raise HTTPException(status_code=400, detail="Query must not be blank.")
    pattern = f"%{_escape_like(q_clean.lower())}%"
    rows = (await db.scalars(
        select(Player)
        .where(func.lower(Player.name).like(pattern, escape="\\"))
        .order_by(Player.name)
        .limit(_RESULT_CAP)
    )).all()
    return [PlayerSearchResult.model_validate(r) for r in rows]
