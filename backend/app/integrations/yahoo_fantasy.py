"""Yahoo Fantasy Sports API v2 client.

Fetches league lists and league settings using an OAuth2 access token.
Handles transparent token refresh on 401.

Yahoo API base: https://fantasysports.yahooapis.com/fantasy/v2/
All requests require ?format=json (default response is XML).
"""
from dataclasses import dataclass
from typing import Optional
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.yahoo import refresh_access_token
from app.security.fernet import encrypt, decrypt

logger = logging.getLogger(__name__)

_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"


class YahooReauthRequired(Exception):
    """Yahoo rejected the refresh token (revoked/expired) — the access token
    can't be renewed and the user must reconnect Yahoo. Mirrors the
    EspnAuthRequired/CbsAuthRequired pattern so callers can surface a
    reconnect prompt instead of a generic "verify credentials" HTTP error."""


class YahooLeaguesParseError(Exception):
    """Yahoo's leagues response didn't match the expected shape — a schema
    drift (unexpected nesting, locale/date change, malformed count) we can't
    navigate. Raised instead of silently returning ``[]`` so the failure
    surfaces through ``_provider_http_error`` as a provider error rather than a
    false "no leagues found" empty state. See issue #643."""


@dataclass
class YahooLeagueSummary:
    league_key: str
    name: str
    season: int
    num_teams: int


@dataclass
class YahooLeagueData:
    league_id: str
    name: str
    season: int
    league_size: int
    raw_scoring: dict       # stat_modifiers.stats — passed to yahoo_to_settings
    keepers: list           # empty list (Yahoo keeper config not in settings endpoint)
    adp_json: Optional[dict]  # always None — Yahoo doesn't expose live ADP


async def _get(url: str, access_token: str) -> dict:
    """GET with Bearer auth, requesting JSON format. Raises httpx.HTTPStatusError on non-2xx."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            params={"format": "json"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _with_refresh(url: str, user, db: AsyncSession) -> dict:
    """Call _get; on 401, refresh the user's token and retry once.

    Updates user.yahoo_access_token (still encrypted) and commits db on refresh.
    """
    access_token = decrypt(user.yahoo_access_token)
    try:
        return await _get(url, access_token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 401:
            raise
    # Token expired — refresh and retry. If the refresh token itself is
    # revoked/expired Yahoo returns 401 (or 400); that is not something the
    # user can fix by "verifying credentials" — they must reconnect Yahoo.
    try:
        new_token = await refresh_access_token(decrypt(user.yahoo_refresh_token))
    except httpx.HTTPStatusError as e:
        # Only a revoked/expired refresh token (Yahoo returns 400/401) means the
        # user must reconnect. Other statuses (429 rate-limit, 5xx) are transient
        # provider outages — re-raise so they flow through _provider_http_error as
        # an upstream error rather than a misleading "reconnect Yahoo" prompt.
        if e.response.status_code in (400, 401):
            raise YahooReauthRequired from e
        raise
    user.yahoo_access_token = encrypt(new_token)
    await db.commit()
    return await _get(url, new_token)


def _parse_leagues(data: dict) -> list[YahooLeagueSummary]:
    """Navigate Yahoo's deeply nested users/games/leagues response structure.

    A genuinely empty account — Yahoo returns the games/leagues envelope with
    ``count == 0`` — yields ``[]``. A response whose structure we can't navigate
    (a schema drift) is logged and raised as :class:`YahooLeaguesParseError`
    rather than swallowed into a misleading empty list, so the caller surfaces a
    provider error instead of a false "no leagues found". See issue #643.
    """
    results = []
    try:
        users = data["fantasy_content"]["users"]
        user_entry = users["0"]["user"]
        games = user_entry[1]["games"]
        game_count = int(games.get("count", 0))
        for gi in range(game_count):
            game_block = games[str(gi)]["game"]
            if len(game_block) < 2:
                continue
            game_meta = game_block[0]
            season = int(game_meta.get("season", 0))
            leagues_block = game_block[1].get("leagues", {})
            league_count = int(leagues_block.get("count", 0))
            for li in range(league_count):
                league = leagues_block[str(li)]["league"][0]
                results.append(YahooLeagueSummary(
                    league_key=league["league_key"],
                    name=league["name"],
                    season=season,
                    num_teams=int(league.get("num_teams", 0)),
                ))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning("Yahoo leagues parse failed: %s", e, exc_info=True)
        raise YahooLeaguesParseError("Unexpected Yahoo leagues response shape") from e
    return results


def _parse_league(data: dict) -> YahooLeagueData:
    """Parse league settings response into YahooLeagueData."""
    league_list = data["fantasy_content"]["league"]
    meta = league_list[0]
    settings = league_list[1]["settings"]
    return YahooLeagueData(
        league_id=meta["league_key"],
        name=meta["name"],
        season=int(meta["season"]),
        league_size=int(meta["num_teams"]),
        raw_scoring=settings.get("stat_modifiers", {}).get("stats", {}),
        keepers=[],
        adp_json=None,
    )


async def list_user_leagues(user, db: AsyncSession) -> list[YahooLeagueSummary]:
    """Return all NFL fantasy leagues for the authenticated user."""
    url = f"{_BASE}/users;use_login=1/games;game_keys=nfl/leagues"
    data = await _with_refresh(url, user, db)
    return _parse_leagues(data)


async def fetch_league(league_key: str, user, db: AsyncSession) -> YahooLeagueData:
    """Fetch scoring settings for a specific league by key (e.g. '423.l.12345')."""
    url = f"{_BASE}/league/{league_key}/settings"
    data = await _with_refresh(url, user, db)
    return _parse_league(data)
