# Favorites Conference Grouping + Madden-Style Player Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the favorites team picker by AFC/NFC conference, and replace the compact `PlayerRow` on the tiers page with a wide Madden-style card showing headshots, team logos, and per-team color tints for favorited teams.

**Architecture:** Six sequential tasks — shared team data module first, then conference grouping in FavoritesPanel, then backend fields, then frontend types, then PlayerCard component (TDD), then wire PlayerCard into TierGroup and delete PlayerRow.

**Tech Stack:** React + TypeScript + Tailwind, Vitest + Testing Library (frontend); Python + FastAPI + Pydantic (backend); Sleeper CDN for headshots/team logos.

**Spec:** `docs/superpowers/specs/2026-06-04-favorites-conference-madden-cards-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `web/src/lib/teams.ts` | NFL_CONFERENCES data, TEAM_FULL_NAME, TEAM_PRIMARY_COLORS, hexToRgb |
| Modify | `web/src/components/FavoritesPanel.tsx` | Import from lib/teams; render conference → division hierarchy |
| Modify | `web/src/tests/components/FavoritesPanel.test.tsx` | Update division label assertions |
| Modify | `backend/app/engine/tiers.py` | Add is_favorite_player / is_favorite_team to TieredPlayer |
| Modify | `backend/app/schemas/generate.py` | Add same two fields to TieredPlayerOut |
| Modify | `backend/app/api/generate.py` | Compute both signals separately; pass to TieredPlayer |
| Modify | `web/src/api/types.ts` | Add both fields to TieredPlayer interface |
| Create | `web/src/components/PlayerCard.tsx` | Madden-style wide card with headshot, team logo, favorite indicators |
| Create | `web/src/tests/components/PlayerCard.test.tsx` | Full test suite for PlayerCard |
| Modify | `web/src/components/TierGroup.tsx` | Swap PlayerRow → PlayerCard |
| Delete | `web/src/components/PlayerRow.tsx` | Replaced by PlayerCard |
| Delete | `web/src/tests/components/PlayerRow.test.tsx` | Replaced by PlayerCard.test.tsx |

---

## Task 1: Create shared teams module

**Files:**
- Create: `web/src/lib/teams.ts`

- [ ] **Step 1: Create `web/src/lib/teams.ts`**

```ts
export const NFL_CONFERENCES: {
  conference: string;
  divisions: { division: string; teams: { code: string; name: string }[] }[];
}[] = [
  {
    conference: "AFC",
    divisions: [
      { division: "East", teams: [
        { code: "BUF", name: "Buffalo Bills" },
        { code: "MIA", name: "Miami Dolphins" },
        { code: "NE",  name: "New England Patriots" },
        { code: "NYJ", name: "New York Jets" },
      ]},
      { division: "North", teams: [
        { code: "BAL", name: "Baltimore Ravens" },
        { code: "CIN", name: "Cincinnati Bengals" },
        { code: "CLE", name: "Cleveland Browns" },
        { code: "PIT", name: "Pittsburgh Steelers" },
      ]},
      { division: "South", teams: [
        { code: "HOU", name: "Houston Texans" },
        { code: "IND", name: "Indianapolis Colts" },
        { code: "JAX", name: "Jacksonville Jaguars" },
        { code: "TEN", name: "Tennessee Titans" },
      ]},
      { division: "West", teams: [
        { code: "DEN", name: "Denver Broncos" },
        { code: "KC",  name: "Kansas City Chiefs" },
        { code: "LV",  name: "Las Vegas Raiders" },
        { code: "LAC", name: "Los Angeles Chargers" },
      ]},
    ],
  },
  {
    conference: "NFC",
    divisions: [
      { division: "East", teams: [
        { code: "DAL", name: "Dallas Cowboys" },
        { code: "NYG", name: "New York Giants" },
        { code: "PHI", name: "Philadelphia Eagles" },
        { code: "WAS", name: "Washington Commanders" },
      ]},
      { division: "North", teams: [
        { code: "CHI", name: "Chicago Bears" },
        { code: "DET", name: "Detroit Lions" },
        { code: "GB",  name: "Green Bay Packers" },
        { code: "MIN", name: "Minnesota Vikings" },
      ]},
      { division: "South", teams: [
        { code: "ATL", name: "Atlanta Falcons" },
        { code: "CAR", name: "Carolina Panthers" },
        { code: "NO",  name: "New Orleans Saints" },
        { code: "TB",  name: "Tampa Bay Buccaneers" },
      ]},
      { division: "West", teams: [
        { code: "ARI", name: "Arizona Cardinals" },
        { code: "LAR", name: "Los Angeles Rams" },
        { code: "SF",  name: "San Francisco 49ers" },
        { code: "SEA", name: "Seattle Seahawks" },
      ]},
    ],
  },
];

export const TEAM_FULL_NAME: Record<string, string> = Object.fromEntries(
  NFL_CONFERENCES.flatMap((c) =>
    c.divisions.flatMap((d) => d.teams.map((t) => [t.code, t.name]))
  )
);

export const TEAM_PRIMARY_COLORS: Record<string, string> = {
  ARI: "#97233F", ATL: "#A71930", BAL: "#241773", BUF: "#00338D",
  CAR: "#0085CA", CHI: "#0B162A", CIN: "#FB4F14", CLE: "#311D00",
  DAL: "#003594", DEN: "#FB4F14", DET: "#0076B6", GB:  "#203731",
  HOU: "#03202F", IND: "#002C5F", JAX: "#006778", KC:  "#E31837",
  LAC: "#0080C6", LAR: "#003594", LV:  "#A5ACAF", MIA: "#008E97",
  MIN: "#4F2683", NE:  "#002244", NO:  "#D3BC8D", NYG: "#0B2265",
  NYJ: "#125740", PHI: "#004C54", PIT: "#FFB612", SEA: "#002244",
  SF:  "#AA0000", TB:  "#D50A0A", TEN: "#4B92DB", WAS: "#5A1414",
};

export function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r}, ${g}, ${b}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/teams.ts
git commit -m "feat(web): add shared NFL teams module (conferences, full names, primary colors)"
```

---

## Task 2: FavoritesPanel — Conference grouping

**Files:**
- Modify: `web/src/components/FavoritesPanel.tsx`
- Modify: `web/src/tests/components/FavoritesPanel.test.tsx`

- [ ] **Step 1: Update the failing test first**

In `web/src/tests/components/FavoritesPanel.test.tsx`, find the test at line 176 (`"team grid renders 32 teams with full-name aria-labels grouped by division"`) and replace it:

```tsx
it("team grid renders 32 teams with full-name aria-labels grouped by conference and division", () => {
  render(
    <FavoritesPanel favorites={makeFav()} onSave={vi.fn()} searchPlayers={vi.fn(async () => [])} />
  );
  expect(screen.getByRole("button", { name: "Kansas City Chiefs" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Buffalo Bills" })).toBeInTheDocument();
  // Conference headings
  expect(screen.getByText("AFC")).toBeInTheDocument();
  expect(screen.getByText("NFC")).toBeInTheDocument();
  // Division subheadings appear once per conference (2×4 = 8 total)
  expect(screen.getAllByText("East").length).toBe(2);
  expect(screen.getAllByText("West").length).toBe(2);
  const teamButtons = screen.getAllByRole("button", { pressed: false });
  expect(teamButtons.length).toBeGreaterThanOrEqual(32);
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd web && npx vitest run src/tests/components/FavoritesPanel.test.tsx
```

Expected: FAIL — `Unable to find an element with the text: AFC`

- [ ] **Step 3: Replace NFL_DIVISIONS data and TEAM_NAME in FavoritesPanel.tsx**

At the top of `web/src/components/FavoritesPanel.tsx`, remove the `NFL_DIVISIONS` constant and the `TEAM_NAME` constant (lines 7–44), and add one import line:

```tsx
import { NFL_CONFERENCES } from "@/lib/teams";
```

- [ ] **Step 4: Update the rendering in FavoritesPanel.tsx**

Find the block (around line 264) that renders `<div className="space-y-3">` with `NFL_DIVISIONS.map(...)` and replace it:

```tsx
<div className="space-y-5">
  {NFL_CONFERENCES.map((conf) => (
    <div key={conf.conference}>
      <h4 className="mb-2 text-sm font-bold text-foreground">{conf.conference}</h4>
      <div className="space-y-3">
        {conf.divisions.map((div) => (
          <div key={div.division}>
            <h5 className="mb-1 text-xs font-semibold text-muted-foreground">{div.division}</h5>
            <div className="grid grid-cols-4 gap-2">
              {div.teams.map((team) => {
                const isFav = favorites.favorite_teams.includes(team.code);
                return (
                  <Button
                    key={team.code}
                    type="button"
                    variant={isFav ? "default" : "outline"}
                    size="sm"
                    onClick={() => toggleTeam(team.code)}
                    disabled={!isFav && teamsAtCap}
                    aria-label={team.name}
                    aria-pressed={isFav}
                  >
                    {team.code}
                  </Button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  ))}
</div>
```

- [ ] **Step 5: Remove the `export { TEAM_NAME }` line** at the bottom of `FavoritesPanel.tsx` (it's not imported anywhere else).

- [ ] **Step 6: Run tests to confirm pass**

```bash
cd web && npx vitest run src/tests/components/FavoritesPanel.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 7: Run full frontend test suite**

```bash
cd web && npx vitest run
```

Expected: All tests PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
git add web/src/components/FavoritesPanel.tsx web/src/tests/components/FavoritesPanel.test.tsx
git commit -m "feat(web): group favorites team picker by AFC/NFC conference"
```

---

## Task 3: Backend — expose is_favorite_player and is_favorite_team

**Files:**
- Modify: `backend/app/engine/tiers.py:24-47`
- Modify: `backend/app/schemas/generate.py:60-85`
- Modify: `backend/app/api/generate.py:357-420`

- [ ] **Step 1: Add fields to TieredPlayer dataclass**

In `backend/app/engine/tiers.py`, add two optional fields after the `rule_applications` field (line 47):

```python
    rule_applications: list[RuleApplication] = field(default_factory=list)
    is_favorite_player: Optional[bool] = None
    is_favorite_team: Optional[bool] = None
```

- [ ] **Step 2: Add fields to TieredPlayerOut schema**

In `backend/app/schemas/generate.py`, add after `rule_applications: list[RuleApplicationOut]` (line 83):

```python
    rule_applications: list[RuleApplicationOut]
    is_favorite_player: Optional[bool] = None
    is_favorite_team: Optional[bool] = None
```

- [ ] **Step 3: Split is_favorite computation in generate.py**

In `backend/app/api/generate.py`, replace the block starting at line 357:

```python
        if has_any_favorites:
            is_favorite = (
                player.id in favorite_pids_set
                or (player.team is not None and player.team in favorite_teams_set)
            )
        else:
            is_favorite = None
```

with:

```python
        if has_any_favorites:
            is_favorite_player = player.id in favorite_pids_set
            is_favorite_team = player.team is not None and player.team in favorite_teams_set
        else:
            is_favorite_player = None
            is_favorite_team = None
```

- [ ] **Step 4: Update PlayerContext call to preserve rule-engine behavior**

Still in `generate.py`, find `is_favorite=is_favorite,` in the `PlayerContext(...)` call and change it to:

```python
            is_favorite=is_favorite_player or is_favorite_team,
```

- [ ] **Step 5: Pass both fields when constructing TieredPlayer**

In the `tiered.append(TieredPlayer(...))` block (line 399), add two fields after `rule_applications=rule_result.applications,`:

```python
            rule_applications=rule_result.applications,
            is_favorite_player=is_favorite_player,
            is_favorite_team=is_favorite_team,
```

- [ ] **Step 6: Run backend tests**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All tests PASS (new fields have defaults; existing rule-engine behavior preserved).

- [ ] **Step 7: Commit**

```bash
git add backend/app/engine/tiers.py backend/app/schemas/generate.py backend/app/api/generate.py
git commit -m "feat(backend): expose is_favorite_player and is_favorite_team in generate response"
```

---

## Task 4: Update frontend TieredPlayer type

**Files:**
- Modify: `web/src/api/types.ts:56-80`

- [ ] **Step 1: Add two fields to the TieredPlayer interface**

In `web/src/api/types.ts`, inside the `TieredPlayer` interface, add after `rule_applications: RuleApplication[];`:

```ts
  rule_applications: RuleApplication[];
  is_favorite_player: boolean | null;
  is_favorite_team: boolean | null;
```

- [ ] **Step 2: Run frontend tests to check for type errors**

```bash
cd web && npx vitest run
```

Expected: Tests will **fail** — `PlayerRow.test.tsx` basePlayer fixture is missing the new required fields.

- [ ] **Step 3: Add the two new fields to the basePlayer fixture in PlayerRow.test.tsx**

In `web/src/tests/components/PlayerRow.test.tsx`, in the `basePlayer` object (line 7), add:

```ts
  is_favorite_player: null,
  is_favorite_team: null,
```

(Add after `league_adp: null,`)

- [ ] **Step 4: Run tests again**

```bash
cd web && npx vitest run
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/types.ts web/src/tests/components/PlayerRow.test.tsx
git commit -m "feat(web): add is_favorite_player and is_favorite_team to TieredPlayer type"
```

---

## Task 5: Create PlayerCard component (TDD)

**Files:**
- Create: `web/src/tests/components/PlayerCard.test.tsx`
- Create: `web/src/components/PlayerCard.tsx`

- [ ] **Step 1: Write failing tests in PlayerCard.test.tsx**

Create `web/src/tests/components/PlayerCard.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlayerCard } from "@/components/PlayerCard";
import type { TieredPlayer } from "@/api/types";

const basePlayer: TieredPlayer = {
  overall_rank: 7,
  player_id: "4035",
  name: "Derrick Henry",
  position: "RB",
  team: "BAL",
  age: 32,
  overall_tier: 1,
  positional_tier: "RB1",
  adjusted_score: 251.26,
  projected_score_raw: 234.82,
  prior_year_actual: 280.5,
  avg_projection: 220.4,
  espn_projection: 215.0,
  fantasypros_projection: 225.8,
  adp_standard: 18,
  adp_ppr: 16,
  adp_dynasty: 22,
  league_adp: null,
  vbd_score: 95.4,
  position_replacement: 155.9,
  flags: ["Contract Year"],
  rules_applied: ["Red Zone Usage Premium"],
  rule_applications: [
    {
      name: "Red Zone Usage Premium",
      effect_type: "multiplier",
      before_score: 234.82,
      after_score: 251.26,
      delta: 16.44,
    },
  ],
  is_favorite_player: null,
  is_favorite_team: null,
};

describe("PlayerCard", () => {
  it("renders rank, name, team abbreviation in subtitle, and VBD score collapsed", () => {
    render(<PlayerCard player={basePlayer} />);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Derrick Henry")).toBeInTheDocument();
    expect(screen.getByText("95.4")).toBeInTheDocument();
    // subtitle shows position and full team name
    expect(screen.getByText(/RB/)).toBeInTheDocument();
    expect(screen.getByText(/Baltimore Ravens/)).toBeInTheDocument();
  });

  it("does not show expanded sections when collapsed", () => {
    render(<PlayerCard player={basePlayer} />);
    expect(screen.queryByText("Score breakdown")).not.toBeInTheDocument();
    expect(screen.queryByText(/Value-Based Drafting/)).not.toBeInTheDocument();
  });

  it("expands on click and shows all detail sections", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for derrick henry/i));
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
    expect(screen.getByText("Rule adjustments")).toBeInTheDocument();
    expect(screen.getByText(/Value-Based Drafting/)).toBeInTheDocument();
    expect(screen.getByText("Flags")).toBeInTheDocument();
    expect(screen.getByText("Tier placement")).toBeInTheDocument();
    expect(screen.getByText("Reference")).toBeInTheDocument();
  });

  it("collapses again when toggled twice", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    const toggle = screen.getByLabelText(/toggle details/i);
    await user.click(toggle);
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
    await user.click(toggle);
    expect(screen.queryByText("Score breakdown")).not.toBeInTheDocument();
  });

  it("shows gold star when is_favorite_player is true", () => {
    render(<PlayerCard player={{ ...basePlayer, is_favorite_player: true }} />);
    expect(screen.getByText("⭐")).toBeInTheDocument();
  });

  it("does not show gold star when is_favorite_player is null or false", () => {
    const { rerender } = render(<PlayerCard player={basePlayer} />);
    expect(screen.queryByText("⭐")).not.toBeInTheDocument();
    rerender(<PlayerCard player={{ ...basePlayer, is_favorite_player: false }} />);
    expect(screen.queryByText("⭐")).not.toBeInTheDocument();
  });

  it("shows team logo badge when is_favorite_team is true", () => {
    render(<PlayerCard player={{ ...basePlayer, is_favorite_team: true }} />);
    // The small badge img has alt = full team name; aria-hidden logo is separate
    const badges = screen.getAllByAltText("Baltimore Ravens");
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it("renders the VBD breakdown with replacement and total when expanded", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));
    const vbd = screen.getByText(/Value-Based Drafting/).parentElement!;
    expect(within(vbd).getByText("Replacement (RB)")).toBeInTheDocument();
    expect(within(vbd).getByText(/155\.9/)).toBeInTheDocument();
  });

  it("renders em-dash for missing team", () => {
    render(<PlayerCard player={{ ...basePlayer, team: null }} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd web && npx vitest run src/tests/components/PlayerCard.test.tsx
```

Expected: FAIL — `Cannot find module '@/components/PlayerCard'`

- [ ] **Step 3: Create PlayerCard.tsx**

Create `web/src/components/PlayerCard.tsx`:

```tsx
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { TEAM_FULL_NAME, TEAM_PRIMARY_COLORS, hexToRgb } from "@/lib/teams";
import type { TieredPlayer } from "@/api/types";

const POSITION_COLORS: Record<string, string> = {
  QB:  "#60a5fa",
  RB:  "#fb923c",
  WR:  "#4ade80",
  TE:  "#fbbf24",
  K:   "#94a3b8",
  DST: "#c084fc",
  DEF: "#c084fc",
};

function positionColor(position: string): string {
  return POSITION_COLORS[position] ?? "#94a3b8";
}

interface PlayerCardProps {
  player: TieredPlayer;
}

export function PlayerCard({ player }: PlayerCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [imgError, setImgError] = useState(false);

  const posColor = positionColor(player.position);
  const teamPrimary = player.team ? TEAM_PRIMARY_COLORS[player.team] : null;
  const teamRgb = teamPrimary ? hexToRgb(teamPrimary) : null;
  const fullTeamName = player.team ? (TEAM_FULL_NAME[player.team] ?? player.team) : "—";

  const isFavPlayer = player.is_favorite_player === true;
  const isFavTeam = player.is_favorite_team === true;

  const cardStyle: React.CSSProperties =
    isFavTeam && teamRgb
      ? {
          backgroundColor: `rgba(${teamRgb}, 0.10)`,
          borderColor: `rgba(${teamRgb}, 0.35)`,
        }
      : {};

  const posRgb = hexToRgb(posColor);

  return (
    <div
      className="rounded-lg border border-l-4 transition-colors"
      style={{ borderLeftColor: posColor, ...cardStyle }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-sm text-left"
        aria-expanded={expanded}
        aria-label={`Toggle details for ${player.name}`}
      >
        {/* Rank */}
        <span
          className="w-6 text-right font-bold shrink-0"
          style={{ color: posColor }}
        >
          {player.overall_rank}
        </span>

        {/* Headshot */}
        {!imgError ? (
          <img
            src={`https://sleepercdn.com/content/nfl/players/thumb/${player.player_id}.jpg`}
            onError={() => setImgError(true)}
            alt={player.name}
            className="w-11 h-11 rounded-full object-cover object-top shrink-0"
            style={{ border: `2px solid ${posColor}` }}
          />
        ) : (
          <div
            className="w-11 h-11 rounded-full shrink-0 flex items-center justify-center text-[11px] font-bold"
            style={{
              border: `2px solid ${posColor}`,
              color: posColor,
              backgroundColor: `rgba(${posRgb}, 0.12)`,
            }}
          >
            {player.position}
          </div>
        )}

        {/* Name + subtitle */}
        <div className="flex-1 min-w-0">
          <div className="font-bold text-sm flex items-center gap-1 flex-wrap">
            <span className="truncate">{player.name}</span>
            {isFavPlayer && <span className="shrink-0">⭐</span>}
            {isFavTeam && player.team && (
              <img
                src={`https://sleepercdn.com/images/team_logos/nfl/${player.team.toLowerCase()}.jpg`}
                alt={fullTeamName}
                className="w-[17px] h-[17px] rounded-sm object-contain shrink-0 opacity-90"
              />
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {player.position} · {fullTeamName}
          </div>
        </div>

        {/* Team logo + VBD */}
        <div className="flex items-center gap-2.5 shrink-0">
          {player.team && (
            <img
              src={`https://sleepercdn.com/images/team_logos/nfl/${player.team.toLowerCase()}.jpg`}
              alt={fullTeamName}
              aria-hidden="true"
              className="w-7 h-7 rounded object-contain"
            />
          )}
          <div className="text-right">
            <div
              className="text-lg font-black leading-none"
              style={{ color: posColor }}
            >
              {player.vbd_score.toFixed(1)}
            </div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-wide">VBD</div>
          </div>
        </div>

        {/* Chevron */}
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform shrink-0",
            expanded && "rotate-180"
          )}
        />
      </button>

      {/* Expanded detail panel */}
      {expanded && (
        <div className="px-3 pb-3 pt-1 space-y-3 text-xs border-t bg-muted/20">
          {/* Score breakdown */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Score breakdown
            </div>
            <div className="space-y-0.5 font-mono">
              {player.prior_year_actual !== null && (
                <div className="flex justify-between">
                  <span>Prior year actual</span>
                  <span>{player.prior_year_actual.toFixed(1)}</span>
                </div>
              )}
              {player.espn_projection !== null && (
                <div className="flex justify-between">
                  <span>ESPN projection</span>
                  <span>{player.espn_projection.toFixed(1)}</span>
                </div>
              )}
              {player.fantasypros_projection !== null && (
                <div className="flex justify-between">
                  <span>FantasyPros consensus</span>
                  <span>{player.fantasypros_projection.toFixed(1)}</span>
                </div>
              )}
              {player.avg_projection !== null && (
                <div className="flex justify-between">
                  <span>Avg projection (all sources)</span>
                  <span>{player.avg_projection.toFixed(1)}</span>
                </div>
              )}
              <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                <span>Blended raw</span>
                <span>{player.projected_score_raw.toFixed(1)}</span>
              </div>
            </div>
          </div>

          {/* Rule adjustments */}
          {(() => {
            const scoringApps = player.rule_applications.filter(
              (a) => a.effect_type !== "flag"
            );
            if (scoringApps.length === 0) {
              return (
                <div className="text-muted-foreground italic">
                  No score adjustments (adjusted = blended)
                </div>
              );
            }
            return (
              <div>
                <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
                  Rule adjustments
                </div>
                <div className="space-y-0.5 font-mono">
                  {scoringApps.map((app, i) => (
                    <div key={i} className="flex justify-between">
                      <span className="truncate pr-2">{app.name}</span>
                      <span
                        className={cn(
                          app.delta > 0 && "text-green-700 dark:text-green-400",
                          app.delta < 0 && "text-red-700 dark:text-red-400"
                        )}
                      >
                        {`${app.delta > 0 ? "+" : ""}${app.delta.toFixed(1)}`}
                        <span className="text-muted-foreground ml-2">
                          → {app.after_score.toFixed(1)}
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                    <span>Adjusted score</span>
                    <span>{player.adjusted_score.toFixed(1)}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Value-Based Drafting */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Value-Based Drafting (vs position replacement)
            </div>
            <div className="space-y-0.5 font-mono">
              <div className="flex justify-between">
                <span>Adjusted score</span>
                <span>{player.adjusted_score.toFixed(1)}</span>
              </div>
              <div className="flex justify-between">
                <span>Replacement ({player.position})</span>
                <span>−{player.position_replacement.toFixed(1)}</span>
              </div>
              <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                <span>VBD score</span>
                <span>{player.vbd_score.toFixed(1)}</span>
              </div>
            </div>
          </div>

          {/* Flags */}
          {player.flags.length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
                Flags
              </div>
              <div className="flex flex-wrap gap-1">
                {player.flags.map((f) => (
                  <span
                    key={f}
                    className="rounded bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300 px-1.5 py-0.5"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Tier placement */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Tier placement
            </div>
            <div className="flex gap-4">
              <div>
                <div className="text-muted-foreground">Overall</div>
                <div className="font-medium">
                  Tier {player.overall_tier} · #{player.overall_rank}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Positional</div>
                <div className="font-medium">{player.positional_tier}</div>
              </div>
            </div>
          </div>

          {/* Reference */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Reference
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <div className="text-muted-foreground">Position</div>
                <div>{player.position}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Age</div>
                <div>{player.age ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ADP (standard)</div>
                <div>{player.adp_standard ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ADP (PPR)</div>
                <div>{player.adp_ppr ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ADP (dynasty)</div>
                <div>{player.adp_dynasty ?? "—"}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run PlayerCard tests**

```bash
cd web && npx vitest run src/tests/components/PlayerCard.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 5: Run full frontend suite**

```bash
cd web && npx vitest run
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/PlayerCard.tsx web/src/tests/components/PlayerCard.test.tsx
git commit -m "feat(web): add madden-style PlayerCard with headshots, team logos, and favorite indicators"
```

---

## Task 6: Wire PlayerCard into TierGroup, delete PlayerRow

**Files:**
- Modify: `web/src/components/TierGroup.tsx`
- Delete: `web/src/components/PlayerRow.tsx`
- Delete: `web/src/tests/components/PlayerRow.test.tsx`

- [ ] **Step 1: Update TierGroup.tsx**

In `web/src/components/TierGroup.tsx`, change the import and usage:

Replace:
```tsx
import { PlayerRow } from "./PlayerRow";
```
with:
```tsx
import { PlayerCard } from "./PlayerCard";
```

Replace inside the map:
```tsx
<PlayerRow key={p.player_id} player={p} />
```
with:
```tsx
<PlayerCard key={p.player_id} player={p} />
```

- [ ] **Step 2: Delete PlayerRow.tsx and its test**

```bash
rm web/src/components/PlayerRow.tsx
rm web/src/tests/components/PlayerRow.test.tsx
```

- [ ] **Step 3: Run full frontend suite**

```bash
cd web && npx vitest run
```

Expected: All tests PASS (PlayerRow tests gone, PlayerCard tests cover the same surface).

- [ ] **Step 4: Commit**

```bash
git add web/src/components/TierGroup.tsx
git rm web/src/components/PlayerRow.tsx web/src/tests/components/PlayerRow.test.tsx
git commit -m "feat(web): wire PlayerCard into TierGroup, remove PlayerRow"
```

---

## Self-Review Checklist

- [x] Conference grouping: `NFL_CONFERENCES` in `lib/teams.ts`, rendered with `<h4>` conference + `<h5>` division, test updated to check for "AFC"/"NFC" headings
- [x] Madden cards: rank, circular headshot (Sleeper CDN + fallback), name, ⭐ for is_favorite_player, small logo badge for is_favorite_team, team logo right side, VBD score, expand panel, ChevronDown
- [x] Team tint: `rgba(teamRgb, 0.10)` background + matching border when is_favorite_team
- [x] Both favorites: tint + star + badge all coexist
- [x] Backend: two optional fields with defaults, `is_favorite` for PlayerContext unchanged
- [x] `lib/teams.ts`: `TEAM_FULL_NAME` derived from `NFL_CONFERENCES`, used in PlayerCard subtitle
- [x] `TEAM_NAME` export removed from FavoritesPanel (no other consumers)
- [x] PlayerRow deleted; PlayerCard.test.tsx covers all previously tested expand/collapse behavior
- [x] TierGroup is the only consumer of PlayerRow — confirmed and updated
