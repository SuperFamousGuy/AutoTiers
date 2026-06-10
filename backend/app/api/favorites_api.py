"""User favorites CRUD. Auth-gated."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserFavorites
from app.auth.dependencies import require_user
from app.schemas.favorites import FavoritesUpdate, FavoritesOut
from app.data.teams import is_valid_team

router = APIRouter(prefix="/favorites", tags=["favorites"])

_PLAYER_CAP = 20
_TEAM_CAP = 4


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _validate_and_normalize(body: FavoritesUpdate) -> tuple[list[str], list[str]]:
    """Apply cap, blank, team-validity, and dedup rules. Raise HTTPException on violation."""
    # Class 2 guard: reject blank/whitespace-only entries before counting toward cap.
    if any(not pid or not pid.strip() for pid in body.favorite_player_ids):
        raise HTTPException(status_code=422, detail="Player ID entries must not be blank.")
    if any(not t or not t.strip() for t in body.favorite_teams):
        raise HTTPException(status_code=422, detail="Team entries must not be blank.")

    # Team validity against the canonical 32.
    for team in body.favorite_teams:
        if not is_valid_team(team):
            raise HTTPException(status_code=422, detail=f"Unknown team: {team}")

    # Dedup BEFORE cap check so the cap reflects unique entries.
    player_ids = _dedupe_preserve_order(body.favorite_player_ids)
    teams = _dedupe_preserve_order(body.favorite_teams)

    if len(player_ids) > _PLAYER_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Too many favorite players (max {_PLAYER_CAP}).",
        )
    if len(teams) > _TEAM_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Too many favorite teams (max {_TEAM_CAP}).",
        )
    return player_ids, teams


@router.get("", response_model=FavoritesOut)
async def get_favorites(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> FavoritesOut:
    row = (await db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one_or_none()
    if row is None:
        return FavoritesOut(favorite_player_ids=[], favorite_teams=[])
    return FavoritesOut.model_validate(row)


@router.put("", response_model=FavoritesOut)
async def put_favorites(
    body: FavoritesUpdate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> FavoritesOut:
    player_ids, teams = _validate_and_normalize(body)

    row = (await db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one_or_none()

    if row is None:
        row = UserFavorites(
            user_id=user.id,
            favorite_player_ids=player_ids,
            favorite_teams=teams,
        )
        db.add(row)
    else:
        row.favorite_player_ids = player_ids
        row.favorite_teams = teams

    await db.commit()
    await db.refresh(row)
    return FavoritesOut.model_validate(row)
