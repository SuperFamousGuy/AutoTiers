# AutoTiers Advanced Rules — Design Spec

**Date:** 2026-05-25
**Status:** Approved
**Parent specs:** `2026-05-19-autotiers-design.md`, `2026-05-20-autotiers-data-pipeline-design.md`

---

## Overview

Add four new built-in rules to AutoTiers, each requiring different data infrastructure beyond what currently exists:

1. **370 Touches** — RBs with 370+ touches last year regress
2. **Year After the Year After** — players injured 2 seasons ago bounce back
3. **Bad Offense** — players on teams with 3-year poor scoring history are penalized
4. **Follow the Money** — players paid above-market are guaranteed usage

Two rules (1 and 2) extend existing data structures. Two rules (3 and 4) require new data sources and storage tables. The work is broken into 4 sequential phases, each shippable as its own PR.

---

## The Four Rules

### Rule 1: 370 Touches

**Concept:** RBs who absorb 370+ touches (rushes + receptions) in a season have historically shown decline the following year — wear-and-tear is real.

**Condition:** `position == "RB" AND prior_touches >= 370`

**Effect:** multiplier `0.90` (`-10%` at default weight)

**Computed field on `PlayerContext`:** `prior_touches: Optional[int]`

Computation (in `_run_generate`):

```python
prior_touches = None
if player.position == "RB" and stat is not None:
    prior_touches = (stat.rush_att or 0) + (stat.receptions or 0)
```

Only computed for RBs to keep the rule scoped. Definition uses carries + receptions (modern interpretation) — captures pass-catching workhorses like CMC and Ekeler-type backs, not just traditional bell-cows.

**Data dependencies:** none new. Uses existing `PlayerStat.rush_att` and `PlayerStat.receptions` from prior season.

---

### Rule 2: Year After the Year After

**Concept:** Soft-tissue injuries (hamstrings, ACLs, ankles) take a full year to fully recover from. Players returning to play after a missed season are often still not at full strength. The "Year After the Year After" — two seasons removed from the injury — is when they're truly back and frequently undervalued by the market.

**Condition:** `position in {"RB", "WR"} AND injured_two_years_ago == True`

**Effect:** multiplier `1.10` (`+10%` at default weight) — this is a *bonus*

**Computed field on `PlayerContext`:** `injured_two_years_ago: Optional[bool]`

Computation:

```python
injured_two_years_ago = None
if player.position in ("RB", "WR"):
    two_seasons_ago = current_year - 2
    two_yrs_ago_stat = next(
        (s for s in player.stats if s.season == two_seasons_ago),
        None,
    )
    if two_yrs_ago_stat is not None:
        injured_two_years_ago = (two_yrs_ago_stat.games_played or 0) < 12
```

Threshold matches the existing `Injury History` rule (`games_played < 12`).

**Data dependencies:** requires `PlayerStat` rows for season `N-2` (where N is current draft year). The current `nfl_data_py` fetcher loads only one prior season (`N-1`). Needs to be extended to load multiple seasons.

**Positions:** RB and WR only. QBs recover differently (arm/shoulder injuries follow different patterns); TEs are too few to matter at a fantasy-positional level.

---

### Rule 3: Bad Offense

**Concept:** Players on teams with chronically bad offenses score fewer fantasy points by structural inevitability — no TDs means no points, no consistent scoring opportunities means low ceilings. A 3-year window of bad offense is a strong signal the structural issue persists.

**Condition:** `bad_offense_team == True` (position scope encoded in field computation — see below)

**Effect:** multiplier `0.93` (`-7%` at default weight)

**Computed field on `PlayerContext`:** `bad_offense_team: Optional[bool]` — computed `True` only for offensive skill players (QB/RB/WR/TE) on bottom-8 teams; `None` for K/DST so the rule doesn't fire on them.

**Definition of "bad offense":** team is in the **bottom 8 of 32 NFL teams by 3-year average points scored**.

Computation (at refresh time, after team_seasons table is populated):

```python
# Aggregate 3-year avg points per team
team_avg = {}
for team in all_teams:
    recent = [ts.points_scored for ts in team.seasons if ts.season >= current_year - 3]
    if len(recent) >= 2:  # at least 2 of 3 seasons present
        team_avg[team.code] = sum(recent) / len(recent)

# Bottom 8
sorted_teams = sorted(team_avg.items(), key=lambda kv: kv[1])
bad_offense_teams = {code for code, _ in sorted_teams[:8]}
```

Then per player:

```python
bad_offense_team = None
if player.position in ("QB", "RB", "WR", "TE"):
    bad_offense_team = player.team in bad_offense_teams
```

K and DST stay at `None` so the rule doesn't apply to them.

**Data dependencies:** new ORM model `TeamSeason` storing annual team scoring. Sourced from `nfl_data_py.import_schedules()` (which has per-game points; aggregated to season totals).

---

### Rule 4: Follow the Money

**Concept:** Front offices don't pay players above-market contracts to ride the bench. A player with a top-tier cap hit for their position has a guarantee of usage that lower-paid players can't claim — even after a slow start.

**Condition:** `above_market_contract == True` (all positions where contracts apply)

**Effect:** multiplier `1.05` (`+5%` at default weight) — bonus for usage assurance

**Computed field on `PlayerContext`:** `above_market_contract: Optional[bool]`

**Definition of "above market":** player's current-year `cap_hit > position_median × 1.5` for that season.

Computation:

```python
# Compute position median cap hit per season (done once per refresh)
position_median = {}
for pos in ("QB", "RB", "WR", "TE"):
    contracts_this_year = [c for c in all_contracts if c.season == current_year and c.player.position == pos]
    if contracts_this_year:
        sorted_hits = sorted(c.cap_hit for c in contracts_this_year)
        position_median[pos] = sorted_hits[len(sorted_hits) // 2]

# Per player
above_market_contract = None
if player_contract is not None and player.position in position_median:
    above_market_contract = player_contract.cap_hit > position_median[player.position] * 1.5
```

**Data dependencies:** new ORM model `PlayerContract` and a new `SpotracFetcher` source. Player matching via `fuzzy_match`. Contract data fetched from `https://www.spotrac.com/nfl/contracts/`.

**Note:** Spotrac scraping is TOS gray-area but widely practiced by fantasy tools. A polite User-Agent and reasonable refresh cadence (weekly, not hourly) are required. If Spotrac blocks us, OverTheCap is the fallback.

---

## Architecture Changes

### New ORM models

```python
# backend/app/models/team_season.py
class TeamSeason(Base):
    __tablename__ = "team_seasons"
    __table_args__ = (UniqueConstraint("team", "season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team: Mapped[str] = mapped_column(String(5), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    points_scored: Mapped[int] = mapped_column(Integer, nullable=False)
    points_rank: Mapped[Optional[int]] = mapped_column(Integer)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
```

```python
# backend/app/models/player_contract.py
class PlayerContract(Base):
    __tablename__ = "player_contracts"
    __table_args__ = (UniqueConstraint("player_id", "season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_hit: Mapped[float] = mapped_column(Float, nullable=False)
    base_salary: Mapped[Optional[float]] = mapped_column(Float)
    signing_bonus: Mapped[Optional[float]] = mapped_column(Float)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
```

Two new tables. Each created via a new Alembic migration.

### nfl_data_py fetcher refactor

Currently loads one season:

```python
class NflDataFetcher:
    def __init__(self, season: int):
        self.season = season
```

Refactor to load N prior seasons (default 3 to support 3-year team offense averages):

```python
class NflDataFetcher:
    def __init__(self, prior_seasons: int = 3, latest_season: int | None = None):
        self.latest_season = latest_season or (datetime.utcnow().year - 1)
        self.seasons_to_load = [self.latest_season - i for i in range(prior_seasons)]
```

For each season in `seasons_to_load`, fetch seasonal data and PBP, upsert PlayerStat rows. Also fetch schedule data (for team scoring) and upsert TeamSeason rows.

### New SpotracFetcher

Modeled on FantasyProsFetcher. Scrapes HTML tables by position. Uses `fuzzy_match` to resolve player names. Stores rows in `player_contracts` table with `source` implicit (only one contract source for now).

### PlayerContext new fields

```python
@dataclass
class PlayerContext:
    # ... existing fields ...
    prior_touches: Optional[int] = None
    injured_two_years_ago: Optional[bool] = None
    bad_offense_team: Optional[bool] = None
    above_market_contract: Optional[bool] = None
```

All default to None for backward compat with existing test constructions.

### Generate endpoint computations

In `_run_generate`, after building each `PlayerContext`, compute the four new fields per the formulas above. The `bad_offense_teams` set and `position_median` map are computed once at the start of the request (not per-player).

---

## Data Sources Summary

| Source | New / Existing | Purpose |
|---|---|---|
| `nfl_data_py` seasonal + PBP | Existing (refactor to multi-season) | Rules 1, 2 — PlayerStat history |
| `nfl_data_py` schedules | New use of existing dep | Rule 3 — team scoring history → TeamSeason |
| Spotrac scrape | New | Rule 4 — PlayerContract |

---

## Schema Changes

Two new Alembic migrations:

- `003_team_seasons_and_contracts.py` — creates `team_seasons` and `player_contracts` tables

(Single migration covers both since they're added at the same time architecturally.)

No changes to `players`, `player_stats`, `projections`, `adp_data`, `team_context`, `data_source_status`. The new tables are additive.

---

## Phasing

This work is decomposed into four sequential PRs. Each PR is independently shippable and adds one rule. Earlier phases lay infrastructure used by later phases.

### Phase 1: 370 Touches

**Scope:** smallest. Adds `prior_touches` to PlayerContext and one new rule.

**Files touched:**
- `backend/app/engine/rules.py` — `PlayerContext.prior_touches`
- `backend/app/engine/builtin_rules.py` — new rule
- `backend/app/api/rules.py` — `_CATEGORIES` mapping
- `backend/app/api/generate.py` — compute `prior_touches`
- `backend/tests/test_rules.py` — rule tests
- `backend/tests/test_api.py` — integration test

**Effort:** ~2 hours. Estimated PR size: ~150 lines.

### Phase 2: Year After the Year After

**Scope:** moderate. Refactors nfl_data_py fetcher to load multiple seasons + new rule.

**Files touched:**
- `backend/app/data/sources/nfl_data.py` — multi-season loading
- `backend/tests/test_sources/test_nfl_data.py` — updated tests
- `backend/app/engine/rules.py` — `PlayerContext.injured_two_years_ago`
- `backend/app/engine/builtin_rules.py` — new rule
- `backend/app/api/rules.py` — `_CATEGORIES`
- `backend/app/api/generate.py` — compute the field by looking up `season = current_year - 2`
- `backend/tests/test_rules.py`, `test_api.py` — tests

**Effort:** ~4-6 hours. PR size: ~300 lines.

### Phase 3: Bad Offense

**Scope:** significant. New `TeamSeason` model + migration + nfl_data_py schedule fetching + new rule.

**Files touched:**
- `backend/app/models/team_season.py` — new model
- `backend/app/models/__init__.py` — export
- `backend/alembic/versions/003_team_seasons_and_contracts.py` — migration (also creates player_contracts; see Phase 4)
- `backend/app/data/sources/nfl_data.py` — fetch schedules, populate TeamSeason
- `backend/app/engine/rules.py` — `PlayerContext.bad_offense_team`
- `backend/app/engine/builtin_rules.py` — new rule
- `backend/app/api/generate.py` — compute bottom-8 team set + per-player flag
- Tests across the above

**Effort:** ~6-8 hours. PR size: ~500 lines.

### Phase 4: Follow the Money

**Scope:** largest. New SpotracFetcher + `PlayerContract` model + new rule.

**Files touched:**
- `backend/app/models/player_contract.py` — new model
- `backend/app/models/__init__.py` — export
- `backend/app/data/sources/spotrac.py` — new fetcher
- `backend/app/data/fetcher.py` — orchestrator add
- `backend/app/engine/rules.py` — `PlayerContext.above_market_contract`
- `backend/app/engine/builtin_rules.py` — new rule
- `backend/app/api/generate.py` — compute median + per-player flag
- Tests across the above + new test_sources/test_spotrac.py

**Effort:** ~8-10 hours. PR size: ~600 lines.

---

## Implementation Decisions Locked

These were resolved during brainstorming and are not re-litigated during implementation:

| Decision | Choice |
|---|---|
| 370 Touches: touch definition | carries + receptions (modern) |
| Year After: positions | RB and WR only |
| Bad Offense: metric | 3-year avg points scored, bottom 8 of 32 |
| Follow the Money: source | Spotrac (with OverTheCap as fallback if blocked) |
| Follow the Money: "above market" | cap_hit > position_median × 1.5 |
| All new fields on PlayerContext | Optional[T] with default None for backward compat |
| Migration strategy | One migration (003) covering both new tables, applied in Phase 3 |

---

## Out of Scope

- UI changes to weight or surface these rules individually. Rules appear in the existing Rules panel automatically because BUILTIN_RULES is exposed via `/api/rules`. No new UI work.
- Per-team contextual modifiers (e.g., specific offensive line quality, coaching changes). Bad Offense uses team-level scoring only.
- Position-specific touch thresholds. Only RB uses 370.
- Mid-season contract restructure tracking. Spotrac fetches current cap_hit for the current season; we don't track changes.
- Rookie contracts (which are always "below market" by structure). The Follow the Money rule will fire less for rookies, which is the correct behavior.
- Historical contract analysis. Only current-year cap hit matters for current-season usage projection.
- Custom user-defined thresholds for any of these rules. Users can adjust the rule weight via low/default/high; threshold values are fixed in BUILTIN_RULES.

---

## Migration / Rollout

1. Phase 1 ships → users see new "370 Touches" rule in the panel
2. Phase 2 ships → multi-season data refresh starts loading 3 years of stats (one-time slower refresh)
3. Phase 3 ships → migration 003 applied, team_seasons populated, "Bad Offense" rule live
4. Phase 4 ships → SpotracFetcher integrated, player_contracts populated, "Follow the Money" rule live

After all four phases, BUILTIN_RULES grows from 14 → 18.

Each phase is independently revertable. If Spotrac blocks us in Phase 4, that PR can be reverted without affecting Phases 1-3.
