# Better Export — Design

Issue: SuperFamousGuy/AutoTiers#192

## Goal
Make the downloaded CSV a draft-day cheat sheet a real user can scan, instead of the 22-column debug dump it is today — while keeping the debug dump reachable for development.

## Approach
Split the single CSV generator into two: a customer-facing **draft CSV** (lean, human-readable headers) that the visible "Download CSV" button emits, and a **debug CSV** (the existing full column set) reachable only when a `?debug=1` query param is present, via a separate, conditionally-rendered button.

## User-facing impact
- "Download CSV" button (unchanged position, [TiersPanel.tsx](../../../web/src/components/TiersPanel.tsx)) now downloads `tiers.csv` with **11 human-readable columns**:
  `Rank, Player, Pos, Team, Age, Tier, Tier Label, Pos Tier, ADP, Value, Flags`
  - `ADP` is the single ADP matching the chosen scoring format (see mapping below) — one column, not three.
  - `Value` is `vbd_score` rounded to 1 decimal (points above replacement — why a player ranks where they do).
  - `Flags` is the existing `flags` array joined with `; `.
- Empty player list still produces a header-only file (no crash).
- **Debug**: when the app URL has `?debug=1`, a second "Download debug CSV" button appears beside the main one and downloads `tiers-debug.csv` with the original 22 machine-named columns. No visible change for normal users.

## Code-facing impact
- `web/src/lib/csv.ts`:
  - `generateDraftCsvString(players, { tierLabelOverrides, scoringFormat })` — new lean output.
  - `generateDebugCsvString(players, tierLabelOverrides)` — the current behaviour, renamed verbatim.
- `web/src/api/hooks.ts`:
  - `downloadDraftCsv(players, opts)` → `tiers.csv`; `downloadDebugCsv(players, opts)` → `tiers-debug.csv`. Shared blob/anchor helper.
- `web/src/components/TiersPanel.tsx`: new optional `debugMode` + `onDownloadDebugCsv` props; debug button rendered only when `debugMode`.
- `web/src/App.tsx`: read `debug` flag from `URLSearchParams`; pass `scoringFormat` into the draft download; wire debug download.

## ADP selection (format-matched, scoring_format only)
`league_type` is hardcoded `"standard"` in the generate request (App.tsx), so dynasty ADP is unreachable from the UI — selection keys off `scoring_format` only:
- `ppr` → `adp_ppr`
- `half_ppr` → `adp_ppr`  *(assumption: half-PPR boards track PPR more closely than standard; no half-PPR ADP source exists)*
- `standard` → `adp_standard`

## Out of scope
- Exposing dynasty ADP / league_type as a real user setting (would unlock `adp_dynasty` selection).
- A dedicated half-PPR ADP data source.
- Bye-week / injury columns — not present on `TieredPlayer`, would need backend work.
- Per-user column customization.

## Open questions
None — debug mechanism (`?debug=1`) and content (cheat-sheet + value) confirmed by user.
