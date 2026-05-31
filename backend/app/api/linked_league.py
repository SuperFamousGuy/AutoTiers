"""Per-profile fantasy-league linking endpoints."""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import User, Profile, LinkedLeague
from app.auth.dependencies import require_user
from app.integrations.sleeper import (
    list_user_leagues, fetch_league as fetch_sleeper_league, SleeperUserNotFound,
)
from app.integrations.espn import fetch_league as fetch_espn_league, EspnAuthRequired
from app.integrations.scoring_mappers import sleeper_to_settings, espn_to_settings
from app.security.fernet import encrypt, decrypt
from app.schemas.linked_league import LinkedLeagueOut
from app.schemas.auth import ProfileOut


router = APIRouter(prefix="/profiles/{profile_id}/link", tags=["linked_league"])


class SleeperLeagueSummaryOut(BaseModel):
    id: str
    name: str
    season: int


class SleeperConnectBody(BaseModel):
    username: str
    league_id: str
    season: int


class EspnConnectBody(BaseModel):
    league_id: str
    season: int
    swid: Optional[str] = None
    espn_s2: Optional[str] = None


class LinkedLeagueResponse(BaseModel):
    linked_league: LinkedLeagueOut
    profile: ProfileOut


async def _check_ownership(
    profile_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Lightweight ownership check — no eager-loading. Raises 404 if not owned by caller."""
    exists = await db.scalar(
        select(Profile.id).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="Profile not found")


async def _resolve_profile(
    profile_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Profile:
    """Load profile + linked_league, raising 404 if not owned by caller."""
    p = await db.scalar(
        select(Profile)
        .where(Profile.id == profile_id, Profile.user_id == user.id)
        .options(selectinload(Profile.linked_league)),
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return p


def _apply_settings(profile: Profile, mapped: dict) -> None:
    """Merge mapped scoring into profile.settings_json, preserving user-controlled fields."""
    current = dict(profile.settings_json or {})
    current.update(mapped)
    profile.settings_json = current


def _upsert_linked_league(profile: Profile, db: AsyncSession) -> LinkedLeague:
    """Return the existing LinkedLeague row or create and register a new one."""
    if profile.linked_league is None:
        ll = LinkedLeague(profile_id=profile.id)
        db.add(ll)
        return ll
    return profile.linked_league


def _build_response(ll: LinkedLeague, profile: Profile) -> LinkedLeagueResponse:
    return LinkedLeagueResponse(
        linked_league=LinkedLeagueOut.model_validate(ll),
        profile=ProfileOut.model_validate(profile),
    )


@router.get("/sleeper/leagues", response_model=list[SleeperLeagueSummaryOut])
async def get_sleeper_leagues(
    profile_id: uuid.UUID,
    username: str,
    season: int,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> list[SleeperLeagueSummaryOut]:
    await _check_ownership(profile_id, user, db)
    try:
        leagues = await list_user_leagues(username, season)
    except SleeperUserNotFound:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{username}' not found")
    return [SleeperLeagueSummaryOut(id=l.id, name=l.name, season=l.season) for l in leagues]


@router.post("/sleeper", response_model=LinkedLeagueResponse)
async def post_sleeper(
    profile_id: uuid.UUID,
    body: SleeperConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    data = await fetch_sleeper_league(body.league_id)
    mapped = sleeper_to_settings(data.raw_scoring, league_size=data.league_size)
    _apply_settings(profile, mapped)

    ll = _upsert_linked_league(profile, db)
    ll.provider = "sleeper"
    ll.league_id = data.league_id
    ll.username_or_swid = body.username
    ll.credentials_encrypted = None
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return _build_response(ll, profile)


@router.post("/espn", response_model=LinkedLeagueResponse)
async def post_espn(
    profile_id: uuid.UUID,
    body: EspnConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    try:
        data = await fetch_espn_league(body.league_id, body.season, body.swid, body.espn_s2)
    except EspnAuthRequired:
        raise HTTPException(
            status_code=400,
            detail="ESPN rejected the request — the league may be private; paste your SWID and espn_s2 cookies and try again.",
        )
    mapped = espn_to_settings(data.raw_scoring, league_size=data.league_size)
    _apply_settings(profile, mapped)

    ll = _upsert_linked_league(profile, db)
    ll.provider = "espn"
    ll.league_id = data.league_id
    ll.username_or_swid = body.swid or ""
    ll.credentials_encrypted = encrypt(body.espn_s2) if body.espn_s2 else None
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return _build_response(ll, profile)


@router.post("/refresh", response_model=LinkedLeagueResponse)
async def refresh(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    ll = profile.linked_league
    if ll is None:
        raise HTTPException(status_code=400, detail="Profile has no linked league")

    stored_season: int = ll.league_metadata_json.get("season") or 0
    if not stored_season:
        raise HTTPException(status_code=400, detail="Linked league is missing season metadata — please reconnect.")

    if ll.provider == "sleeper":
        data = await fetch_sleeper_league(ll.league_id)
        mapped = sleeper_to_settings(data.raw_scoring, league_size=data.league_size)
    elif ll.provider == "espn":
        espn_s2 = decrypt(ll.credentials_encrypted) if ll.credentials_encrypted else None
        try:
            data = await fetch_espn_league(
                ll.league_id, stored_season,
                ll.username_or_swid or None, espn_s2,
            )
        except EspnAuthRequired:
            raise HTTPException(status_code=400, detail="ESPN cookies expired — please reconnect.")
        mapped = espn_to_settings(data.raw_scoring, league_size=data.league_size)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{ll.provider}'")

    _apply_settings(profile, mapped)
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return _build_response(ll, profile)


@router.delete("", status_code=204)
async def delete_link(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await _resolve_profile(profile_id, user, db)
    if profile.linked_league is None:
        return
    await db.delete(profile.linked_league)
    await db.commit()
