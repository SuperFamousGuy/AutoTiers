"""ESPN unofficial-API client for league-linking flows.

Public leagues are reachable anonymously. Private leagues require two cookies
the user pastes from their browser: SWID (a UUID-ish identifier) and
espn_s2 (a long opaque session blob).

We attach both cookies and request three views in a single call:
  view=mSettings   → name, size, scoringSettings
  view=mTeam       → teams + keepers (under draftStrategy)
  view=mDraftDetail → completed draft picks
"""
import httpx
from app.integrations.types import LeagueData


class EspnAuthRequired(Exception):
    """ESPN returned 401/403 — the league is private and cookies are missing or expired."""


_BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"
_VIEWS = "view=mSettings&view=mTeam&view=mDraftDetail"

# ESPN rejects requests that look like a script (default httpx UA). Use a
# regular browser UA so the API call goes through.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def fetch_league(
    league_id: str,
    season: int,
    swid: str | None,
    espn_s2: str | None,
) -> LeagueData:
    url = f"{_BASE_URL}/seasons/{season}/segments/0/leagues/{league_id}?{_VIEWS}"
    headers: dict[str, str] = {
        "User-Agent": _BROWSER_UA,
        "Accept": "application/json",
    }
    # Build the Cookie header by hand — httpx URL-encodes cookie values via
    # its Cookies object, which mangles the braces in SWID. ESPN wants the
    # raw values (e.g. `SWID={ABCD-1234-...}; espn_s2=...`).
    parts = []
    if swid:
        parts.append(f"SWID={swid}")
    if espn_s2:
        parts.append(f"espn_s2={espn_s2}")
    if parts:
        headers["Cookie"] = "; ".join(parts)

    # follow_redirects=True so benign redirects (http→https canonicalization,
    # CDN/load-balancer hops) are transparently followed instead of leaving a
    # 3xx body for resp.json() to choke on. httpx defaults this to False.
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        # 401/403 are the explicit auth-required cases. ESPN also bounces
        # private leagues (via a 3xx) to their HTML login page; now that we
        # follow redirects, that arrives as a non-JSON 200 body rather than a
        # raw 3xx. Detect both and surface the same "paste your cookies" hint
        # instead of letting resp.json() blow up with an opaque JSONDecodeError.
        if resp.status_code in (401, 403):
            raise EspnAuthRequired("ESPN rejected the request — league may be private and cookies missing/expired")
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            raise EspnAuthRequired("ESPN rejected the request — league may be private and cookies missing/expired")

    settings = data.get("settings") or {}
    players_by_id: dict[int, dict] = {p["id"]: p for p in (data.get("players") or [])}

    keepers: list[dict] = []
    for team in data.get("teams") or []:
        for k in (team.get("draftStrategy") or {}).get("keepers") or []:
            p = players_by_id.get(k.get("playerId"))
            if p is None:
                continue
            keepers.append({
                "player_name": p.get("fullName") or "",
                "position": _POSITION_BY_ID.get(p.get("defaultPositionId"), ""),
                "team": _PRO_TEAM_BY_ID.get(p.get("proTeamId"), ""),
            })

    adp_json: dict | None = None
    draft = data.get("draftDetail") or {}
    if draft.get("drafted"):
        adp_json = {}
        for pick in draft.get("picks") or []:
            p = players_by_id.get(pick.get("playerId"))
            if p is None or not p.get("fullName"):
                continue
            adp_json[p["fullName"]] = float(pick.get("overallPickNumber") or 0)

    return LeagueData(
        league_id=str(data.get("id") or league_id),
        name=settings.get("name") or f"ESPN league {league_id}",
        season=season,
        raw_scoring=settings.get("scoringSettings") or {},
        league_size=int(settings.get("size") or 12),
        keepers=keepers,
        adp_json=adp_json,
    )


# Minimal subset — covers the offense positions AutoTiers ranks.
# Both 3 and 4 map to "WR" because ESPN historically uses both slot ids for receivers.
_POSITION_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "WR", 5: "TE", 16: "DST", 17: "K"}

# Subset of ESPN's pro-team id → abbreviation. Unknown ids map to empty string.
_PRO_TEAM_BY_ID = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA",
    16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI",
    23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR",
    30: "JAX", 33: "BAL", 34: "HOU",
}
