# AutoTiers Frontend — Design Spec

**Date:** 2026-05-21
**Status:** Approved
**Parent spec:** `2026-05-19-autotiers-design.md`
**Depends on:** Plan 1 (backend API) and Plan 2 (data pipeline) — both merged.

---

## Overview

Build the user-facing AutoTiers web app: a three-panel React app where users configure their league settings, toggle rules, click Generate, and see a draft-board with downloadable CSV. The backend API and data pipeline are already live; this plan is purely the frontend.

After Plan 3, AutoTiers is feature-complete for v1: anonymous users can land on the page, configure their draft, and walk away with a tier-banded CSV.

---

## Stack

| Layer | Choice |
|---|---|
| Framework | React 18 + TypeScript |
| Build tool | Vite |
| Server state | TanStack Query v5 |
| Form state | Local `useState` in the parent (no Zustand, no Context) |
| Styling | Tailwind CSS |
| Component library | shadcn/ui (Radix primitives + Tailwind, source-owned) |
| Testing | Vitest + @testing-library/react + MSW |
| Dev container | New `web` service in `docker-compose.yml` |
| Deployment | Railway (alongside backend, per the original spec) |

**Why these choices:**
- **Vite over CRA** — CRA is unmaintained; Vite is fast, modern, supports React 18 + TS out of the box
- **TanStack Query** — already chosen in the v1 spec; handles caching, deduplication, retries, and is the right shape for this "configure → fetch → render" flow
- **Local useState over Zustand** — the form is shallow (~20 fields total). One state lives in the App component, panels read/write via props. No global store needed for v1.
- **shadcn/ui** — copy-paste components built on Radix. You own the source, no runtime dep bloat, fully accessible (Radix handles keyboard nav and ARIA). Comes with sensible defaults for sliders, switches, dropdowns, dialogs — all needed here.
- **Vitest over Jest** — Vite-native, faster, same `expect` API, no separate Jest config

---

## Architecture

### Three-panel layout

```
┌──────────────────────────────────────────────────────────────────┐
│  AutoTiers          Data updated 2 days ago         [Generate]   │  ← Header
├──────────────┬─────────────────────────┬─────────────────────────┤
│  SETTINGS    │  RULES                  │  TIERS                  │
│              │                         │                         │
│  League Type │  ▾ Age/Longevity        │ [All|QB|RB|WR|TE|K|DST] │
│  ◯ Standard  │    ☑ RB age penalty     │                         │
│  ◯ Dynasty   │      low ●━━━ high      │  ── Tier 1 ────────     │
│  ◯ Keeper    │    ☑ WR age penalty     │  1. Chase   WR1 385.2   │
│              │      low ━●━━ high      │  2. Henry   RB1 378.4   │
│  Scoring     │  ▾ Usage                │  3. Jefferson WR1 371.6 │
│  ◯ Standard  │    ☑ Committee RB       │                         │
│  ◯ Half-PPR  │    ☑ Target share       │  ── Tier 2 ────────     │
│  ● PPR       │    ☐ Red zone           │  4. Lamb    WR1 354.1   │
│  ◯ TE Prem   │  ▾ Custom Rule          │  ...                    │
│              │    + Add rule (JSON)    │                         │
│  League Size │                         │  [↓ Download CSV]       │
│  [12 ▾]      │                         │                         │
│              │                         │                         │
│  Bonuses     │                         │                         │
│  ☐ 100yd rush│                         │                         │
│  ☐ 100yd rec │                         │                         │
│              │                         │                         │
│  Weights     │                         │                         │
│  Prior:  40% │                         │                         │
│  ESPN:   30% │                         │                         │
│  Cnsns:  30% │                         │                         │
│  ✓ Sums 100% │                         │                         │
└──────────────┴─────────────────────────┴─────────────────────────┘
```

On mobile (<1024px) the three panels stack vertically in the order Settings → Rules → Tiers.

### Component hierarchy

```
App
├── QueryClientProvider (TanStack Query)
├── Header
│   ├── Title
│   ├── DataFreshness (reads /api/data/status)
│   └── GenerateButton (disabled until weights = 100%)
├── ThreePanelLayout
│   ├── SettingsPanel
│   │   ├── LeagueTypeRadio       (standard | dynasty | keeper)
│   │   ├── ScoringFormatRadio    (standard | half_ppr | ppr | te_premium)
│   │   ├── LeagueSizeSelect      (8 | 10 | 12 | 14 | 16)
│   │   ├── QbTdPointsRadio       (4 | 6)
│   │   ├── BonusToggles          (3 switches)
│   │   └── ScoreWeights          (3 linked sliders, sum-to-100 validator)
│   ├── RulesPanel
│   │   ├── RuleCategory (collapsible per category from /api/rules)
│   │   │   └── RuleItem (toggle + 3-position weight chip)
│   │   └── CustomRulesEditor (JSON textarea + add button)
│   └── TiersPanel
│       ├── PositionFilter (All | QB | RB | WR | TE | K | DST)
│       ├── TierGroup (one per overall_tier)
│       │   └── PlayerRow
│       └── DownloadCsvButton
└── Toaster (global error notifications)
```

### Data flow

```
On mount:
  useRules()       → GET /api/rules        (cached forever; only changes with deploy)
  useDataStatus()  → GET /api/data/status  (cached 60s; powers DataFreshness)

User interaction:
  Form state lives in App.tsx as a single `formState` object passed by prop to each panel.
  Each panel receives `value` + `onChange` callbacks (controlled inputs).

Click Generate:
  useGenerateMutation()  → POST /api/generate with current formState
  Result populates TiersPanel.

Click Download CSV:
  Triggers POST /api/generate/csv with the same formState; browser downloads tiers.csv.
```

---

## File Structure

```
web/                                # NEW directory at repo root
├── package.json
├── package-lock.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── components.json                 # shadcn/ui config
├── Dockerfile                      # dev container
├── .dockerignore
├── .gitignore
├── index.html
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx                    # entrypoint, wires QueryClientProvider
    ├── App.tsx                     # top-level layout + form state
    ├── index.css                   # Tailwind imports + globals
    ├── api/
    │   ├── client.ts               # QueryClient setup + fetcher wrapper
    │   ├── types.ts                # TS types mirroring backend Pydantic schemas
    │   └── hooks.ts                # useRules, useDataStatus, useGenerate, useDownloadCsv
    ├── components/
    │   ├── ui/                     # shadcn primitives (Button, Slider, Select, ...)
    │   ├── Header.tsx
    │   ├── DataFreshness.tsx
    │   ├── GenerateButton.tsx
    │   ├── ThreePanelLayout.tsx
    │   ├── SettingsPanel.tsx
    │   ├── ScoreWeights.tsx        # the 3 linked sliders
    │   ├── RulesPanel.tsx
    │   ├── RuleCategory.tsx
    │   ├── RuleItem.tsx
    │   ├── CustomRulesEditor.tsx
    │   ├── TiersPanel.tsx
    │   ├── TierGroup.tsx
    │   ├── PlayerRow.tsx
    │   └── PositionFilter.tsx
    ├── lib/
    │   ├── weights.ts              # linked-slider redistribution logic
    │   ├── csv.ts                  # CSV download trigger
    │   └── format.ts               # relative time, number formatting
    └── tests/
        ├── setup.ts                # Vitest + Testing Library + MSW config
        ├── handlers.ts             # MSW request handlers
        ├── lib/
        │   └── weights.test.ts
        └── components/
            ├── ScoreWeights.test.tsx
            ├── RuleItem.test.tsx
            ├── CustomRulesEditor.test.tsx
            └── TiersPanel.test.tsx
```

---

## API Integration

### Types (`src/api/types.ts`)

Mirror the backend Pydantic schemas. These have to stay in sync; document the source of truth as `backend/app/schemas/*.py`.

```ts
export type ScoringFormat = "standard" | "half_ppr" | "ppr" | "te_premium";
export type LeagueType = "standard" | "dynasty" | "keeper";
export type LeagueSize = 8 | 10 | 12 | 14 | 16;

export interface RuleCondition {
  field: string;
  operator: ">" | ">=" | "<" | "<=" | "==" | "!=";
  value: number | string | boolean;
}

export interface RuleEffect {
  type: "multiplier" | "flat_bonus" | "flat_penalty" | "flag";
  value: number | string;
}

export interface Rule {
  name: string;
  conditions: RuleCondition[];
  effect: RuleEffect;
  enabled: boolean;
  weight: number;        // 0.5 | 1.0 | 2.0
  is_builtin: boolean;
  category: string;      // "Age/Longevity" | "Usage" | "Situation" | "Regression" | "Flag" | "Custom"
}

export interface GenerateRequest {
  scoring_format: ScoringFormat;
  league_type: LeagueType;
  league_size: LeagueSize;
  qb_td_points: 4 | 6;
  bonus_100yd_rushing: boolean;
  bonus_100yd_receiving: boolean;
  bonus_first_downs: boolean;
  weight_prior_year: number;
  weight_espn: number;
  weight_consensus: number;
  rules: Rule[];
}

export interface TieredPlayer {
  overall_rank: number;
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  overall_tier: number;
  positional_tier: string;
  adjusted_score: number;
  projected_score_raw: number;
  prior_year_actual: number | null;
  adp_standard: number | null;
  adp_ppr: number | null;
  adp_dynasty: number | null;
  flags: string[];
  rules_applied: string[];
}

export interface GenerateResponse {
  players: TieredPlayer[];
  total: number;
  data_as_of: string | null;
}

export interface DataSourceStatus {
  last_updated: string | null;
  last_attempted: string | null;
  last_error: string | null;
  rows_upserted: number;
}

export type DataStatusResponse = Record<string, DataSourceStatus>;
```

### Hooks (`src/api/hooks.ts`)

```ts
export function useRules() {
  return useQuery<Rule[]>({
    queryKey: ["rules"],
    queryFn: () => fetch(`${API_URL}/api/rules`).then(r => r.json()),
    staleTime: Infinity,  // rules only change on deploy
  });
}

export function useDataStatus() {
  return useQuery<DataStatusResponse>({
    queryKey: ["data-status"],
    queryFn: () => fetch(`${API_URL}/api/data/status`).then(r => r.json()),
    staleTime: 60_000,
  });
}

export function useGenerateMutation() {
  return useMutation<GenerateResponse, Error, GenerateRequest>({
    mutationFn: (body) =>
      fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(async r => {
        if (!r.ok) throw new Error(`API error ${r.status}: ${await r.text()}`);
        return r.json();
      }),
  });
}

export async function downloadCsv(body: GenerateRequest): Promise<void> {
  const resp = await fetch(`${API_URL}/api/generate/csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`CSV download failed: ${resp.status}`);
  const blob = await resp.blob();
  triggerDownload(blob, "tiers.csv");
}
```

`API_URL` comes from `import.meta.env.VITE_API_URL` (set in `.env.local` or by the Docker compose service).

---

## Key Behaviors

### Linked weight sliders

State: three numbers, must sum to 100. User drags one; the other two redistribute proportionally.

```ts
// lib/weights.ts
export function redistribute(
  changed: "prior" | "espn" | "consensus",
  newValue: number,
  current: { prior: number; espn: number; consensus: number },
): { prior: number; espn: number; consensus: number } {
  const others: ("prior" | "espn" | "consensus")[] =
    changed === "prior" ? ["espn", "consensus"]
    : changed === "espn" ? ["prior", "consensus"]
    : ["prior", "espn"];

  const remaining = 100 - newValue;
  const oldOtherSum = current[others[0]] + current[others[1]];

  // If the other two are both 0, split evenly
  if (oldOtherSum === 0) {
    return {
      ...current,
      [changed]: newValue,
      [others[0]]: Math.floor(remaining / 2),
      [others[1]]: Math.ceil(remaining / 2),
    };
  }

  // Otherwise distribute proportionally
  const a = Math.round((current[others[0]] / oldOtherSum) * remaining);
  const b = remaining - a;
  return {
    ...current,
    [changed]: newValue,
    [others[0]]: a,
    [others[1]]: b,
  };
}
```

Slider granularity: integer steps of 1 (so the three values always sum to exactly 100, no floating-point drift).

Display: above each slider, show `42%`. Below the three sliders, a "✓ Sums 100%" indicator (always green since redistribution maintains the invariant; only goes red if someone manages to break it via the URL-state hack or similar).

### Rule weight (3-position chip)

```
   ┌─────────┐
   │ low | • default | high │
   └─────────┘
```

A segmented control (shadcn ToggleGroup) with three options. Internally maps to `0.5 | 1.0 | 2.0`. Default position selected on first render.

### Custom rule editor

Single textarea, monospace font. Parses on a debounced timer (300ms after last keystroke). Inline below the textarea: green "✓ Valid" or red error message with line number.

Schema enforced client-side matches `RuleSchema` from the backend. On Add, the custom rule joins the rules list with `is_builtin: false, category: "Custom"`.

Custom rules can be deleted (small × button). Built-in rules cannot — only toggled off.

### Generate button

States:
- **Disabled (gray)**: weights don't sum to 100, or settings invalid (shouldn't happen since UI prevents it)
- **Enabled (primary blue)**: ready to click
- **Loading (spinner)**: mutation pending
- **Error (red border, retry icon)**: mutation failed; tooltip shows error message

Click handler: calls `mutation.mutate(formState)`. On success, `TiersPanel` reads from `mutation.data` and rerenders. On error, a Toaster notification appears.

### Tiers panel

Default state: empty placeholder "Click Generate to build your tier list."

Loading state: skeleton rows (~5 grayed-out rows).

Result state:
- Position filter at the top — clicking "WR" filters all but WRs
- Below filter: tier groups, each with a header `── Tier N ──`
- Each player row: rank, name, position+tier label, team, age, score, flags as chips
- Bottom: large "Download CSV" button

Animation: fade-in transition (Tailwind `transition-opacity duration-200`) when results arrive.

### Data freshness

Reads from `/api/data/status`. Displays the minimum `last_updated` across sources as relative time ("2 days ago"). Hovering the indicator shows a tooltip listing per-source timestamps and any errors.

Color: green if oldest source < 3 days; yellow if 3-7 days; red if >7 days or any source has a `last_error`.

### Error handling

- Network errors → Toaster with the error message + a "Retry" action
- 422 validation errors from `/api/generate` → highlight the offending field (`weight_*` if weights don't sum, etc.) and show the error inline
- Empty result → "No players found. Try a manual refresh: `POST /api/data/refresh`"
- Custom rule parse errors → inline red text below the textarea

---

## Docker Integration

### New `web` service in `docker-compose.yml`

```yaml
services:
  # ... db, api unchanged ...

  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    container_name: autotiers-web
    depends_on:
      - api
    ports:
      - "${WEB_PORT:-5173}:5173"
    environment:
      VITE_API_URL: "http://localhost:${API_PORT:-8000}"
    volumes:
      - ./web/src:/app/src
      - ./web/public:/app/public
      - ./web/index.html:/app/index.html
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### `web/Dockerfile`

```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### `.env.example` additions

```
WEB_PORT=5173
```

### Local dev flow

```bash
podman compose up --build
# → db on 5432, api on 8000, web on 5173
# → open http://localhost:5173
```

Hot reload works in both directions: Python changes restart uvicorn, React changes hot-swap via Vite HMR.

---

## Testing

### Unit (Vitest)

- `lib/weights.test.ts` — redistribution math under various conditions (one-zero-zero, balanced, etc.)
- `lib/csv.test.ts` — download trigger (mocked URL.createObjectURL)
- `lib/format.test.ts` — relative time formatting

### Component (Testing Library + MSW)

- `ScoreWeights.test.tsx` — dragging one slider updates the others; sum always 100
- `RuleItem.test.tsx` — toggle on/off, weight chip changes value
- `CustomRulesEditor.test.tsx` — valid JSON parses + adds; invalid JSON shows error
- `TiersPanel.test.tsx` — renders tier groups in order; position filter narrows the list; empty state shown when no data

### Integration (Testing Library + MSW)

- `App.test.tsx` (single happy-path test): load → settings render → toggle a rule → adjust weights → click Generate → tiers appear → click Download CSV → file save called

### Coverage target

70%+ line coverage on `src/`. Not pursuing 100% — visual/styling code (Tailwind classes) doesn't need tests.

### Test seed data

MSW handlers serve fixtures from `src/tests/fixtures/` matching real backend response shapes. Examples:
- `rules.json` — 18 built-in rules across 5 categories
- `data-status.json` — all 4 sources, recent timestamps
- `generate-response.json` — ~20 players across 3 overall tiers

---

## Out of Scope (v1)

- **User accounts / saved configurations** — anonymous use only per the v1 spec
- **Real-time draft tracking** — no live draft integration
- **Trade analyzer / mock draft simulator** — those are v2+ features
- **Dark mode** — single light theme for v1; can add toggle later via Tailwind `dark:` classes
- **i18n** — English only
- **Detailed accessibility audit** — Radix primitives give us the basics; full audit is post-v1
- **Server-side rendering** — pure SPA, all client-rendered

---

## Migration / Rollout

1. New PR builds the entire `web/` directory
2. After merge to main: Railway picks up the new service from the same repo
3. Set `VITE_API_URL=https://api.autotiers.com` (or wherever the backend lives) in Railway's frontend service env
4. Backend's `CORS_ORIGINS` already supports `["*"]`; tighten to the frontend's domain in production

No database migration. No backend API changes. Pure additive.

---

## Open Questions for the Implementation Plan

Two implementation details deferred to the plan:

1. **Initial form state** — should we hydrate from URL query params (shareable configs) or just use sensible defaults? Plan defaults to sensible defaults; URL hydration is a Plan 4 enhancement.
2. **shadcn/ui installation flow** — shadcn is a CLI, not an npm package. Plan will document the `npx shadcn-ui init` + per-component `npx shadcn-ui add button slider ...` flow.

Neither blocks the plan — they're tactical decisions the plan will document.
