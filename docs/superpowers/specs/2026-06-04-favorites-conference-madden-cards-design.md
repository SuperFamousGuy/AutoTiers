# Design: Conference Grouping + Madden-Style Player Cards

**Date:** 2026-06-04
**Branch:** feat/favorites-ui-redesign
**Status:** Approved

---

## Overview

Two related UI improvements:

1. **FavoritesPanel — Conference grouping:** Split the team picker into AFC and NFC sections, each containing their 4 divisions.
2. **Madden-style PlayerCard:** Replace the compact `PlayerRow` on the tiers page with a wide card that shows headshots, team logos, and position-colored accents. Favorite indicators distinguish direct player favorites (⭐) from team favorites (color tint + logo badge).

---

## Change 1: FavoritesPanel — Conference Grouping

### What changes

`FavoritesPanel.tsx` currently renders a flat list of 8 divisions. This change adds a top-level conference heading (AFC / NFC) above each block of 4 divisions.

### Data structure

Replace `NFL_DIVISIONS` (flat array of 8) with `NFL_CONFERENCES` (nested two-level structure):

```ts
const NFL_CONFERENCES: { conference: string; divisions: { division: string; teams: { code: string; name: string }[] }[] }[] = [
  {
    conference: "AFC",
    divisions: [
      { division: "East", teams: [BUF, MIA, NE, NYJ] },
      { division: "North", teams: [BAL, CIN, CLE, PIT] },
      { division: "South", teams: [HOU, IND, JAX, TEN] },
      { division: "West", teams: [DEN, KC, LV, LAC] },
    ],
  },
  {
    conference: "NFC",
    divisions: [
      { division: "East", teams: [DAL, NYG, PHI, WAS] },
      { division: "North", teams: [CHI, DET, GB, MIN] },
      { division: "South", teams: [ATL, CAR, NO, TB] },
      { division: "West", teams: [ARI, LAR, SF, SEA] },
    ],
  },
]
```

Division labels shorten from `"AFC East"` → `"East"` since the conference heading provides context.

### Rendering

```
AFC                          ← bold conference heading
  East                       ← division subheading (existing style, just shorter label)
  [BUF] [MIA] [NE]  [NYJ]   ← existing 4-button grid, unchanged
  North
  [BAL] [CIN] [CLE] [PIT]
  ...
NFC
  ...
```

### What is NOT changed

- `TEAM_NAME` export (still derived from the same team list)
- `TEAM_CAP`, cap enforcement, at-cap messaging
- `toggleTeam` handler
- Any other behavior in `FavoritesPanel`

---

## Change 2: Madden-Style PlayerCard

### New component: `PlayerCard`

New file: `web/src/components/PlayerCard.tsx`

Replaces `PlayerRow` in `TiersPanel`. `PlayerRow.tsx` is deleted (no other consumers).

### Card layout

```
┌─ [pos border] ──────────────────────────────────────────┐
│ [rank]  [headshot]  [Name ⭐/badge]    [team logo] [VBD] │
│                     [POS · Full Team]                     │
└──────────────────────────────────────────────────────────┘
```

**Left border:** 4px solid, colored by position (matches existing position badge palette in `PlayerRow`):
- WR → `#4ade80` (green)
- QB → `#60a5fa` (blue)
- RB → `#fb923c` (orange)
- TE → `#fbbf24` (amber)
- K  → `#94a3b8` (slate)
- DST/DEF → `#c084fc` (purple)

**Rank:** numeric rank, styled in position color, fixed width left of headshot.

**Headshot:**
- URL: `https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg`
- Size: 44×44px, circular (`border-radius: 50%`), border in position color
- Fallback on `onError`: position-colored circle with position abbreviation

**Player name row:**
- Bold name, truncated on overflow
- Inline ⭐ emoji if `is_favorite_player === true`
- Inline 17px team logo badge if `is_favorite_team === true` (after name/star)
- Below: `{position} · {full team name}` — full name from `TEAM_FULL_NAME` lookup (see Shared Teams Module below)

**Right side:**
- 28px team logo from `https://sleepercdn.com/images/team_logos/nfl/{team.toLowerCase()}.jpg`
- VBD score in large position-colored text, `"VBD"` label below in muted

**Card background for team favorites:**
- `is_favorite_team === true`: background `rgba({teamPrimaryRgb}, 0.10)`, border color `rgba({teamPrimaryRgb}, 0.35)`
- `is_favorite_player === true`: no background change (star is the indicator)
- Both: tint + star + badge all applied

### Team primary color map

Static `TEAM_PRIMARY_COLORS: Record<string, string>` covering all 32 teams, used to derive the rgba tint. Example entries:

```ts
const TEAM_PRIMARY_COLORS: Record<string, string> = {
  ARI: "#97233F", ATL: "#A71930", BAL: "#241773", BUF: "#00338D",
  CAR: "#0085CA", CHI: "#0B162A", CIN: "#FB4F14", CLE: "#311D00",
  DAL: "#003594", DEN: "#FB4F14", DET: "#0076B6", GB:  "#203731",
  HOU: "#03202F", IND: "#002C5F", JAX: "#006778", KC:  "#E31837",
  LAC: "#0080C6", LAR: "#003594", LV:  "#A5ACAF", MIA: "#008E97",
  MIN: "#4F2683", NE:  "#002244", NO:  "#D3BC8D", NYG: "#0B2265",
  NYJ: "#125740", PHI: "#004C54", PIT: "#FFB612", SEA: "#002244",
  SF:  "#AA0000", TB:  "#D50A0A", TEN: "#4B92DB", WAS: "#5A1414",
}
```

A utility `hexToRgb(hex: string): string` converts hex → `"r, g, b"` string for use in `rgba(...)`.

### Expand behavior

Clicking the card toggles an expanded score breakdown panel below, with identical content to today's `PlayerRow` expand (score breakdown, rule adjustments, VBD math, flags, tier placement, reference stats). The `ChevronDown` icon rotates on expand.

---

## Backend Changes

These are purely additive — no existing fields removed or renamed.

### `backend/app/engine/tiers.py`

Add two optional fields to the `TieredPlayer` dataclass:

```python
is_favorite_player: Optional[bool] = None
is_favorite_team: Optional[bool] = None
```

### `backend/app/schemas/generate.py`

Add to `TieredPlayerOut`:

```python
is_favorite_player: Optional[bool] = None
is_favorite_team: Optional[bool] = None
```

### `backend/app/api/generate.py`

Replace the current single `is_favorite` computation with two separate signals:

```python
if has_any_favorites:
    is_favorite_player = player.id in favorite_pids_set
    is_favorite_team = player.team is not None and player.team in favorite_teams_set
else:
    is_favorite_player = None
    is_favorite_team = None
```

Pass both when constructing `TieredPlayer(...)`. The existing `is_favorite` field on `PlayerContext` continues to receive `is_favorite_player or is_favorite_team` (unchanged rule-engine behavior).

### `web/src/api/types.ts`

Add to `TieredPlayer`:

```ts
is_favorite_player: boolean | null;
is_favorite_team: boolean | null;
```

---

## Shared Teams Module

A new file `web/src/lib/teams.ts` centralises all NFL team data:

- `NFL_CONFERENCES` — the nested conference → division → teams structure used by `FavoritesPanel`
- `TEAM_FULL_NAME: Record<string, string>` — abbreviation → full name (e.g., `"MIN"` → `"Minnesota Vikings"`), derived from the same team list, used by `PlayerCard` for the subtitle line
- `TEAM_PRIMARY_COLORS: Record<string, string>` — abbreviation → hex primary color, used by `PlayerCard` for the team-favorite tint

`FavoritesPanel.tsx` drops its local `NFL_DIVISIONS` and `TEAM_NAME` in favour of importing from `lib/teams.ts`. The `TEAM_NAME` export from `FavoritesPanel.tsx` is removed (it was re-exported for consumers; any consumers update their import to `lib/teams.ts`).

---

## Out of Scope

- No changes to `TierGroup`, `TiersPanel` filter/grouping logic, or CSV export
- No changes to `FavoritesPanel` player search section
- No changes to `useFavorites` hook or favorites API
- No Sleeper CDN caching or image preloading — images load on demand, fallback handles 404s
- No changes to the rule engine's `is_favorite` usage in `PlayerContext`
