# AutoTiers — Design Spec
**Date:** 2026-05-19
**Status:** Approved

---

## Overview

AutoTiers is a hosted web application that generates fantasy football draft tier lists. Users configure their league settings, scoring format, and a set of heuristic rules; the system fetches current player data and projections automatically, applies the rules as score modifiers, clusters players into tiers per position, merges them into an overall draft board, and produces a downloadable CSV.

---

## Architecture

**Stack:**
- **Backend:** Python 3.12, FastAPI
- **Frontend:** React 18, TypeScript, Vite, TanStack Query, Tailwind CSS
- **Database:** PostgreSQL (Supabase-hosted)
- **Background jobs:** APScheduler (data refresh)
- **Deployment:** Railway (backend + frontend); Supabase (PostgreSQL database, separately hosted)

**Request flow:**
1. User configures settings and rules in the browser
2. Clicks Generate → `POST /api/generate` with settings + rules payload
3. Backend pulls cached player data from PostgreSQL
4. Scoring engine computes blended projected scores
5. Rules engine applies modifiers and collects flags
6. Tier engine clusters per position (Jenks Natural Breaks), then merges into overall board
7. Response returned as JSON; frontend renders tier-banded table and offers CSV download

**Data refresh schedule:**
- Weekly (June–July, pre-season)
- Daily (August–September, draft season)
- Triggered by APScheduler background job on the backend service

```
External data sources:
  nfl_data_py       — historical stats, play-by-play, rosters (free)
  FantasyPros       — consensus projections, ADP (scraped public pages)
  ESPN unofficial   — ESPN projections
  Sleeper API       — dynasty ADP, player metadata (free, no auth required)
```

---

## Database Schema

```sql
players (
  id, name, position, team, age, years_exp, last_updated
)

player_stats (
  player_id, season,
  targets, receptions, rec_yards, rec_tds,
  rush_att, rush_yards, rush_tds,
  pass_att, pass_yards, pass_tds, interceptions,
  snaps, snap_pct, carry_share, target_share,
  games_played, red_zone_looks
)

projections (
  player_id, source [espn|yahoo|fantasypros],
  scoring_format [standard|half_ppr|ppr],
  projected_points, last_updated
)

adp_data (
  player_id, format [standard|half_ppr|ppr|dynasty],
  adp, adp_source, last_updated
)

team_context (
  team, season,
  off_line_grade,         -- PFF grade
  new_head_coach,         -- boolean
  coaching_scheme,        -- text descriptor
  last_updated
)
```

---

## Scoring Engine

Produces one `projected_score` per player from a configurable weighted blend of three sources:

| Source | Default Weight | Notes |
|--------|---------------|-------|
| Prior year actuals | 40% | Normalized to user's scoring format |
| ESPN projection | 30% | Current season |
| FantasyPros consensus | 30% | Current season (aggregates expert projections) |

**Weights are user-configurable** via linked sliders in the UI (must sum to 100%). Dynasty mode ships with a different default preset (20% / 40% / 40%) that favors projections over history, reflecting the importance of youth trajectory.

**League settings that affect scoring:**

| Setting | Options |
|---------|---------|
| Scoring format | Standard, Half-PPR, Full PPR, TE Premium (+1.5 to TE receptions) |
| League type | Standard, Dynasty, Keeper |
| League size | 8 / 10 / 12 / 14 / 16 teams |
| Roster format | Standard (QB/2RB/2WR/TE/FLEX) or custom |
| QB TD value | 4-pt or 6-pt passing TDs |
| Bonus settings | 100-yd bonuses, first-down bonuses (optional toggles) |

---

## Rules Engine

Each rule is a typed object with:
- `enabled` — boolean toggle
- `weight` — user-adjustable multiplier: `low (0.5×) | default (1×) | high (2×)`
- `condition` — what triggers the rule
- `effect` — `score_multiplier`, `flat_bonus`, `flat_penalty`, or `flag`

**Built-in rules (18 at launch):**

| Category | Rule | Default Effect |
|----------|------|---------------|
| Age/Longevity | RB age penalty (28+) | −8% per year over 28 |
| Age/Longevity | WR age penalty (31+) | −5% per year over 31 |
| Age/Longevity | Dynasty youth premium (<25) | +10% in dynasty mode |
| Usage | RB committee discount (<50% carry share) | −15% |
| Usage | Target share premium (>25%) | +10% |
| Usage | Red zone usage premium (top-10 looks) | +7% |
| Usage | Declining snap% trend (H2 of prior season) | −10% |
| Situation | New team / new scheme | −10% |
| Situation | New head coach | −7% |
| Situation | ADP above projection (overvalued) | −5% per round gap |
| Situation | Sophomore leap (2nd-year skill player) | +8% |
| Situation | Contract year motivation | flag only |
| Regression | TD regression (actual TDs vs red-zone-opportunity-implied TDs) | ±score correction toward expected |
| Regression | Injury history (2+ missed games in 2 yrs) | −12% |
| Regression | OL quality penalty (PFF grade <60) | −8% for RB/QB |
| Flag | Identified handcuff (backup RB) | flag: "Handcuff" |
| Flag | Injury designation entering season | flag: "Injury Risk" |
| Flag | Suspension/holdout risk | flag: "Availability Risk" |

**Custom rules:** Power users can define additional rules via a JSON config block in the UI. Schema:

```json
{
  "name": "My Rule",
  "type": "score_penalty",
  "condition": { "field": "age", "operator": ">", "value": 34 },
  "effect": { "type": "multiplier", "value": 0.80 }
}
```

Supported condition fields: `age`, `position`, `snap_pct`, `carry_share`, `target_share`, `games_played`, `years_exp`, `adp`, `projected_score`, `new_team`, `new_coach`.

Supported effect types: `multiplier`, `flat_bonus`, `flat_penalty`, `flag`.

---

## Tier Calculation Algorithm

1. **Compute adjusted score** — Apply all enabled rules in sequence to each player's blended projected score. Multipliers compound; flags are collected in a separate list.

2. **Cluster within each position** — For each position (QB, RB, WR, TE, K, DST), run **Jenks Natural Breaks** on the adjusted scores. Jenks finds breakpoints where score gaps are largest — no need to specify `k` upfront. Max tiers per position are capped by league size (12-team → QB3, RB5, WR5, TE3).

3. **Assign positional tier labels** — QB1/QB2/QB3, RB1–RB5, WR1–WR5, TE1–TE3, etc.

4. **Merge into overall draft board** — Sort all players by `adjusted_score` descending. Run a second Jenks pass on the merged distribution to assign overall tier numbers. Overall tiers map loosely to draft round ranges but breaks come from the data, not fixed round counts.

5. **Output** — JSON response to frontend; CSV on download.

---

## CSV Output Format

```
overall_rank, player, position, team, age,
overall_tier, positional_tier,
adjusted_score, projected_score_raw, prior_year_actual,
adp_standard, adp_ppr, adp_dynasty,
flags, rules_applied
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/generate` | Generate tier list; body contains settings + rules config |
| `GET` | `/api/rules` | Return all available built-in rules with defaults |
| `GET` | `/api/players` | Return all cached players with current data |
| `GET` | `/api/data/status` | Data freshness timestamp per source |
| `POST` | `/api/data/refresh` | Trigger manual data refresh (admin) |

---

## Frontend UI

Three-panel left-to-right layout matching the draft workflow:

```
┌─────────────────────────────────────────────────────────────────┐
│  AutoTiers                                          [Generate]  │
├──────────────────┬──────────────────────┬───────────────────────┤
│  SETTINGS        │  RULES               │  TIERS                │
│                  │                      │                        │
│  League Type     │  ┌ Age/Longevity ──┐ │  [All|QB|RB|WR|TE]   │
│  ○ Standard      │  │ ☑ RB age penalty│ │                        │
│  ○ Dynasty       │  │   weight: ━━●━  │ │  ── Tier 1 ────────  │
│  ○ Keeper        │  │ ☑ WR age penalty│ │  1. Chase   WR1 385  │
│                  │  │   weight: ━●━━  │ │  2. Henry   RB1 378  │
│  Scoring         │  └─────────────────┘ │  3. Jefferson WR1 371│
│  ○ Standard      │  ┌ Usage ─────────┐  │                        │
│  ○ Half-PPR      │  │ ☑ Committee RB │  │  ── Tier 2 ────────  │
│  ● Full PPR      │  │ ☑ Target share │  │  4. Lamb    WR1 354  │
│  ○ TE Premium    │  │ ☐ Red zone     │  │  5. McCaffrey RB1 349│
│                  │  └─────────────────┘  │  ...                  │
│  League Size     │  ┌ Custom Rule ───┐   │                        │
│  [12 teams  ▾]   │  │ + Add rule     │   │       [↓ Download CSV]│
│                  │  └─────────────────┘  │                        │
│  Score Weights   │                       │                        │
│  Prior yr: 40%   │                       │                        │
│  ESPN:     30%   │                       │                        │
│  Consensus: 30%  │                       │                        │
│  [must = 100%]   │                       │                        │
└──────────────────┴──────────────────────┴───────────────────────┘
```

**Key UX behaviors:**
- Score weight sliders are linked — adjusting one auto-adjusts others to keep sum at 100%
- Rule weight shows as a 3-point slider: low (0.5×) / default (1×) / high (2×)
- Generate button disabled until weights sum to 100%
- Tiers panel shows loading skeleton while generating, then animates in
- Data freshness timestamp displayed ("Player data last updated: May 18, 2026")
- CSV download always reflects the current displayed result

---

## Error Handling

- If a data source fails to fetch, the engine falls back to cached data and notes the source as stale in the UI
- If no projection data exists for a player (returning player), prior-year actuals receive 100% weight with a "Projection Unavailable" flag
- If a player has neither projections nor prior-year stats (true rookie), they are included using only available data sources with a "Rookie — Limited Data" flag; users should treat their tier placement as low-confidence
- If weights don't sum to 100%, the Generate button stays disabled and an inline validation message explains why
- Custom rules with invalid JSON are rejected inline with a parse error message before submission

---

## Out of Scope (v1)

- User accounts / saved configurations (anonymous use only)
- Real-time ADP tracking during live drafts
- Mock draft simulation
- Trade value calculator
- Multi-year dynasty rankings
