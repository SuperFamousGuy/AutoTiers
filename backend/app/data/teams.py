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


# Teams whose home stadium is a fully enclosed dome or retractable-roof facility.
# Retractable-roof closure is the norm for cold/rain games (~90 % of home games
# in adverse-weather months), so treating these as "dome" is the standard industry
# approximation used by ETR, Footballguys, and PFF kicker tier tools.
# Used by the "Dome Kicker" builtin rule (app.engine.builtin_rules).
DOME_TEAMS: frozenset[str] = frozenset({
    "DET", "MIN", "NO", "LV",           # fixed domes
    "DAL", "HOU", "IND", "ARI", "ATL",  # retractable roofs
    "LAR", "LAC",                        # SoFi Stadium (roofed; partially open sides)
})

# Team that plays home games at meaningful altitude (~5,280 ft above sea level).
# The structural elevation advantage for the home kicker is ~5 yards of extra
# range per Burke/Advanced Football Analytics (2013). Visiting kickers benefit
# for one game only — not enough for a season-long redraft boost.
# Used by the "Mile High Kicker" builtin rule (app.engine.builtin_rules).
ELEVATION_TEAM: str = "DEN"
