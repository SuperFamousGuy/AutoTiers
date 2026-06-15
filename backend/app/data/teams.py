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

# Teams whose home venue is a consistently cold outdoor stadium where Nov–Jan
# game-time temperatures and wind regularly impair field goal accuracy.
# Source rationale: Burke/Advanced Football Analytics 2012 — cold at 30°F
# imposes a ~5 yd FG distance penalty; FG% drops from ~87% (warm) to ~80.2%
# at ≤30°F. PFF: 20+ mph wind reduces kicker output from 8.3 to 7.7 fpg.
# Excludes all DOME_TEAMS (controlled environment, no overlap) and DEN
# (altitude advantage is modeled separately by ELEVATION_TEAM / Mile High Kicker).
# Used by the "Cold-Weather Kicker" builtin rule (app.engine.builtin_rules).
COLD_WEATHER_TEAMS: frozenset[str] = frozenset({
    "GB",   # avg Nov-Jan 38.1°F — coldest outdoor home venue in the league
    "BUF",  # misery index rank #1 (cold + wind combined)
    "CLE",  # misery index rank #3
    "PIT",  # misery index rank #4
    "CHI",  # misery index rank #5
    "NE",   # misery index rank #7
    "KC",   # misery index rank #8; second-windiest outdoor city
    "CIN",  # misery index rank #10
})
