"""User favorites CRUD. Auth-gated."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserFavorites, Profile
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


async def _maybe_enable_favorites_rule(db: AsyncSession, user: User) -> None:
    """If the user's active profile doesn't yet list 'Favorites' in rules_json,
    append it as enabled. Does NOT modify a 'Favorites' entry that already
    exists (so a user who disabled the rule keeps it disabled across
    subsequent adds)."""
    if user.last_active_profile_id is None:
        return
    profile = await db.get(Profile, user.last_active_profile_id)
    if profile is None:
        return
    current_names = {entry.get("name") for entry in profile.rules_json if isinstance(entry, dict)}
    if "Favorites" in current_names:
        return
    profile.rules_json = [
        *profile.rules_json,
        {"name": "Favorites", "enabled": True, "weight": 1.0},
    ]


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

    had_any_before = (
        row is not None
        and (bool(row.favorite_player_ids) or bool(row.favorite_teams))
    )

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

    has_any_now = bool(player_ids) or bool(teams)

    # Auto-enable the Favorites rule on the user's transition from 0 → 1+,
    # in the same transaction so a partial failure can't desync.
    if has_any_now and not had_any_before:
        await _maybe_enable_favorites_rule(db, user)

    await db.commit()
    await db.refresh(row)
    return FavoritesOut.model_validate(row)
