from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.player import Player

router = APIRouter()


@router.get("/players")
async def list_players(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(Player).order_by(Player.name))
    players = result.scalars().all()
    return [
        {"id": p.id, "name": p.name, "position": p.position, "team": p.team, "age": p.age}
        for p in players
    ]
