"""CBS Sports unofficial-API client for league-linking flows.

CBS has no public OAuth program. Authentication is a credential exchange
against an unofficial mobile-app endpoint: the user's CBS email + password
are POSTed and exchanged for an opaque access token. AutoTiers persists that
token (Fernet-encrypted), not the password — see backend/app/api/linked_league.py
post_cbs for the persistence flow.

Endpoints and the client_id/client_secret pair below were confirmed live
against api.cbssports.com; client_id/client_secret are public constants
baked into CBS's own mobile app (not a secret AutoTiers controls), mirrored
verbatim from the open-source fantasy-football-metrics-weekly-report project
(ffmwr/dao/platforms/cbs.py).

Quirk: the auth endpoint returns HTTP 200 even on bad credentials, with the
failure embedded in the JSON body as {"body": {"errors": [...]}}. We must
inspect the body, not rely on httpx.raise_for_status().
"""
from datetime import date

import httpx
from app.integrations.types import LeagueData


class CbsAuthRequired(Exception):
    """CBS rejected credentials (bad email/password) or an access token is
    expired/invalid — the caller needs to reconnect."""


_AUTH_URL = "https://api.cbssports.com/general/oauth/mobile/login?response_format=json"
_CLIENT_ID = "cbssports"
_CLIENT_SECRET = "sportsallthetime"

_LEAGUE_VIEWS = ("details", "rules", "teams", "rosters", "transaction-list/log")

# CBS's API is the unofficial backend for its own mobile app, not a public
# web API — like ESPN (see espn.py's _BROWSER_UA comment), it may reject
# requests carrying the default httpx UA ("python-httpx/x.y.z") as
# script-like traffic. The FFMWR reference implementation
# (ffmwr/dao/platforms/cbs.py) always pins this exact mobile-app UA on every
# request, auth included, so we mirror it rather than risk an unverified
# default.
_MOBILE_UA = "Fantasy FB/5 CFNetwork/1410.0.3 Darwin/22.6.0"


def _league_api_base(league_id: str) -> str:
    return f"https://{league_id}.football.cbssports.com/api/league"


def _current_season(stored_season: int | None = None) -> int:
    """Best-effort current NFL season, mirroring web/src/lib/season.ts.

    CBS's /league/details response (confirmed against the FFMWR reference
    implementation, ffmwr/dao/platforms/cbs.py, map_data_to_base) exposes
    name/current_period/num_teams/regular_season_periods/num_divisions but
    NO season/year field — FFMWR itself sources season from caller-supplied
    config, not from the API.

    When a `stored_season` is supplied (the /link/refresh path passes the
    season cached at initial-link time), we return it verbatim so the season
    is pinned to what the user linked and only ever changes on an explicit
    relink. Without a caller-supplied season (the initial-link path, which
    has no prior value) we fall back to wall-clock inference (NFL season
    rolls over in March; Jan/Feb belong to the previous season), the same
    logic the frontend's currentSeason() uses for ESPN's pre-link flow.

    Deriving season from wall-clock on *every* fetch was the bug (issue
    #775): a refresh made after the March rollover boundary could silently
    flip league_metadata_json.season forward with no underlying league
    change, corrupting the season badge and any season-keyed logic
    downstream. Caching it at link time removes that non-determinism.
    """
    if stored_season:
        return stored_season
    today = date.today()
    return today.year - 1 if today.month < 3 else today.year


async def get_access_token(email: str, password: str) -> str:
    """Exchange CBS email + password for an opaque access token.

    Raises CbsAuthRequired on bad credentials (CBS returns HTTP 200 with an
    embedded errors array on bad credentials, not a 4xx — see module docstring).
    """
    body = {
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "user_id": email,
        "password": password,
    }
    headers = {"User-Agent": _MOBILE_UA, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.post(_AUTH_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    response_body = data.get("body") or {}
    if response_body.get("errors"):
        raise CbsAuthRequired("CBS rejected the supplied email or password")

    access_token = response_body.get("access_token")
    if not access_token:
        # Defensive: a 200 with neither an access_token nor an errors array
        # is itself an auth failure from AutoTiers' point of view — we have
        # nothing usable to persist.
        raise CbsAuthRequired("CBS did not return an access token")
    return access_token


async def fetch_league(
    league_id: str, access_token: str, stored_season: int | None = None
) -> LeagueData:
    """Fetch league details/rules/teams/rosters/transaction-log from CBS.

    `stored_season`, when passed, is the season cached in
    league_metadata_json at initial-link time. The /link/refresh path
    threads it through so the season stays pinned to what the user linked
    (issue #775); the initial-link call site omits it (there is no prior
    season) and falls back to wall-clock inference. See _current_season.

    Raises CbsAuthRequired on an invalid/expired access token (CBS returns
    HTTP 400 with 'Failed Authentication: error - invalid access token').
    """
    headers = {"Authorization": access_token, "Accept": "application/json", "User-Agent": _MOBILE_UA}
    base = _league_api_base(league_id)
    query = f"version=3.0&response_format=json&sport=football&league_id={league_id}"

    bodies: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for view in _LEAGUE_VIEWS:
            url = f"{base}/{view}?{query}"
            resp = await client.get(url, headers=headers)
            if resp.status_code == 400 and (
                "Failed Authentication" in resp.text or "invalid access token" in resp.text
            ):
                raise CbsAuthRequired("CBS access token expired or invalid")
            resp.raise_for_status()
            payload = resp.json()
            bodies[view] = payload.get("body") or {}

    details = bodies["details"].get("league_details") or {}
    rules = bodies["rules"].get("rules") or {}
    teams_raw = bodies["teams"].get("teams") or []
    rosters_raw = (bodies["rosters"].get("rosters") or {}).get("teams") or []
    transaction_log = bodies["transaction-list/log"].get("transaction_log") or []

    name = details.get("name") or f"CBS league {league_id}"
    league_size = int(details.get("num_teams") or len(teams_raw) or 12)

    keepers = _extract_keepers(transaction_log, rosters_raw)

    # CBS's /league/details payload has no season/year field (confirmed
    # against the FFMWR reference implementation — see _current_season's
    # docstring); on the refresh path use the season cached at link time
    # (stored_season), and otherwise derive it from wall-clock, rather than
    # trusting a key that doesn't exist (which previously always evaluated to
    # season=0 and broke /link/refresh's "missing season metadata" guard on
    # every CBS profile).
    season = (
        int(details["season"])
        if isinstance(details.get("season"), int)
        else _current_season(stored_season)
    )

    return LeagueData(
        league_id=str(league_id),
        name=name,
        season=season,
        raw_scoring=rules,
        league_size=league_size,
        keepers=keepers,
        # CBS exposes no draft-pick-level endpoint comparable to ESPN's
        # draftDetail.picks in this view set — ADP is not available.
        adp_json=None,
    )


def _as_dict_list(value) -> list[dict]:
    """Coerce `value` into a list of dicts, or [] if it isn't usable.

    Two failure modes get collapsed into the same safe result:
    1. `value` itself isn't a list at all (e.g. a JSON boolean/number/string
       where a list was expected — `"moves": true` or `"players": 7`). The
       common `x.get(key) or []` idiom does NOT catch this: `or []` only
       substitutes on a *falsy* value (None, [], ""), but `True`/`5`/`"x"`
       are truthy, so a bare `for item in (x.get(key) or [])` raises
       `TypeError: 'bool' object is not iterable` before any per-item
       isinstance check ever runs.
    2. `value` is a list but contains non-dict items (e.g. `None` for a
       voided/cancelled transaction) — those individual items are filtered
       out rather than the whole list being discarded.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_keepers(transaction_log: list[dict], rosters_raw: list[dict]) -> list[dict]:
    """Derive keepers from the league transaction log.

    CBS has no dedicated "keepers" settings field (unlike ESPN's
    draftStrategy.keepers per team) — keeper status is recorded as a
    transaction-log entry. We look for moves whose type/description marks
    them as a keeper designation. Player position/team are filled in from
    the roster payload when available, falling back to empty strings
    (mirrors ESPN's behaviour when a lookup misses, espn.py lines 67-77).

    UNVERIFIED: the FFMWR reference implementation (ffmwr/dao/platforms/cbs.py)
    reads the transaction log only to count "won"/"drop"/"trade" move types
    for box-score reporting — it never extracts keepers and contains no
    "keeper" move-type literal anywhere. No move-type discriminator for
    keeper designations was found in any available reference, and no live
    CBS account was available during implementation to inspect a real
    transaction log. This match on "keeper" appearing in move.type (or an
    is_keeper boolean) is a best-effort guess at CBS's naming convention, not
    a confirmed field. If the real key differs, this silently returns []
    (an honest empty list, not a crash) rather than guessing wrong loudly.
    See Implementation Report "keepers escalation" for the recommended
    follow-up: capture a real transaction-list/log payload from a live CBS
    league and verify/correct this discriminator.

    Robustness: every list-shaped value consumed here — the top-level
    transaction_log/rosters_raw arguments, each tx's "moves", and each
    team's "players" — is routed through `_as_dict_list`, which handles
    BOTH a value that isn't a list at all (e.g. `"moves": true` or
    `"players": 7` — note `x.get(key) or []` alone does NOT catch this,
    since `or []` only substitutes on a *falsy* value, and a JSON
    boolean/number is truthy) AND a list containing non-dict items (CBS is
    known to put `None` in `moves` for voided/cancelled transactions).
    Single-dict fields (`move["player"]`, a roster `player`) keep their own
    `isinstance(..., dict)` guard since a list is not expected there. Every
    malformed or unexpected shape anywhere in this payload degrades to an
    empty (or partial) keepers list — never an exception — for any input.
    """
    # Build a name -> {position, team} lookup from the roster payload so we
    # can enrich whatever player identifier the transaction log uses.
    player_lookup: dict[str, dict] = {}
    for team in _as_dict_list(rosters_raw):
        for player in _as_dict_list(team.get("players")):
            full_name = player.get("fullname") or player.get("full_name")
            if not full_name:
                continue
            player_lookup[full_name] = {
                "position": player.get("position") or "",
                "team": player.get("pro_team") or "",
            }

    keepers: list[dict] = []
    for tx in _as_dict_list(transaction_log):
        for move in _as_dict_list(tx.get("moves")):
            move_type = str(move.get("type") or "").lower()
            is_keeper = "keeper" in move_type or bool(move.get("is_keeper"))
            if not is_keeper:
                continue
            player = move.get("player")
            if not isinstance(player, dict):
                continue
            full_name = player.get("fullname") or player.get("full_name") or ""
            if not full_name:
                continue
            looked_up = player_lookup.get(full_name, {})
            keepers.append({
                "player_name": full_name,
                "position": player.get("position") or looked_up.get("position", ""),
                "team": player.get("pro_team") or looked_up.get("team", ""),
            })
    return keepers
