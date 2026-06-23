"""NFL.com Fantasy anonymous-read client for league-linking flows.

NFL.com Fantasy exposes a working unofficial v2 JSON API at
api.fantasy.nfl.com/v2/league/*. Confirmed live (2026-06-23):
GET /v2/league/standings and GET /v2/league/teams return HTTP 200 with full
league metadata (name, leagueType, numTeams, divisions, teams) for BOTH
public AND private leagues, with NO app key, NO cookie, NO OAuth. This is
the simplest auth posture of any provider — we collect no credentials.

Two important quirks (both confirmed live; see autotiers-ff-knowledge):

1. Status code lies. A non-existent league returns HTTP *200* with an
   embedded {"errors": [{"messageStringId": "LEAGUE_INVALID", ...}]} body,
   NOT a 4xx. We inspect the body for an errors array — exactly the same
   discipline cbs.get_access_token uses for CBS's 200-with-errors quirk.
   (bug-class #4 — never trust the status code alone.)

2. Synthetic gameKey. The league nests under games.{gameKey}.leagues.{id}
   where gameKey (e.g. "102025" for season 2025) is not known a priori.
   We read it by iterating games.values() -> leagues.values() rather than
   computing or hardcoding the gameKey.

Scoring settings (/v2/league/settings) are gated behind an NFL appKey we do
not hold, so this client does NOT fetch scoring — raw_scoring is {} and
nfl_to_settings contributes only league_size. See the design doc and
follow-up issues.
"""
import httpx
from app.integrations.types import LeagueData


class NflLeagueNotFound(Exception):
    """NFL.com reported the league does not exist (returned a 200 body with
    an errors array, e.g. LEAGUE_INVALID) — the caller supplied a bad league
    id or season, or the league was deleted/made unreadable."""


_BASE_URL = "https://api.fantasy.nfl.com/v2/league"

# NFL's edge may reject the default httpx UA ("python-httpx/x.y.z") as
# script-like traffic, the same failure ESPN exhibits (see espn.py's
# _BROWSER_UA). Pin a regular browser UA on every request.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# We fetch ONLY the standings view: it carries everything LeagueData needs
# (name, numTeams) for this deliverable. The teams view was confirmed
# reachable anonymously too, but parsing rosters is out of scope (keepers
# are not exposed there), so fetching it would be a dead network call.
_VIEW = "standings"


def _first_league(payload: dict) -> dict:
    """Pull the single league dict out of games.{gameKey}.leagues.{id}.

    The gameKey is a synthetic, season-derived key we don't know ahead of
    time, so we iterate rather than hardcode it. Returns {} if the shape is
    missing entirely (defensive — a malformed payload degrades to "no league
    found" rather than a KeyError/AttributeError).
    """
    games = payload.get("games")
    if not isinstance(games, dict):
        return {}
    for game in games.values():
        if not isinstance(game, dict):
            continue
        leagues = game.get("leagues")
        if not isinstance(leagues, dict):
            continue
        for league in leagues.values():
            if isinstance(league, dict):
                return league
    return {}


def _has_league_error(payload: dict) -> bool:
    """True when NFL returned an errors array in a 200 body (the not-found
    signal). NFL does NOT 404 a bad league id — see module docstring."""
    errors = payload.get("errors")
    return isinstance(errors, list) and len(errors) > 0


async def fetch_league(league_id: str, season: int) -> LeagueData:
    """Fetch league metadata from NFL.com's anonymous-read v2 API.

    Raises NflLeagueNotFound when NFL reports the league does not exist
    (a 200 body carrying an errors array — NOT a 4xx). Other HTTP/transport
    failures propagate to the caller (the API layer maps them via
    _provider_http_error).
    """
    headers = {"User-Agent": _BROWSER_UA, "Accept": "application/json"}
    params = {"leagueId": str(league_id), "season": str(season)}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_BASE_URL}/{_VIEW}", params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    if not isinstance(payload, dict):
        payload = {}

    # NFL returns HTTP 200 with an errors array for a missing league (NOT a
    # 4xx) — inspect the body, not the status code (bug-class #4).
    if _has_league_error(payload):
        raise NflLeagueNotFound(
            f"NFL.com reports league {league_id} does not exist for season {season}"
        )

    league = _first_league(payload)
    if not league:
        # No errors array but also no league dict — treat as not found rather
        # than fabricating an empty league row.
        raise NflLeagueNotFound(
            f"NFL.com returned no league data for league {league_id}, season {season}"
        )

    name = league.get("name") or f"NFL league {league_id}"
    league_size = int(league.get("numTeams") or league.get("maxTeams") or 12)

    return LeagueData(
        league_id=str(league_id),
        name=name,
        # NFL's body has no standalone season field on these views; the
        # caller supplied the season in the path, so it is the source of
        # truth (same honest-source pattern as cbs._current_season).
        season=int(season),
        # Scoring is appKey-gated and not fetched here — nfl_to_settings
        # contributes only league_size. See the design doc / follow-up issue.
        raw_scoring={},
        league_size=league_size,
        # Keepers and ADP are not exposed on the anonymous endpoints —
        # degrade exactly as Sleeper/ESPN/Yahoo do when unavailable.
        keepers=[],
        adp_json=None,
    )
