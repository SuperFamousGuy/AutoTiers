"""Per-profile fantasy-league linking endpoints."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

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
    # Either both league_id + season are present (full link with league data),
    # or neither (pre-link the provider account without a league).
    league_id: Optional[str] = None
    season: Optional[int] = None


class EspnConnectBody(BaseModel):
    # league_id + season are optional so users can link an ESPN account
    # (cookies-only) to unlock auth-gated rankings without picking a league.
    league_id: Optional[str] = None
    season: Optional[int] = None
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


def _provider_http_error(provider: str, e: Exception) -> HTTPException:
    """Convert a provider-side error into a structured HTTPException.

    Without this, an unhandled exception from httpx (timeout, HTTP error from the
    provider, JSON decode error, etc.) becomes a FastAPI 500 whose response often
    skips CORS headers — the browser blocks it, the frontend sees a network error
    instead of a useful message, and we lose any signal about what went wrong.
    """
    logger.exception("%s provider error", provider)
    if isinstance(e, httpx.HTTPStatusError):
        return HTTPException(
            status_code=502,
            detail=f"{provider} returned HTTP {e.response.status_code}. Verify the league id and your credentials.",
        )
    if isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError)):
        return HTTPException(
            status_code=504,
            detail=f"{provider} timed out. Try again in a moment.",
        )
    if isinstance(e, httpx.RequestError):
        return HTTPException(
            status_code=502,
            detail=f"Couldn't reach {provider} ({type(e).__name__}).",
        )
    return HTTPException(
        status_code=502,
        detail=f"Unexpected {provider} error: {type(e).__name__}: {e}",
    )


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
    except Exception as e:
        raise _provider_http_error("Sleeper", e)
    return [SleeperLeagueSummaryOut(id=l.id, name=l.name, season=l.season) for l in leagues]


@router.post("/sleeper", response_model=LinkedLeagueResponse)
async def post_sleeper(
    profile_id: uuid.UUID,
    body: SleeperConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    ll = _upsert_linked_league(profile, db)
    ll.provider = "sleeper"
    ll.username_or_swid = body.username
    ll.credentials_encrypted = None
    ll.last_synced_at = datetime.now(timezone.utc)

    if body.league_id:
        try:
            data = await fetch_sleeper_league(body.league_id)
        except Exception as e:
            raise _provider_http_error("Sleeper", e)
        mapped = sleeper_to_settings(data.raw_scoring, league_size=data.league_size)
        _apply_settings(profile, mapped)
        ll.league_id = data.league_id
        ll.league_metadata_json = {"name": data.name, "season": data.season}
        ll.keepers_json = data.keepers
        ll.adp_json = data.adp_json
    else:
        # Pre-link: provider account stored, no league data fetched.
        ll.league_id = None
        ll.league_metadata_json = None
        ll.keepers_json = None
        ll.adp_json = None

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
    # Either a league_id (public or about to be paired with cookies) or a
    # full SWID + espn_s2 cookie pair is required. An empty body would
    # produce a row with nothing useful in it.
    if not body.league_id and not (body.swid and body.espn_s2):
        raise HTTPException(
            status_code=400,
            detail="Provide a league ID, or paste your ESPN SWID + espn_s2 cookies. Nothing to link without either.",
        )

    profile = await _resolve_profile(profile_id, user, db)
    ll = _upsert_linked_league(profile, db)
    ll.provider = "espn"
    ll.username_or_swid = body.swid or ""
    ll.credentials_encrypted = encrypt(body.espn_s2) if body.espn_s2 else None
    ll.last_synced_at = datetime.now(timezone.utc)

    if body.league_id and body.season is not None:
        try:
            data = await fetch_espn_league(body.league_id, body.season, body.swid, body.espn_s2)
        except EspnAuthRequired:
            raise HTTPException(
                status_code=400,
                detail="ESPN rejected the request — the league may be private; paste your SWID and espn_s2 cookies and try again.",
            )
        except Exception as e:
            raise _provider_http_error("ESPN", e)
        mapped = espn_to_settings(data.raw_scoring, league_size=data.league_size)
        _apply_settings(profile, mapped)
        ll.league_id = data.league_id
        ll.league_metadata_json = {"name": data.name, "season": data.season}
        ll.keepers_json = data.keepers
        ll.adp_json = data.adp_json
    else:
        # Pre-link: cookies stored, no league data fetched.
        ll.league_id = None
        ll.league_metadata_json = None
        ll.keepers_json = None
        ll.adp_json = None

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
        raise HTTPException(status_code=400, detail="Profile has no linked provider account")
    if not ll.league_id:
        # Pre-linked provider with no league selected — nothing to refresh.
        raise HTTPException(
            status_code=400,
            detail="No league is selected on this linked account — pick one before refreshing.",
        )

    stored_season: int = (ll.league_metadata_json or {}).get("season") or 0
    if not stored_season:
        raise HTTPException(status_code=400, detail="Linked league is missing season metadata — please reconnect.")

    if ll.provider == "sleeper":
        try:
            data = await fetch_sleeper_league(ll.league_id)
        except Exception as e:
            raise _provider_http_error("Sleeper", e)
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
        except Exception as e:
            raise _provider_http_error("ESPN", e)
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
