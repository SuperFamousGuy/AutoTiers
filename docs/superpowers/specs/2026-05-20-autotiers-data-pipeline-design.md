# AutoTiers Data Pipeline — Design Spec
**Date:** 2026-05-20
**Status:** Approved
**Parent spec:** `2026-05-19-autotiers-design.md`

---

## Overview

Replace the stub `DataFetcher` with a real pipeline that pulls live data from four sources, normalizes it against a single player identity, persists it idempotently, and surfaces per-source freshness/errors via the existing `/api/data/status` endpoint. Also wires in the two play-by-play-derived stats (`expected_tds`, `red_zone_looks`) and adds the two BUILTIN_RULES that were deferred from Plan 1 because they depend on those fields.

After Plan 2, the API stops returning seed data and starts returning real players ranked from real projections.

---

## Architecture

### Module layout

```
backend/app/data/
├── fetcher.py                # DataFetcher.refresh_all() — orchestrator (existing, rewritten)
├── sources/
│   ├── __init__.py
│   ├── base.py               # SourceFetcher protocol + SourceResult dataclass
│   ├── sleeper.py            # Master player list
│   ├── nfl_data.py           # Historical stats (seasonal + PBP-derived)
│   ├── espn.py               # Current-season projections
│   └── fantasypros.py        # Consensus projections + ADP
├── matching.py               # Normalize names, fuzzy-match (name, team, position)
└── status.py                 # Read/write helpers for DataSourceStatus

backend/app/models/
└── data_source_status.py     # NEW — one row per source, persisted refresh state

backend/app/engine/
└── builtin_rules.py          # Add 2 new rules: TD regression, Red Zone Premium
```

### Data source roles

| Source | Role | Auth | Cost | Library |
|---|---|---|---|---|
| Sleeper | Master player list + cross-ID map + dynasty ADP | None | Free | `httpx` |
| nfl_data_py | Historical stats (seasonal + PBP) | None | Free | `nfl_data_py` |
| ESPN unofficial | Current-season projections | None | Free | `httpx` |
| FantasyPros | Consensus projections + redraft ADP | None | Free | `httpx` (HTML scrape) |

### Player ID strategy

**Sleeper is the master.** Sleeper's `/v1/players/nfl` endpoint returns every active NFL player with their Sleeper ID plus mappings to `gsis_id`, `espn_id`, `yahoo_id`, full name, team, position, age, years of experience. We:

- Use **Sleeper's `player_id`** as our `Player.id` (existing column, already `String`)
- Store `gsis_id` and `espn_id` on `Player` (new columns) so the other fetchers can look them up directly
- FantasyPros has no IDs — fuzzy-match against the populated player table on `(normalized_name, team, position)`

### Refresh orchestration

```
refresh_all():
    sleeper_result = await sleeper.fetch(db)         # serial — must come first
    if sleeper_result.error:
        # bail — every downstream source depends on the player table
        return {sleeper: sleeper_result, ...all_others: skipped}

    results = await asyncio.gather(
        nfl_data.fetch(db),
        espn.fetch(db),
        fantasypros.fetch(db),
        return_exceptions=True,
    )
    # each gets its own transaction inside .fetch()
    persist_status(db, all_results)
    return all_results
```

### Failure semantics

- Each `SourceFetcher.fetch()` opens its own DB session and commits independently
- If a source raises, the exception is caught, logged, and persisted to `data_source_status.last_error`
- `data_source_status.last_updated` is only bumped on success
- The frontend (and the data-as-of timestamp in `/api/generate`) reads from `last_updated` to surface staleness

### Idempotency

All upserts follow the pattern:
```python
existing = await db.scalar(select(Model).where(Model.key == value))
if existing:
    update_fields(existing, new_data)
else:
    db.add(Model(**new_data))
```

Slower than `ON CONFLICT` but works on both Postgres (prod) and SQLite (tests) without dialect branching. Acceptable cost — refresh runs at most once a day.

### Inactive players

Add `Player.active: bool` (default `True`). On each Sleeper refresh, players present in the response are marked active; players absent are marked inactive. Records are never deleted — preserves historical stats and ADP rows for traded/retired players.

---

## Database Schema Changes

```sql
-- New columns on players
ALTER TABLE players ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE players ADD COLUMN gsis_id VARCHAR(20);
ALTER TABLE players ADD COLUMN espn_id VARCHAR(20);
CREATE INDEX ix_players_gsis_id ON players (gsis_id);
CREATE INDEX ix_players_espn_id ON players (espn_id);

-- New table
CREATE TABLE data_source_status (
    source VARCHAR(30) PRIMARY KEY,        -- 'sleeper' | 'nfl_data_py' | 'espn' | 'fantasypros'
    last_updated TIMESTAMP,                -- last successful run
    last_attempted TIMESTAMP NOT NULL,     -- last run regardless of outcome
    last_error TEXT,                       -- error message from last attempt, NULL on success
    rows_upserted INTEGER NOT NULL DEFAULT 0
);
```

One Alembic migration: `002_data_pipeline.py`.

---

## Source Implementations

### `sources/base.py`

```python
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class SourceResult:
    source: str
    rows_upserted: int
    last_updated: datetime
    error: str | None = None

class SourceFetcher(Protocol):
    name: str
    async def fetch(self, db: AsyncSession) -> SourceResult: ...
```

### `sources/sleeper.py`

- **Endpoint:** `GET https://api.sleeper.app/v1/players/nfl` (returns full JSON map)
- **Filters:** only `position in {QB, RB, WR, TE, K, DST}` and `team is not None`
- **Upserts:** `Player.id` (Sleeper ID), `name`, `position`, `team`, `age`, `years_exp`, `gsis_id`, `espn_id`, `active=True`
- Players in DB but not in response → set `active=False`
- **ADP:** Sleeper has dynasty ADP at `GET https://api.sleeper.app/v1/players/nfl/trending/add` (or via league-aggregated ADP) — for dynasty, write to `ADPData(format="dynasty", adp_source="sleeper")`

### `sources/nfl_data.py`

- **Library:** `nfl_data_py` (already in pyproject deps)
- **Seasonal stats:** `nfl_data_py.import_seasonal_data([prior_season])` — returns a pandas DataFrame
- **Snap counts:** `import_snap_counts([prior_season])` for `snap_pct`
- **Play-by-play (for PBP-derived fields):** `import_pbp_data([prior_season])`
  - `expected_tds` = sum of `td_prob` for each play where the player is a receiver or rusher and the play is inside the 20-yard line
  - `red_zone_looks` = count of plays in red zone (yardline_100 ≤ 20) where the player is targeted or carried
- **Match by `gsis_id`:** the seasonal data uses NFL's gsis_id, which we now have on `Player` from Sleeper
- **Upserts** into `player_stats` for `season = prior_season`

### `sources/espn.py`

- **Endpoint:** ESPN Fantasy API public-but-unofficial — `GET https://fantasy.espn.com/apis/v3/games/ffl/seasons/{current_season}/segments/0/leaguedefaults/3?view=kona_player_info`
  - The `kona_player_info` view returns projected fantasy points for all players, per scoring format, for the current season
- **Format mapping:** ESPN encodes scoring via `scoringPeriodId` and stat-set headers; for each player we pull projections for standard, half-PPR, PPR (TE Premium not supported by ESPN → write to `ppr` only)
- **Match by `espn_id`** (we have it on `Player` from Sleeper)
- **Upserts** into `projections` with `source="espn"`

### `sources/fantasypros.py`

- **Endpoints (HTML scrape):**
  - Projections: `https://www.fantasypros.com/nfl/projections/{position}.php?scoring={STD|HALF|PPR}`
  - ADP: `https://www.fantasypros.com/nfl/adp/{format}.php` (format = `overall`, `half-point-ppr`, `ppr`)
- **Parser:** BeautifulSoup4 (new dep) — tables have stable IDs (`#data` table is the players table)
- **Matching:** rows are name + team + position only; pass through `matching.fuzzy_match()` to resolve to `Player.id`
- **Unmatched rows:** logged with name/team/position, NOT silently dropped (a count gets returned in `SourceResult` for `/api/data/status`)
- **Upserts** projections (`source="fantasypros"`) and ADP rows

### New Dependencies

Added to `pyproject.toml`:
- `nfl_data_py>=0.3` — already in pyproject; no change needed
- `rapidfuzz>=3.0` — fuzzy string matching (MIT)
- `beautifulsoup4>=4.12` — HTML parsing for FantasyPros (MIT)
- `lxml>=5.0` — fast HTML parser backend for bs4 (BSD)

Added to dev deps:
- `respx>=0.21` — httpx mock library for fetcher tests

### `matching.py`

```python
def normalize_name(name: str) -> str:
    """Lowercase, strip Jr/Sr/II/III/IV, strip punctuation, collapse spaces."""

async def fuzzy_match(
    db: AsyncSession,
    name: str, team: str, position: str,
    threshold: int = 90,
) -> Player | None:
    """
    1. Exact (normalized_name, team, position) — return immediately.
    2. (normalized_name, position) ignoring team — for traded players.
    3. rapidfuzz token_set_ratio on normalized_name within position bucket — return if score ≥ threshold.
    """
```

`rapidfuzz` added as new dep.

---

## Two New Built-in Rules

Both depend on PBP-derived fields now being populated.

### TD Regression

```python
Rule(
    name="TD Regression (positive)",
    conditions=[
        RuleCondition(field="actual_tds_above_expected", operator=">=", value=3),
    ],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
)

Rule(
    name="TD Regression (negative)",
    conditions=[
        RuleCondition(field="actual_tds_above_expected", operator="<=", value=-3),
    ],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.10),
)
```

Adds a new field `actual_tds_above_expected: Optional[float]` to the `PlayerContext` dataclass. Computed in `_run_generate` as `actual_tds - expected_tds` when both are present, else `None`. The rules engine already returns False for any condition whose field is `None` (existing behavior), so the rule simply doesn't fire when PBP data isn't loaded for a player.

### Red Zone Usage Premium

```python
Rule(
    name="Red Zone Usage Premium",
    conditions=[
        RuleCondition(field="red_zone_looks", operator=">=", value=25),
    ],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.07),
)
```

This brings BUILTIN_RULES from 16 → 18, matching the design spec's "18 built-in rules at launch."

---

## API Changes

### `/api/data/status` — fleshed out

Before:
```json
{"nfl_data_py": "stub", "fantasypros": "stub", "espn": "stub", "sleeper": "stub"}
```

After:
```json
{
  "sleeper":      { "last_updated": "2026-05-20T03:00:00Z", "last_attempted": "2026-05-20T03:00:00Z", "last_error": null,                     "rows_upserted": 1542 },
  "nfl_data_py":  { "last_updated": "2026-05-20T03:00:12Z", "last_attempted": "2026-05-20T03:00:12Z", "last_error": null,                     "rows_upserted": 612 },
  "espn":         { "last_updated": "2026-05-19T03:00:08Z", "last_attempted": "2026-05-20T03:00:09Z", "last_error": "HTTP 503 from ESPN",     "rows_upserted": 0 },
  "fantasypros":  { "last_updated": "2026-05-20T03:00:15Z", "last_attempted": "2026-05-20T03:00:15Z", "last_error": null,                     "rows_upserted": 580 }
}
```

`last_updated` only advances on success; `last_attempted` advances every run.

### `/api/data/refresh` — same contract, real work

`POST /api/data/refresh` (still admin-gated by `ADMIN_API_KEY`) now calls the real `DataFetcher.refresh_all()`. Returns the same shape as `/api/data/status` reflecting this run's results.

### `/api/generate` — `data_as_of` becomes meaningful

Currently `data_as_of` is `str(date.today())` (the request time, which lies about freshness). Change to: the **minimum `last_updated` across the four sources** — surfaces the oldest underlying data. If any source has never succeeded, returns its `null` (frontend will show "data may be incomplete").

---

## Testing

### Fixtures

```
backend/tests/fixtures/
├── sleeper_players.json          # ~50 trimmed players covering all positions
├── sleeper_dynasty_adp.json
├── nfl_data_seasonal.csv         # ~50 rows
├── nfl_data_snap_counts.csv
├── nfl_data_pbp.csv              # ~200 plays — enough to compute RZ + expected TDs
├── espn_projections.json         # ESPN API response shape
├── fantasypros_projections_qb.html
├── fantasypros_projections_rb.html
├── fantasypros_projections_wr.html
├── fantasypros_projections_te.html
└── fantasypros_adp_ppr.html
```

### Test files

- `tests/test_sources/test_sleeper.py` — fetcher round-trips fixture → DB, active toggling
- `tests/test_sources/test_nfl_data.py` — seasonal upsert + PBP-derived field computation
- `tests/test_sources/test_espn.py` — projection upsert per format
- `tests/test_sources/test_fantasypros.py` — HTML parse + fuzzy match + unmatched logging
- `tests/test_sources/test_matching.py` — name normalization edge cases (Jr/III/punctuation)
- `tests/test_refresh.py` — end-to-end: all 4 fetchers run against fixtures, DB state asserted, status table populated
- `tests/test_refresh_failures.py` — one fetcher raises; others still commit; status table reflects per-source errors
- `tests/test_api_data_status.py` — `/api/data/status` returns the new richer shape

All HTTP calls go through `respx.mock`. `nfl_data_py` calls are monkey-patched to read fixture CSVs from `tests/fixtures/`.

### Live smoke script (optional, not in CI)

`backend/scripts/smoke_live.py` runs all 4 fetchers against real APIs for manual end-to-end verification. Not part of pytest.

---

## Out of Scope (deferred to Plan 2.5 or later)

- TeamContext data (`off_line_grade`, `new_head_coach`) — PFF is paid and free OL ranking sources are unreliable. The two rules depending on this (`New Team Penalty`, `New Head Coach`) stay dormant. Will be addressed by a small follow-up that loads a hand-maintained `team_context.json` once per offseason.
- Real-time mid-season player news / injury designations
- ADP from sources other than the four listed
- Historical multi-season stat trends (we pull prior season only)
- Data validation / anomaly detection (e.g., catching a feed regression where projections drop to 0)

---

## Migration / Rollout

1. Apply migration `002_data_pipeline.py` (new columns + new table)
2. Deploy backend with new fetcher code
3. Trigger `POST /api/data/refresh` once manually — populates real data, replaces seed
4. Scheduler picks up the rest (weekly June-July, daily August-September)

Existing seed data in dev environments stays untouched until someone hits `/api/data/refresh` or wipes the volume — the upserts will overwrite seed rows in place when real data arrives for the same player IDs (Sleeper IDs differ from seed IDs like `wr_chase`, so seeded players just become orphaned/inactive after a real refresh).
