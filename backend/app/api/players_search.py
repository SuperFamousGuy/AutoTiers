"""Auth-gated player-by-name search. Powers the favorites picker UI."""
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.models.player import Player
from app.auth.dependencies import require_user, get_current_user

router = APIRouter(prefix="/players", tags=["players"])

_RESULT_CAP = 25


class PlayerSearchResult(BaseModel):
    id: str
    name: str
    position: str
    team: str | None

    model_config = {"from_attributes": True}


@router.get("")
async def list_or_search_players(
    q: Annotated[Optional[str], Query(min_length=1, max_length=80)] = None,
    user: Optional[User] = get_current_user,
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/players — list all players (no auth required).
    GET /api/players?q=<name> — search players by name (auth required).
    """
    # Search mode: when ?q is provided, auth is required
    if q is not None:
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
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

    # List mode: no auth required, return all players
    result = await db.execute(select(Player).order_by(Player.name))
    players = result.scalars().all()
    return [
        {"id": p.id, "name": p.name, "position": p.position, "team": p.team, "age": p.age}
        for p in players
    ]
