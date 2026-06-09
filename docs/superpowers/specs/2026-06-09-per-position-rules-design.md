# Per-Position Rules — Design

**Date:** 2026-06-09
**Status:** Approved
**Parent specs:** `2026-05-19-autotiers-design.md`, `2026-05-25-autotiers-advanced-rules-design.md`
**GitHub issue:** #189

---

## Goal

Allow users to restrict any rule to a subset of positions (e.g., "apply Declining Snap% to WR and TE only, not to RB or QB"). Today every rule fires against every position for which its conditions can be satisfied. This produces incorrect rankings when a stat-based threshold makes sense for one position but not another. The fix surfaces position scoping as a first-class, user-editable property of every rule — without making the common case (apply everywhere) harder to see or configure.

---

## Approach

### Storage — extend the JSON blob, not the DB schema

Add `positions: list[str] | null` to the rule representation everywhere it appears. `null` means "all positions" and is the default. An empty list `[]` is treated identically to `null` — both mean "no position filter applied." This avoids introducing a confusing "apply to none / disabled" semantic that would conflict with the existing `enabled` toggle.

The allowed position strings are `"QB"`, `"RB"`, `"WR"`, `"TE"`, `"K"`, `"DST"` — the same set used throughout the codebase (`PositionFilterValue` in the frontend, `player.position` on the backend).

`Profile.rules_json` already stores `[{ name, enabled, weight }]` per rule override. Extend that shape to `[{ name, enabled, weight, positions }]`. No DB migration. Any existing persisted record without `positions` deserializes with the field absent — code treats that as null/all-positions.

### Data model changes

**Backend — `Rule` dataclass (`backend/app/engine/rules.py`):**

```python
@dataclass
class Rule:
    name: str
    conditions: list[RuleCondition]
    effect: RuleEffect
    enabled: bool = True
    weight: float = 1.0
    description: str = ""
    positions: list[str] | None = None   # <-- new; None = all positions
```

**Backend — `RuleSchema` (`backend/app/schemas/rules.py`):**

```python
class RuleSchema(BaseModel):
    name: str
    conditions: list[RuleConditionSchema]
    effect: RuleEffectSchema
    enabled: bool = True
    weight: float = 1.0
    is_builtin: bool = False
    category: str = "Custom"
    description: str = ""
    positions: list[str] | None = None   # <-- new
```

**Frontend — `Rule` interface (`web/src/api/types.ts`):**

```typescript
export interface Rule {
  name: str;
  conditions: RuleCondition[];
  effect: RuleEffect;
  enabled: boolean;
  weight: number;
  is_builtin: boolean;
  category: string;
  description?: string;
  positions: string[] | null;   // <-- new; null = all positions
}
```

Also extend `Profile.rules_json` element type:

```typescript
rules_json: Array<{ name: string; enabled: boolean; weight: number; positions: string[] | null }>;
```

### Rule engine — position gate in `apply_rules`

Add a single early-exit check inside the `apply_rules` loop before condition evaluation:

```python
def apply_rules(base_score: float, ctx: PlayerContext, rules: list[Rule]) -> RuleResult:
    ...
    for rule in rules:
        if not rule.enabled:
            continue
        # Position gate: if positions list is non-empty, player must be in it.
        if rule.positions:
            if ctx.position not in rule.positions:
                continue
        if not all(_evaluate(c, ctx) for c in rule.conditions):
            continue
        ...
```

This is purely additive. Existing rules with `positions=None` or `positions=[]` pass through unchanged.

### Built-in rules — positions defaults and lock status

Several built-in rules already have position awareness implemented upstream in `generate.py` via `None`-gating of context fields (e.g. `prior_touches` is only set for RBs, `bad_offense_team` only for QB/RB/WR/TE). These are listed in the table below along with their correct default `positions` values. Declaring these defaults on the built-in `Rule` objects makes the data contract explicit and allows the UI to show users what's already restricted.

| Rule name | Default `positions` | Editable by user? |
|---|---|---|
| `RB Committee Penalty` | `["RB"]` | Yes — field conditions reference `carry_share`, which is only meaningful for RBs. But user may want to lock it to RB themselves. Editable so they can loosen it. |
| `Target Share Premium` | `["WR", "TE"]` | Yes |
| `370 Touches` | `["RB"]` | No — rule has `position == "RB"` as an explicit condition. Positions field is `["RB"]` and rendered read-only. Changing it would be misleading without changing the condition. |
| `Handcuff RB` | `["RB"]` | No — same reason: carries a semantic meaning tied to the position label. |
| `Over the Hill` | `["QB", "RB", "WR", "TE"]` | Yes — age thresholds are position-keyed; K/DST are excluded by design. User might want to narrow further. |
| `Year After the Year After` | `["RB", "WR"]` | Yes — upstream gating makes it safe to widen later if research supports it, but default is RB/WR. |
| `Bad Offense` | `["QB", "RB", "WR", "TE"]` | Yes |
| `Follow the Money` | `["QB", "RB", "WR", "TE"]` | Yes |
| All other rules | `null` (all positions) | Yes |

"Not editable" means two things concretely: the UI renders the position badges but not the edit control, and the backend ignores any `positions` override for those rule names sent via `POST /generate` or `PATCH /profiles/{id}` (the backend re-applies the locked value from `BUILTIN_RULES` during the merge step).

### API — merge behavior

`POST /generate` merges the client-supplied `rules: list[RuleSchema]` with `BUILTIN_RULES` by name. Currently the merge overwrites `enabled` and `weight` from the client payload. Extend the merge to also apply `positions` from the client payload, **except** for locked rules (see table above), where the built-in positions value is always used.

Merging approach in pseudocode:

```python
LOCKED_POSITIONS = {"370 Touches", "Handcuff RB"}

def merge_rule(builtin: Rule, override: RuleSchema) -> Rule:
    positions = (
        builtin.positions
        if builtin.name in LOCKED_POSITIONS
        else (override.positions if override.positions is not None else builtin.positions)
    )
    return Rule(
        ...existing merge fields...,
        positions=positions,
    )
```

### UI — inline position selector inside `RuleItem` expanded section

The existing `RuleItem` has a collapsible expanded section that already shows description, weight input, and Low/High suggestion buttons. Position scoping belongs in this same section — it is an advanced control that should not clutter the default collapsed row.

**Expanded section layout (additions only):**

Below the weight input row, add a "Positions" row:

- Label: `"Positions"` in the same `text-xs text-muted-foreground` style as the description.
- Control: a row of small toggle buttons, one per position: `QB RB WR TE K DST`. Buttons use `variant="outline"` when off and `variant="default"` when on (matching the `PositionFilter` pattern exactly). An additional `"All"` button at the start acts as "select none / apply to all" — pressing it clears the selection. When all individual positions are selected, the display automatically reverts to showing "All" as active.
- When the rule's `positions` is `null` or `[]`, "All" is visually active and all position buttons are in their off/outline state.
- When `positions` is non-empty, "All" is in outline state and matching position buttons are filled/default.
- Locked rules (see table above): render the position badges as plain `<span>` elements with `bg-muted text-muted-foreground` styling, no interactive controls. A parenthetical "(locked)" in the same muted style follows the position list.

**No separate position filter tab in RulesPanel.** A tab/filter approach (option c from the brief) would reduce visible rules to those relevant to a position but forces users to visit each position tab to configure a rule they want to apply broadly. Given that most users are configuring 1–3 rules per session, the inline control inside the existing expand pattern is lower friction and doesn't require a new navigation layer.

**`onChange` contract:** When the user toggles a position button, `RuleItem` calls `onChange({ ...rule, positions: <new array or null> })`. The parent chain (`RuleCategory` → `RulesPanel` → `App.tsx`) is unchanged — the existing `updateRule` path already passes the full `Rule` object through.

**"All" → `null` mapping:** When the user clicks "All" or deselects the last active position, set `positions: null`. Do not set `positions: []`. Both are semantically equivalent at the engine but `null` is the canonical "apply everywhere" value; keeping it consistent prevents spurious diff noise in autosave PATCH calls.

**Visual example — collapsed row (unchanged):**

```
[switch] Declining Snap%                                    [v]
```

**Visual example — expanded row with positions set to WR, TE:**

```
[switch] Declining Snap%                                    [^]
  Penalizes players whose offensive snap share dropped under 55%...
  [All] [QB] [RB] [WR*] [TE*] [K] [DST]
  − [  7  ] %    [Low: −5%]  [High: −20%]
```

(* = filled/active button)

**Visual example — locked rule expanded:**

```
[switch] 370 Touches                                        [^]
  Penalizes RBs who absorbed 370+ touches...
  Positions: RB (locked)
  − [ 10 ] %    [Low: −5%]  [High: −20%]
```

### Keyboard and accessibility

- Each position toggle button must have `aria-label="Toggle {POSITION}"` and `aria-pressed={boolean}`.
- The "All" button: `aria-label="Apply to all positions"` and `aria-pressed={allPositionsActive}`.
- The positions row as a group: wrap in a `<div role="group" aria-label="Position scope">`.
- Tab order within the expanded section: description (non-interactive) → positions group → magnitude input → Low suggestion → High suggestion.
- Locked positions: rendered as `<span>` with no tab stop. The "(locked)" text is inline, no tooltip.

### Autosave

No changes needed. `positions` is just another field on the `Rule` object. `useAutoSave` watches the rules array and PATCHes `rules_json` on change. The PATCH payload already serializes the full rule override shape; adding `positions` to the type is sufficient.

---

## User-facing impact

**Common case — user doesn't touch positions:** Zero change. The expanded section shows "All" as active by default for rules with `positions: null`. The rule behaves as before.

**Power user use case:** A user who disagrees that "Declining Snap%" should apply to QBs (whose snap% is nearly always 100%) can open the rule, deselect QB, and the rule will fire only on RB/WR/TE/K/DST. The next Generate picks it up immediately.

**Discovery:** Position scoping is visible only when the user expands a rule item. The collapsed row continues to show only the toggle and the rule name. Users who don't need this feature never see it cluttering their workflow.

**Copy conventions:**

- Position toggle group label: `"Positions"` — no explanation needed; the buttons are self-describing.
- Locked rule footnote: `"Positions: {list} (locked)"` — "locked" is plain English and honest; it means the backend enforces it regardless of user action.
- No toast or confirmation on position change. Changes are silent autosave, same as weight and enabled changes.

---

## Code-facing impact

Files that change:

| File | Change |
|---|---|
| `backend/app/engine/rules.py` | Add `positions: list[str] \| None = None` to `Rule` dataclass |
| `backend/app/engine/builtin_rules.py` | Add `positions=[...]` to the 8 rules listed in the table above |
| `backend/app/schemas/rules.py` | Add `positions: list[str] \| None = None` to `RuleSchema` |
| `backend/app/api/generate.py` | Extend merge logic to carry `positions` through; enforce locked set |
| `web/src/api/types.ts` | Add `positions: string[] \| null` to `Rule` interface; extend `rules_json` element type |
| `web/src/components/RuleItem.tsx` | Add positions toggle group in expanded section; handle locked display |
| `web/src/components/RuleItem.test.tsx` (new or extend) | Tests for positions toggle rendering and onChange behavior |

Files that do NOT change:

- `RulesPanel.tsx` — pass-through of `onChange` is unchanged
- `RuleCategory.tsx` — pass-through of `onChangeRule` is unchanged
- `App.tsx` — `updateRule` is unchanged
- `useAutoSave` — no change needed; watches the rules array reference
- DB schema / migrations — no change; `rules_json` is JSONB

**Backend merge location:** The rule merge logic currently lives in `generate.py`. The locked-positions enforcement (`LOCKED_POSITIONS` set) also lives there, not in the schema validator. Reason: a schema validator would correctly reject unknown overrides, but "locked" is a business rule, not a type constraint — it belongs with the generation logic where the full built-in rule list is available for comparison.

**Backward compatibility:** Existing `Profile.rules_json` rows have no `positions` key. Pydantic's `None` default and Python's dataclass default both handle missing fields gracefully. No data migration needed.

---

## Out of scope

- **Custom user-created rules.** The current system has no UI for creating a rule from scratch. Per-position scoping applies only to built-in rules in this iteration.
- **Position-specific weight values.** For example, "apply this rule at weight 1.0 for WR but 0.5 for TE." That requires a fundamentally different data model (a map from position to weight). Not in scope here; `weight` remains a single scalar per rule.
- **The `PositionFilter` in `TiersPanel.tsx`.** This feature does not change how the Tiers panel filters display — it changes how rules are evaluated upstream in generation. These are independent.
- **K and DST rule design.** Kickers and defenses rarely have useful non-flag rules. The position toggle buttons include K and DST so the system is consistent and complete, but no built-in rules are being added for those positions here.
- **Reordering rules** or grouping them by the positions they apply to. Category grouping is unchanged.
- **Analytics or diff view** showing how per-position scoping changed a specific player's score. The existing `rule_applications` array on `TieredPlayer` already records which rules fired; that is sufficient.

---

## Open questions

None that block implementation. The following are flagged for the Engineer's awareness but have defined answers:

1. **What if a user sends `positions: []` via the API?** Treat identically to `null` — apply to all positions. Document this in a code comment next to the `if rule.positions:` guard. The guard is falsy for both `None` and `[]`.

2. **Should the `GET /rules` endpoint return the default `positions` on built-in rules?** Yes. The frontend reads `GET /rules` to populate the initial rule list. If `positions` is present on the returned schema, the UI will correctly display the defaults (e.g., showing `["RB", "WR"]` for "Year After the Year After") on first load without any client-side knowledge of which rules have defaults. This means `RuleSchema` must serialize `positions` in the response, which it will once the field is added.
