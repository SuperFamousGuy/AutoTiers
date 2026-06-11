# Kicker: Dome + Elevation Rules — Design

## Goal
Add two new K-position scoring rules: a modest boost for kickers whose home venue is a dome or retractable-roof stadium, and a well-supported boost for the Denver Broncos kicker due to altitude.

## Approach
Both rules follow the existing pattern: add a boolean field to `PlayerContext`, derive it from `player.team` in `generate.py`, and add a `Rule` entry in `builtin_rules.py`. No DB migrations or schema changes required — both fields are computed at tier-generation time from static lookup tables.

## User-facing impact
- Dome kickers (11 teams) receive a +4% multiplier to their adjusted score.
- The Broncos kicker receives a +5% multiplier.
- Both rules appear in the `rules_applied` and `rule_applications` breakdown on each TieredPlayer.
- Users can toggle/weight both rules from the Rules panel like any other rule.

## Code-facing impact

### `backend/app/engine/rules.py` — `PlayerContext`
Add two optional boolean fields:
```python
plays_in_dome: Optional[bool] = None
is_denver_kicker: Optional[bool] = None
```

### `backend/app/api/generate.py` — context computation
Add static lookup sets near `_compute_bad_offense_teams`:
```python
# Fixed domes + retractable roofs. Retractable-roof closure is ~90% of home
# games in cold/rain months; treating them as "dome" is the standard industry
# approximation used by ETR, Footballguys, and PFF tier tools.
DOME_TEAMS: frozenset[str] = frozenset({
    "DET", "MIN", "NO", "LV",          # fixed domes
    "DAL", "HOU", "IND", "ARI", "ATL", # retractable roofs
    "LAR", "LAC",                       # SoFi (roofed, partially open sides)
})
ELEVATION_TEAM = "DEN"
```

In the player loop (position-gated to K):
```python
plays_in_dome: Optional[bool] = None
if player.position == "K":
    plays_in_dome = player.team in DOME_TEAMS

is_denver_kicker: Optional[bool] = None
if player.position == "K":
    is_denver_kicker = player.team == ELEVATION_TEAM
```

Pass both to `PlayerContext(...)`.

### `backend/app/engine/builtin_rules.py`
Add two rules to `BUILTIN_RULES`:
```python
Rule(
    name="Dome Kicker",
    conditions=[RuleCondition(field="plays_in_dome", operator="==", value=True)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.04),
    description=(
        "Boosts kickers whose home venue is a dome or retractable-roof stadium "
        "(DET, MIN, NO, LV, DAL, HOU, IND, ARI, ATL, LAR, LAC). "
        "Controlled environment eliminates wind/cold penalties. "
        "Signal is modest across sources; +4% at default weight."
    ),
    positions=["K"],
),
Rule(
    name="Mile High Kicker",
    conditions=[RuleCondition(field="is_denver_kicker", operator="==", value=True)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.05),
    description=(
        "Boosts the Denver Broncos kicker for the structural altitude advantage "
        "at ~5,280 ft (~5 yards of extra range per Burke/Advanced Football Analytics). "
        "8 home games at elevation per season; visiting kickers only benefit "
        "for one game so no season-long boost warranted for them. +5% at default weight."
    ),
    positions=["K"],
),
```

## Math / statistical claims
- **Dome**: PFF 2024 reports dome kickers average 8.7 fpg vs 8.3 league average (+0.4 fpg, ~+5%). Fantasy Index 2005–2014 found outdoor kickers averaged +1 pt/season over dome kickers. Klein 2016–2017 found distributions "nearly identical." Choosing +4% (conservative, below PFF's implied signal) acknowledges the conflicting evidence.
- **Denver**: Burke/Advanced Football Analytics 2013 controlled study: altitude adds ~5 yards of range. 50+ yd FG rate in Denver games ~0.8/game vs league average ~0.63/game. Confidence high. +5% is well within the supported range (+4–6%).

## FF heuristic basis
See `autotiers-ff-knowledge` entries: "Dome Kicker Advantage" and "Denver Altitude Kicker Boost" (added by researcher 2026-06-10).

## Out of scope
- Per-game dome/open status for retractable-roof stadiums (would require game-schedule API integration; approximating as always-dome is standard industry practice).
- Visiting-kicker elevation bonus for road games at Denver (single-game benefit; not meaningful for season-long redraft ranking).
- Weather penalty for outdoor cold-weather teams (AFC North, AFC East, NFC North) — complementary but separate rule; file as follow-up issue.
- SoFi reclassification (partially open sides; current: treated as dome): revisit if data shows divergence.

## Open questions
None blocking implementation. One assumption to document: SoFi is included as dome-like because the roof covers the field and wind is substantially reduced; if user disagrees, LAR/LAC can be removed from `DOME_TEAMS`.
