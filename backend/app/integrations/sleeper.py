"""Sleeper public-API client for league-linking flows.

Sleeper has no auth: a username is enough. We use these endpoints:
  - /v1/user/{username} → user_id
  - /v1/user/{user_id}/leagues/nfl/{season}
  - /v1/league/{league_id} and /v1/league/{league_id}/rosters
  - /v1/players/nfl  (static player dictionary for keeper/pick name lookup)
  - /v1/league/{league_id}/drafts  (list, may be empty before draft happens)
  - /v1/draft/{draft_id}/picks  (only when a draft completed)
"""
import time

import httpx
from app.config import settings
from app.integrations.types import LeagueSummary, LeagueData


BASE_URL = "https://api.sleeper.app"

# Process-local cache for /v1/players/nfl (issue #560). The dict is static and
# identical for every user/league, so it's keyed globally (a single slot), not
# per-user. Guarded by a monotonic timestamp so it's immune to wall-clock jumps.
_players_cache: dict | None = None
_players_cached_at: float | None = None


def clear_players_cache() -> None:
    """Reset the global players-dict cache. Used by tests for hermetic isolation."""
    global _players_cache, _players_cached_at
    _players_cache = None
    _players_cached_at = None


class SleeperUserNotFound(Exception):
    """Raised when the Sleeper user lookup returns 404."""


async def _get_json(client: httpx.AsyncClient, path: str) -> object:
    resp = await client.get(f"{BASE_URL}{path}")
    resp.raise_for_status()
    return resp.json()


async def _get_players_dict(client: httpx.AsyncClient) -> dict:
    """Return Sleeper's NFL player dictionary, served from a process-local cache.

    A cache hit within the TTL avoids re-downloading the multi-MB payload on
    every league link (Sleeper asks callers not to fetch it more than once a
    day). The network request uses its own larger timeout, independent of the
    blanket 10s the small league/rosters/drafts calls share, so a slow-but-
    healthy transfer isn't mistaken for a Sleeper outage.
    """
    global _players_cache, _players_cached_at
    ttl = settings.sleeper_players_cache_ttl_seconds
    now = time.monotonic()
    if (
        _players_cache is not None
        and _players_cached_at is not None
        and ttl > 0
        and now - _players_cached_at < ttl
    ):
        return _players_cache

    resp = await client.get(
        f"{BASE_URL}/v1/players/nfl",
        timeout=settings.sleeper_players_timeout_seconds,
    )
    resp.raise_for_status()
    players = resp.json()
    if ttl > 0:
        _players_cache = players
        _players_cached_at = now
    else:
        # Caching disabled (TTL <= 0): don't retain the multi-MB payload in the
        # module-level cache — an operator disabling caching (often to save
        # memory) would be surprised to see it linger. Drop any prior slot too.
        _players_cache = None
        _players_cached_at = None
    return players


async def list_user_leagues(username: str, season: int) -> list[LeagueSummary]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/v1/user/{username}")
        if resp.status_code == 404:
            raise SleeperUserNotFound(f"Sleeper user '{username}' not found")
        resp.raise_for_status()
        user = resp.json()
        user_id = user["user_id"]

        leagues_data = await _get_json(client, f"/v1/user/{user_id}/leagues/nfl/{season}")
        return [
            LeagueSummary(id=l["league_id"], name=l["name"], season=int(l["season"]))
            for l in leagues_data
        ]


async def fetch_league(league_id: str) -> LeagueData:
    async with httpx.AsyncClient(timeout=10.0) as client:
        league = await _get_json(client, f"/v1/league/{league_id}")
        rosters = await _get_json(client, f"/v1/league/{league_id}/rosters")
        players_dict = await _get_players_dict(client)
        drafts = await _get_json(client, f"/v1/league/{league_id}/drafts")

        keepers: list[dict] = []
        for roster in rosters:
            for pid in (roster.get("keepers") or []):
                p = players_dict.get(pid)
                if p is None:
                    continue
                keepers.append({
                    "player_name": p.get("full_name") or "",
                    "position": p.get("position") or "",
                    "team": p.get("team") or "",
                })

        adp_json: dict | None = None
        completed_drafts = [d for d in drafts if d.get("status") == "complete"]
        if completed_drafts:
            draft_id = completed_drafts[0]["draft_id"]
            picks = await _get_json(client, f"/v1/draft/{draft_id}/picks")
            adp_json = {}
            for pick in picks:
                p = players_dict.get(pick["player_id"])
                if p is None or not p.get("full_name"):
                    continue
                adp_json[p["full_name"]] = float(pick["pick_no"])

        return LeagueData(
            league_id=league["league_id"],
            name=league["name"],
            season=int(league["season"]),
            raw_scoring=league.get("scoring_settings") or {},
            league_size=int(league.get("total_rosters") or 12),
            keepers=keepers,
            adp_json=adp_json,
        )
