# Design Artifact: Customizable Tier Count + Tier Name Editor

**Date:** 2026-06-06
**Stage:** Design (Stage 1)
**Engineer handoff target:** After mathematician's backend field-name spec is confirmed (see Open Questions)
**Mathematician coordination required:** Yes — backend contract for `overall_tier_count` and `tier_names` fields

---

## Summary

Extend the existing Tier Labels section in `SettingsPanel` with:
1. A tier-count control (how many overall tiers the engine produces).
2. A name-editor that grows/shrinks to match the count, with sensible defaults beyond tier 6.

This is an extension of existing `SettingsPanel` UI, not a new panel or dialog. The tier-count control is new; the tier-name editor already exists in skeletal form (6 hardcoded rows) and will be driven by count going forward.

---

## Flow

User opens the app -> views SettingsPanel -> scrolls to "Tier Labels" section -> sees a "Number of Tiers" select above the name rows -> changes count -> row list grows or shrinks -> optionally edits names inline -> generates -> TiersPanel renders with user-defined names.

---

## Where the Control Lives

**Extend `SettingsPanel`, not a new panel or dialog.**

Rationale:
- Tier count is a generation parameter like `draft_rounds`. Both live in `SettingsState` today. Separating them would split logically coupled controls.
- A dialog would require the user to open/close it to make related adjustments (count + names + scoring format). That is friction on a control users will tune before every draft.
- The "15-25 rows is a lot of vertical space" concern is handled with a collapsible wrapper (Radix `Collapsible` is already in `web/src/components/ui/collapsible.tsx`), not with a dialog.

**Layout of the Tier Labels section (after this change):**

```
Tier Labels                        [Reset all]   [v collapse toggle]
  Number of Tiers   [Select 6 ▾]
  ─────────────────────────────────
  Tier 1   [____________]           (placeholder: "Elite")
  Tier 2   [____________]           (placeholder: "Strong Starter")
  ...
  Tier N   [____________]           (placeholder: "<default for tier N>")
```

The collapsible is **open by default**. Toggle persists only in React state (not saved to profile), so it resets on page reload — intentional, the user needs to see names they've set.

---

## Tier Count Control

**Widget:** `Select` (matches the `draft_rounds` Select immediately above; maintains visual language).

**Options:** Integers 4 through 20 (inclusive). Presented as "4 tiers", "5 tiers", etc. The engineer may adjust the upper bound after consulting the mathematician on practical backend limits — flag as an open question.

**Default value:** `draft_rounds` at the time the feature ships. For existing profiles the default is whatever `draft_rounds` is currently stored, NOT a hardcoded 6. This is set once on feature adoption:
- The `DEFAULT_SETTINGS` object in `App.tsx` gains `tier_count: 15` (matching the existing `draft_rounds` default).
- On profile hydration, if `settings_json` has no `tier_count`, the app falls back to `settings.draft_rounds`. This avoids a breaking migration for stored profiles.

**ID in `SettingsState`:** `tier_count: number` (see State Shape below).

**Relationship to `draft_rounds`:** `draft_rounds` and `tier_count` are independent controls after initial seeding. The user can set 20 draft rounds but only 8 tiers, or vice versa. The previous linkage (default count = draft_rounds) only applies at first load/creation.

---

## Name Editor Rows

**Row count:** Derived from `tier_count`. When `tier_count` changes, the displayed rows grow or shrink accordingly.

**Name preservation on shrink:** When the user lowers `tier_count` from N to M (M < N), rows M+1 through N are hidden but their `tier_labels` overrides are **preserved** in `SettingsState`. They are not sent in the `GenerateRequest`. If the user raises count back to N, their previously typed names reappear. This is consistent with how `draft_rounds` changes don't wipe other settings.

**Empty-name handling:** When a name input is empty or whitespace-only (blurred), that tier's key is deleted from `tier_labels` (matching the existing `handleTierLabelBlur` behavior). `getCustomTierLabel` already falls back to `getTierLabel`, which falls back to the extended default scheme (see below). No change needed to `getCustomTierLabel`.

**Placeholder text:** Each row's `Input` placeholder shows the default name for that tier — the extended default for tiers 7+.

---

## Default Name Scheme for Tiers Beyond 6

The current static `TIER_LABELS` covers tiers 1-6. Tiers 7+ fall back to "Late Round" universally, which is unusable as a placeholder when there are 12 distinct tiers.

**Proposed extended scheme (to be added to `tiers.ts`):**

| Tier | Default label |
|------|---------------|
| 1 | Elite |
| 2 | Strong Starter |
| 3 | Starter |
| 4 | Flex Starter |
| 5 | Streamers / Deep Flex |
| 6 | Handcuff / Late Round |
| 7 | Deep Sleepers |
| 8 | Lottery Tickets |
| 9 | IR Stash |
| 10 | Waiver Wire |
| 11 | Practice Squad |
| 12+ | Late Round (ordinal suffix) — e.g., "Tier 13", falling back gracefully |

Tiers 7-11 get named entries in `TIER_LABELS`. Tiers 12+ use a computed fallback of `"Late Round"` as today (their placeholder will read "Late Round" since `getTierLabel` returns that — acceptable because 12+ tiers is unusual).

The engineer updates `TIER_LABELS` in `web/src/lib/tiers.ts` with entries for tiers 7-11. The `getTierLabel` function signature does not change; neither does `getCustomTierLabel`.

**Tests to update in `web/src/tests/lib/tiers.test.ts`:**
- The existing test `"exports a record with exactly 6 entries"` must be updated to `11` (or to check that keys 1-11 exist, without a hard count).
- Add `it.each` cases for tiers 7-11 in the `getTierLabel` suite.

---

## State Shape Additions

### `SettingsState` (in `web/src/components/SettingsPanel.tsx`)

Add:

```ts
tier_count?: number;   // absent = fall back to draft_rounds for backward compat
```

`tier_labels` already exists as `Partial<Record<number, string>>`. No change to its type. The editor continues to write to it the same way; the count control just determines how many rows are rendered.

### `GenerateRequest` (in `web/src/api/types.ts`)

Add two fields — **exact names pending mathematician reconciliation (see Open Questions)**:

```ts
overall_tier_count?: number;   // number of tiers the engine should produce
tier_names?: Record<number, string>; // resolved names for each active tier
```

`tier_names` is the **resolved** map (defaults filled in, not the sparse override-only map). The engineer builds the resolved map in `App.tsx`'s `buildRequest()` using a helper:

```ts
function buildResolvedTierNames(
  tierCount: number,
  overrides: Partial<Record<number, string>> | undefined
): Record<number, string> {
  const result: Record<number, string> = {};
  for (let t = 1; t <= tierCount; t++) {
    result[t] = getCustomTierLabel(t, overrides);
  }
  return result;
}
```

This helper belongs in `web/src/lib/tiers.ts` and should be exported. It is a pure function that can be unit-tested without rendering.

### `DEFAULT_SETTINGS` (in `web/src/App.tsx`)

```ts
tier_count: 15,  // matches draft_rounds default
```

### CSV export (`web/src/lib/csv.ts` + `web/src/api/hooks.ts`)

`downloadCsv` already accepts `tierLabelOverrides`. After this change, the caller in `App.tsx` should pass the **resolved names map** (not the sparse overrides) so that tiers 7+ get proper names rather than the static "Late Round" fallback when no override was typed. Change the call site in `App.tsx`:

```ts
// Before
downloadCsv(generate.data.players, settings.tier_labels);

// After
downloadCsv(
  generate.data.players,
  buildResolvedTierNames(settings.tier_count ?? settings.draft_rounds, settings.tier_labels)
);
```

This is a backward-compatible change — `generateCsvString` already uses `getCustomTierLabel` with the map.

---

## Interaction Details

### Count changes

1. User changes "Number of Tiers" select.
2. `set("tier_count", n)` fires immediately; `SettingsState` updates.
3. Tier label rows rerender to show exactly n rows (1 through n).
4. Rows that reappear (count raised) show the stored override if present, or the default placeholder.
5. Autosave fires after 800ms debounce as normal.

### Per-tier reset button

Unchanged from existing behavior: appears only when that tier has a non-empty, non-default override. Uses `RotateCcw` icon with `aria-label="Reset tier N label"`.

### Reset all button

Unchanged: appears when `hasAnyOverride`, clears all `tier_labels` overrides. Does not reset `tier_count`.

### Collapsible toggle

- Default state: open.
- Chevron icon (`ChevronDown` / `ChevronUp` from lucide-react) in the section header.
- `aria-expanded` on the trigger button.
- `CollapsibleContent` wraps both the count select and all name rows.
- When collapsed, the header still shows "Tier Labels" and the Reset all button (if active). This avoids hiding the "you have customizations" signal.

### Section header layout

```
[Tier Labels]                [Reset all (conditional)]  [ChevronDown button]
```

All three on one flex row. The chevron button is icon-only with `aria-label="Expand tier labels"` / `"Collapse tier labels"` based on open state.

---

## Render States

**State: No overrides, default count, collapsed**
User sees: "Tier Labels" header with chevron. No Reset all. Content hidden.
Next action: Click chevron to expand.

**State: No overrides, default count, expanded**
User sees: Count select (showing 15), 15 rows with placeholder text only, no reset buttons.
Next action: Type in a row, or change count.

**State: Some overrides, any count, expanded**
User sees: Count select, rows for 1..N. Rows with overrides show filled input + per-row reset button. "Reset all" in header.
Next action: Edit more names, click per-row reset, click Reset all, generate.

**State: Some overrides, collapsed**
User sees: Header with "Reset all" visible — signals the user that customizations are active even when collapsed. Chevron shows up-pointing (collapsed, meaning "content is hidden"). Wait — this is an inversion. Use: open = chevron pointing down (standard), closed = chevron pointing right. When open state is true, button shows ChevronUp (click to collapse). When open is false, shows ChevronDown (click to expand).

**State: Count reduced, hidden rows have overrides**
User sees: Fewer rows; previously visible row names are gone from view. If they set names for tiers 8-12 and drop to 6 tiers, those names are invisible. No indication they exist.
Design decision: Accept this. The names are in state and will reappear. A warning like "3 hidden tier names" adds complexity without much value — the user can re-expand count to see them.

---

## Error and Edge Cases

**Tier count below minimum (< 4):** Disallow in the Select — minimum option is 4. No runtime guard needed.

**Tier count above maximum:** The Select caps at 20. If the mathematician specifies a lower max, reduce the option list.

**`tier_count` absent from stored profile (legacy profiles):** Fall back to `settings.draft_rounds` wherever `tier_count` is consumed. In the Select, `value={String(settings.tier_count ?? settings.draft_rounds)}` shows the draft_rounds value.

**`draft_rounds` changes after `tier_count` is set:** They are independent. Changing draft rounds does not change tier count. User manages them separately.

**Name input wider than the column on narrow screens:** The SettingsPanel sidebar is 300px wide (`lg:grid-cols-[300px_...]`). At 300px, the row layout `[Tier N label] [Input] [Reset icon]` is tight but workable. The `shrink-0 w-12` on the tier label text is already in the existing code. No change needed. The Reset icon button is 32px. Input gets `flex-1` and will shrink to fill remaining space.

**Count field shows the wrong value after profile switch:** Profile hydration sets `settings` from `active.settings_json`. If `tier_count` is in `settings_json` it loads correctly. If absent, the fallback to `draft_rounds` applies. No special handling needed.

---

## How TiersPanel Consumes User-Supplied Names

`TiersPanel` already receives `tierLabelOverrides?: Partial<Record<number, string>>` and passes it to `getCustomTierLabel`. No signature change needed on `TiersPanel`.

The change is in `App.tsx`: pass the **resolved names map** instead of the sparse overrides map:

```ts
// In the JSX:
tierLabelOverrides={buildResolvedTierNames(
  settings.tier_count ?? settings.draft_rounds,
  settings.tier_labels
)}
```

This ensures tiers 7+ display the extended default names rather than "Late Round" for every tier beyond 6. The resolved map is computed in the render on every settings change. It is cheap (a for-loop over at most 20 iterations) and does not need memoization.

---

## Component Checklist for Engineer

1. **`web/src/lib/tiers.ts`**
   - Extend `TIER_LABELS` with entries for tiers 7-11.
   - Add and export `buildResolvedTierNames(tierCount: number, overrides: Partial<Record<number, string>> | undefined): Record<number, string>`.

2. **`web/src/api/types.ts`**
   - Add `overall_tier_count?: number` and `tier_names?: Record<number, string>` to `GenerateRequest`. (Field names pending mathematician confirmation.)

3. **`web/src/components/SettingsPanel.tsx`**
   - Add `tier_count?: number` to `SettingsState`.
   - Add a `TIER_COUNT_OPTIONS` constant: `[4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]`.
   - Replace the hardcoded `TIER_LABEL_ROWS = [1..6]` with a derived array: `Array.from({ length: effectiveTierCount }, (_, i) => i + 1)` where `effectiveTierCount = value.tier_count ?? value.draft_rounds`.
   - Wrap the entire "Tier Labels" section in a `Collapsible` / `CollapsibleContent`.
   - Add the count `Select` as the first control inside `CollapsibleContent`, before the name rows.
   - Move "Reset all" and the chevron button into the section header, on one flex row.

4. **`web/src/App.tsx`**
   - Add `tier_count: 15` to `DEFAULT_SETTINGS`.
   - Import `buildResolvedTierNames` from `@/lib/tiers`.
   - In `buildRequest()`, add `overall_tier_count` and `tier_names` fields using `buildResolvedTierNames`.
   - Update `downloadCsv` call to pass resolved names.
   - Update the `tierLabelOverrides` prop on `TiersPanel` to pass the resolved names map.

5. **`web/src/tests/lib/tiers.test.ts`**
   - Update the "exports a record with exactly 6 entries" test to reflect 11 entries.
   - Add `it.each` rows for tiers 7-11 in `getTierLabel` suite.
   - Add tests for `buildResolvedTierNames`: empty overrides returns all defaults; overrides replace defaults; count boundary (tier count = 1, count = 20).

6. **`web/src/tests/components/SettingsPanel.test.tsx`**
   - Existing tests exercise tiers 1-6 and must continue to pass.
   - Add: "number of tiers select renders with default value equal to draft_rounds when tier_count is absent".
   - Add: "changing tier count renders the correct number of rows".
   - Add: "reducing tier count hides rows beyond the new count".
   - Add: "restoring tier count reveals previously typed names".
   - Add: "collapsible toggle hides and shows tier label rows".
   - Add: "reset all button is visible in collapsed header when overrides exist".

---

## Accessibility Requirements

- Collapsible trigger: icon-only button with `aria-label="Expand tier labels"` / `"Collapse tier labels"`. Must respond to `Enter` and `Space`.
- Count select: `<Label htmlFor="tier-count-select">Number of Tiers</Label>` with matching `id`. Or wrap in standard `<Select>` with `aria-label` if Label association is awkward.
- Name inputs: existing `aria-label={Tier ${tier} label}` pattern continues unchanged.
- Per-tier reset buttons: existing `aria-label="Reset tier N label"` pattern unchanged.
- No new focus traps introduced. The collapsible is not a modal.

---

## Out of Scope (Each = Potential GitHub Issue)

1. **Tier count tied to draft rounds dynamically.** Today's proposal: they are independent after initial seed. A "sync to draft rounds" affordance (e.g., a lock icon) is a follow-on.
2. **Positional tier name editing.** `POSITIONAL_TIER_LABELS` is explicitly excluded per the product brief.
3. **Tier count as a per-position setting** (e.g., 6 RB tiers, 4 QB tiers). The engine always assigns a single `overall_tier` per player. Out of scope.
4. **Reordering tier rows via drag-and-drop.** Out of scope; tiers are ordinal.
5. **Color coding per tier.** The TierGroup header background (`bg-muted/60`) is uniform; per-tier color assignment is a separate feature.
6. **Importing/exporting tier name presets.** Profile import/export is a broader feature not scoped here.
7. **Tier count persisted separately from settings_json.** Currently all settings go into one `settings_json` blob. A schema migration to give `tier_count` a first-class backend column is out of scope for this feature.

---

## Open Questions (Engineer Reconcile with Mathematician)

1. **Backend field names.** The mathematician names the `GenerateRequest` fields. This artifact uses `overall_tier_count` and `tier_names` as placeholders. Once confirmed, update `GenerateRequest` in `types.ts` and `buildRequest()` in `App.tsx`.

2. **Does the backend use `tier_names` at all, or only `overall_tier_count`?** If the backend assigns names purely for return-trip labeling, `tier_names` may be a frontend-only concern (names applied to `TieredPlayer.overall_tier` on the client). If the backend needs them for grouping or export, they belong in the request. Clarify before implementing.

3. **Maximum tier count the engine supports.** The UI caps at 20; if the mathematician specifies a lower or higher practical ceiling, adjust `TIER_COUNT_OPTIONS`.

4. **Minimum meaningful tier count.** The UI floor is 4. Confirm this is acceptable with the mathematician — very few tiers may produce degenerate groupings.

5. **Backward compatibility of stored profiles without `tier_count`.** The frontend fallback to `draft_rounds` is defined here. Confirm the backend does not require `overall_tier_count` to be present (i.e., it should have its own default, likely 6 or draft_rounds-derived).

6. **`SettingsPanel.test.tsx` `baseSettings` uses `weight_prior_year/weight_espn/weight_consensus` as keys inside `weights`.** The current `Weights` type in `lib/weights.ts` should be verified — `SettingsState` has `weights: Weights` and `ScoreWeights` uses `prior` and `consensus` keys. The test's `baseSettings` may be stale and could cause false failures when the engineer adds new tests. Flag for the engineer to verify and fix `baseSettings` in the test file (pre-existing issue, not introduced by this feature).
