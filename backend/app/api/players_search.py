"""Auth-gated player-by-name search. Powers the favorites picker UI.

Distinct from `app.api.players.list_players` (anonymous full list) — this
endpoint requires auth and supports an `?q=` substring match.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.models.player import Player
from app.auth.dependencies import require_user

router = APIRouter(prefix="/players", tags=["players-search"])

_RESULT_CAP = 25


class PlayerSearchResult(BaseModel):
    id: str
    name: str
    position: str
    team: str | None

    model_config = {"from_attributes": True}


@router.get("/search", response_model=list[PlayerSearchResult])
async def search_players(
    q: Annotated[str, Query(min_length=1, max_length=80)],
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> list[PlayerSearchResult]:
    """Case-insensitive substring match on Player.name. Returns up to 25 rows."""
    q_clean = q.strip()
    if not q_clean:
        raise HTTPException(status_code=400, detail="Query must not be blank.")
    pattern = f"%{q_clean.lower()}%"
    rows = (await db.scalars(
        select(Player)
        .where(func.lower(Player.name).like(pattern))
        .order_by(Player.name)
        .limit(_RESULT_CAP)
    )).all()
    return [PlayerSearchResult.model_validate(r) for r in rows]
