"""Canonical set of NFL team abbreviations.

Used by the favorites API to validate `favorite_teams` entries against
the actual 32-team league. Treat this as the single source of truth;
the frontend's team-grid UI should also draw from it (via an endpoint
or a duplicated constant — duplication is acceptable if synced when
this set ever changes).
"""

NFL_TEAMS: frozenset[str] = frozenset({
    "ARI", "ATL", "BAL", "BUF",
    "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV",  "MIA",
    "MIN", "NE",  "NO",  "NYG",
    "NYJ", "PHI", "PIT", "SEA",
    "SF",  "TB",  "TEN", "WAS",
})


def is_valid_team(code: str) -> bool:
    """Whether `code` is a known canonical NFL team abbreviation.

    Empty / whitespace-only strings return False (Class 2 guard).
    """
    if not code or not code.strip():
        return False
    return code in NFL_TEAMS
