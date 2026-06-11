# Position-First Rules UX — Design

**Date:** 2026-06-09
**Status:** Draft
**Supersedes:** `2026-06-09-per-position-rules-design.md` (the earlier per-rule position toggle design remains implemented and in production; this design replaces the entire rules UX on top of a new data model)
**GitHub issue:** TBD

---

## 1. Goal

Invert the rules UX. Today the user sees every rule at once and can restrict each rule to a set of positions inside an expand/collapse section. That model is confusing: a user optimizing RBs must mentally filter out the 12 rules that don't apply, and editing the same rule for different positions requires setting it once and hoping the weight is universal.

The new model: the user picks a position first (QB / RB / WR / TE / K / DST), and only the rules that are meaningful for that position are displayed. Each rule stores enabled/weight settings **per position independently** — "Target Share Premium" can be weight 2.0 for WR and weight 0.5 for TE without any gymnastics. The generate request sends the complete per-position picture to the backend, which applies each rule only to its position's players.

---

## 2. Approach

### 2.1 Data model recommendation: Format A (position-keyed object)

Two formats were considered:

**Format A (recommended):**
```json
{
  "QB": [
    { "name": "New Team Penalty", "enabled": true, "weight": 1.0 },
    { "name": "Favorites", "enabled": true, "weight": 1.5 }
  ],
  "RB": [
    { "name": "New Team Penalty", "enabled": true, "weight": 0.5 },
    { "name": "RB Committee Penalty", "enabled": true, "weight": 1.0 }
  ]
}
```

**Format B:**
```json
[
  { "name": "New Team Penalty", "position": "QB", "enabled": true, "weight": 1.0 },
  { "name": "New Team Penalty", "position": "RB", "enabled": true, "weight": 0.5 }
]
```

Format A is recommended because:
- The backend merge loop reads "rules for position X" with a single dict lookup, not a filter scan over the whole list.
- The frontend's active-position state maps directly to a key: `rulesState["RB"]` is the list to display.
- Profile hydration and autosave both deal with a single dict structure rather than deduplication logic.
- JSON storage size is comparable; neither format is obviously larger.
- Format B requires the backend to handle duplicate names across the list; Format A makes the structure self-describing.

### 2.2 Hardcoded position-to-rules mapping

The product owner has defined exactly which rules appear under each position tab. This mapping is **authoritative** — the frontend filters the canonical rule list from `GET /rules` down to only these names for the active position. The backend uses the same mapping to determine which position's override to apply when scoring a player.

```
QB:  New Team Penalty, New Head Coach, Sophomore Leap, Bad Offense,
     Follow the Money, Injury History, TD Regression,
     Opportunity Over-Producer, Opportunity Under-Producer,
     Red Zone Usage Premium, Projection Unavailable,
     Year After the Year After, Over the Hill, Favorites

RB:  RB Committee Penalty, Target Share Premium, Declining Snap%,
     New Team Penalty, New Head Coach, Sophomore Leap, Bad Offense,
     Follow the Money, Injury History, TD Regression,
     Opportunity Over-Producer, Opportunity Under-Producer,
     Red Zone Usage Premium, Projection Unavailable,
     Year After the Year After, Over the Hill, Favorites

WR:  Target Share Premium, Declining Snap%, New Team Penalty,
     New Head Coach, Sophomore Leap, Bad Offense, Follow the Money,
     Injury History, TD Regression, Opportunity Over-Producer,
     Opportunity Under-Producer, Red Zone Usage Premium,
     Projection Unavailable, Year After the Year After,
     Over the Hill, Favorites

TE:  Target Share Premium, Declining Snap%, New Team Penalty,
     New Head Coach, Sophomore Leap, Bad Offense, Follow the Money,
     Injury History, TD Regression, Opportunity Over-Producer,
     Opportunity Under-Producer, Red Zone Usage Premium,
     Projection Unavailable, Year After the Year After,
     Over the Hill, Favorites

K:   Projection Unavailable, Year After the Year After,
     Over the Hill, Favorites

DST: Projection Unavailable, Favorites
```

This mapping lives in a single constant in the frontend at `web/src/lib/positionRulesMap.ts`. The backend does not need to store or validate the mapping — it simply applies whichever overrides appear for a position in the request.

### 2.3 Rules omitted from all position tabs

These BUILTIN_RULES have no entry in any position's mapping:

| Rule | Reason for omission |
|---|---|
| `370 Touches` | Implicit in `RB Committee Penalty`; adds noise for RB users. Backend continues to apply it from BUILTIN_RULES defaults — users cannot configure it. |
| `Contract Year Flag` | FLAG type (no score change). Hidden today by the frontend's `r.effect.type !== "flag"` filter. Remains hidden. |
| `Handcuff RB` | FLAG type. Remains hidden. |
| `Availability Risk` | FLAG type. Remains hidden. |

These rules continue to fire in the backend via their BUILTIN_RULES defaults. They are not sent in the `rules` field of the generate request; instead the backend engine falls back to the built-in enabled/weight for any rule not overridden by the client. **Decision: keep them applying silently.** Removing them would change scoring behavior and require a mathematician review. They are informational flags or a single RB-specific threshold that the product owner did not surface — not disabling them is correct.

### 2.4 BUILTIN_RULES positions field updates

The new UX makes the `positions` field on each built-in rule a backend-only signal that constrains which players a rule can fire for. The product-owner mapping now drives frontend display, but the backend still needs `positions` set correctly to gate scoring correctly.

Required updates to `backend/app/engine/builtin_rules.py`:

| Rule | Current `positions` | New `positions` | Reason |
|---|---|---|---|
| `Target Share Premium` | `["WR", "TE"]` | `["RB", "WR", "TE"]` | Now appears in RB tab; RBs can have high target share in PPR |
| `Declining Snap%` | `None` (all positions) | `["RB", "WR", "TE"]` | Now appears only in RB/WR/TE tabs; does not appear for QB (near-100% snap always), K, DST |
| `Year After the Year After` | `["RB", "WR"]` | `["QB", "RB", "WR", "TE", "K"]` | Now appears in QB/RB/WR/TE/K tabs per product owner |
| `Over the Hill` | `["QB", "RB", "WR", "TE"]` | `["QB", "RB", "WR", "TE", "K"]` | Now appears in K tab per product owner; `OVER_THE_HILL_AGE` dict in `generate.py` needs `"K"` entry — **open question below** |
| `Projection Unavailable` | `None` (all positions) | `None` (all positions) | No change; appears in all tabs |
| `Favorites` | `None` (all positions) | `None` (all positions) | No change; appears in all tabs |

All other rules' `positions` fields are unchanged from the currently-shipped values.

**Over the Hill for K — open question flagged in section 7.**

Additionally, the `conditions` field on `Year After the Year After` currently gates on `injured_two_years_ago`, which is only computed for `RB` and `WR` in `generate.py` (the `if player.position in ("RB", "WR")` block). Extending that rule to QB/TE/K requires also computing `injured_two_years_ago` for those positions in the generate loop. This is a backend logic change: the `two_seasons_ago` stat lookup and the `< 12 games` condition should run for `QB`, `TE`, and `K` as well. See section 4 file-change list.

### 2.5 New storage format — `rules_json` column

The `Profile.rules_json` column changes from:

```json
[{ "name": "...", "enabled": true, "weight": 1.0, "positions": ["QB","RB"] }]
```

to:

```json
{
  "QB": [{ "name": "New Team Penalty", "enabled": true, "weight": 1.0 }],
  "RB": [{ "name": "New Team Penalty", "enabled": true, "weight": 0.5 },
         { "name": "RB Committee Penalty", "enabled": false, "weight": 1.0 }]
}
```

Only rules whose settings differ from the built-in defaults need to appear. A rule absent from a position's list is treated as enabled=true, weight=1.0 (the built-in default). This mirrors the current sparse-override pattern.

The column is typed as `JSONB` on Postgres and `JSON` on SQLite. The column type (`list` in the Python ORM annotation) must change to `dict`. The `ProfileOut` schema must change `rules_json: list[dict]` to `rules_json: dict[str, list[dict]]`. The `ProfileCreate` and `ProfileUpdate` schemas must match.

### 2.6 Generate API — new `rules` field shape

The current `GenerateRequest.rules` field is `list[RuleSchema]` — a flat list of full rule objects (conditions, effect, weight, enabled, positions). Under the new model the frontend no longer sends the full rule object with conditions and effect. Those fields are authoritative on the backend (BUILTIN_RULES). The frontend sends only overrides: which rules to change from their defaults, keyed by position.

New `rules` field type in `GenerateRequest`:

```python
rules: dict[str, list[RuleOverrideSchema]] = Field(default_factory=dict)
```

Where `RuleOverrideSchema` is a new minimal schema:

```python
class RuleOverrideSchema(BaseModel):
    name: str
    enabled: bool
    weight: float
```

The dict key is the position string (`"QB"`, `"RB"`, etc.). The value is the list of per-position overrides for that position's rules. Only rules that differ from defaults need to be present; the backend fills in defaults for any rule not listed.

This is a **breaking change** to the `POST /generate` endpoint. It is internal-only (frontend is the sole caller), so no versioning ceremony is needed.

New generate request body shape:

```json
{
  "scoring_format": "ppr",
  "league_size": 12,
  "draft_rounds": 15,
  "qb_td_points": 4,
  "bonus_100yd_rushing": false,
  "bonus_100yd_receiving": false,
  "bonus_first_downs": false,
  "weight_prior_year": 0.30,
  "weight_espn": 0.0,
  "weight_consensus": 0.70,
  "overall_tier_count": 12,
  "rules": {
    "QB": [
      { "name": "New Team Penalty", "enabled": true, "weight": 1.5 }
    ],
    "RB": [
      { "name": "RB Committee Penalty", "enabled": false, "weight": 1.0 },
      { "name": "Target Share Premium", "enabled": true, "weight": 2.0 }
    ]
  },
  "keepers": null,
  "league_adp": null
}
```

### 2.7 Backend merge logic rewrite

The current merge in `generate.py` (`_run_generate`) takes the flat `rules` list, matches by name against `BUILTIN_RULES`, and replaces `enabled`/`weight`/`positions` per rule. Under the new model:

1. Start from `BUILTIN_RULES` as the complete authoritative rule list.
2. For each player being scored, get their position.
3. Look up `req.rules.get(player.position, [])` to get that position's overrides as a dict keyed by rule name.
4. For each BUILTIN_RULE, check if there is an override for `(rule.name, player.position)`. If yes, apply enabled/weight from the override. If no, use the built-in default.
5. Pass the resulting `list[Rule]` (with each rule's `positions` already set to exactly the player's position, or left as-is for backend gating) into `apply_rules`.

This changes the merge from a one-time pre-pass to a per-player operation. The performance impact is negligible: BUILTIN_RULES has ~20 entries, and the per-player dict lookup is O(1). The player loop already does comparable work for each player.

Concretely, the `_run_generate` function changes:

```python
# OLD: single merged list, then apply_rules per player
rules = list(merged.values())
...
rule_result = apply_rules(blended, ctx, rules)

# NEW: per-player rule list built from per-position overrides
def _build_rules_for_position(position: str, req: GenerateRequest) -> list[Rule]:
    override_map = {o.name: o for o in req.rules.get(position, [])}
    result = []
    for builtin in BUILTIN_RULES:
        o = override_map.get(builtin.name)
        rule = dataclasses.replace(
            builtin,
            enabled=o.enabled if o else builtin.enabled,
            weight=o.weight if o else builtin.weight,
        )
        result.append(rule)
    return result

...
rules_for_player = _build_rules_for_position(player.position, req)
rule_result = apply_rules(blended, ctx, rules_for_player)
```

The `LOCKED_POSITIONS` concept and `_merge_positions` helper are removed — they were needed to prevent per-rule position overrides from the old flat model, which no longer exists.

The `custom_rules` code path (rules not in `BUILTIN_RULES` by name) is removed. The new `RuleOverrideSchema` only accepts overrides by name against the known built-in list. Unknown names are silently ignored (no error needed — malformed client payloads don't break generation; they just don't apply).

---

## 3. User-facing impact

### 3.1 UX flow

**Current flow:**
1. User opens RulesPanel. Sees all rules grouped by category (Age/Longevity, Usage, Situation, Regression, Personal).
2. User clicks a rule to expand it. Adjusts enabled/weight. Optionally sets position filter via the toggle row.
3. Changes autosave.

**New flow:**
1. User opens RulesPanel. Sees a position tab strip at the top: `QB | RB | WR | TE | K | DST`.
2. A position is active (default: RB — the most complex position with the most rules, giving new users the richest starting view).
3. Under the active tab, user sees only the rules applicable to that position, still grouped by category.
4. User adjusts enabled/weight for any rule. Settings apply only to that position.
5. Switching tabs shows that position's independent settings. A rule that is disabled for QB may still be enabled for WR.
6. Changes autosave per position.

### 3.2 Default active tab

Default is `RB`. This is the position with the most rules in the mapping (17), giving users the most immediate signal that the panel is useful. Power users who draft QB-first will notice immediately and switch tabs. The last-selected tab is not persisted between sessions — opening the rules panel always shows RB.

### 3.3 Category grouping within a position tab

Yes, keep category grouping. The existing `RuleCategory` component works correctly and provides useful cognitive chunking. Each position tab will render the same category headers (Usage, Situation, Regression, Age/Longevity, Personal) but only populate them with rules from that position's mapping. Empty categories for a given position are not rendered.

Category assignment for rules added to new positions:

- `Target Share Premium` in RB: category remains "Usage".
- `Declining Snap%` in RB/WR/TE: category remains "Usage".
- `Year After the Year After` in QB/TE/K: category remains "Regression".
- `Over the Hill` in K: category remains "Age/Longevity".

### 3.4 Favorites rule for unauthenticated users

The `GET /rules` endpoint already omits the `Favorites` rule for unauthenticated callers (`if rule.name == "Favorites" and current_user is None: continue`). Because the position tab's rule list is derived by filtering the response from `GET /rules` against the position mapping, unauthenticated users will simply not see `Favorites` in any tab. No additional handling needed.

When a user signs in mid-session, `useRules` (a React Query hook) will be re-fetched (or the user refreshes). The Favorites rule appears in the tab list on the next render.

### 3.5 States to handle

**RulesPanel states:**

| State | What the user sees | Next action |
|---|---|---|
| Rules not yet loaded (`rules.length === 0`) | "Loading rules..." placeholder with position tab strip disabled/greyed | Wait; auto-resolves |
| Rules loaded, unauthenticated | Tabs + rules; Favorites absent from all tabs | Use rules as-is; sign in to unlock Favorites |
| Rules loaded, authenticated | Tabs + rules including Favorites | Configure per position |
| Active tab with 2 rules (K tab) | Two rule items under their categories; no empty-state message (2 rules is not "empty") | Adjust as needed |
| Active tab DST (2 rules) | Same | Adjust as needed |

The loading state already exists in RulesPanel (`rules.length === 0` branch). It should also disable or grey the tab strip while loading, because tabs need to be clickable only when the rule list is ready. Otherwise clicking a tab during load will show a correctly-rendered empty tab instead of the loaded one.

**RuleItem states within a position tab:**

The `RuleItem` component no longer renders a position toggle section (that section is removed). The expanded section contains only: description, magnitude input, Low/High suggestion buttons. The Collapsible expand/collapse pattern is unchanged. This simplifies RuleItem — the positions toggle group and all its aria/state is removed.

### 3.6 Empty state

K and DST tabs have 2 rules each. That is not empty — no empty-state message is needed. A "no rules" scenario can't happen under the hardcoded mapping.

### 3.7 Mobile width

The tab strip (6 tabs) at ~375px: use a single-line flexbox with `flex-wrap: nowrap` and `overflow-x: auto`. Each tab label is 2–3 characters (QB, RB, WR, TE, K, DST). At 375px they fit on one row without wrapping even at default font size. Verify during visual verification.

---

## 4. Code-facing impact

### 4.1 New TypeScript types

**`web/src/api/types.ts`** — replace:

```typescript
// OLD Rule interface (positions field was added by prior spec)
export interface Rule {
  name: string;
  conditions: RuleCondition[];
  effect: RuleEffect;
  enabled: boolean;
  weight: number;
  is_builtin: boolean;
  category: string;
  description?: string;
  positions: string[] | null;
}
```

The `Rule` interface is unchanged in shape — the frontend still receives the full rule from `GET /rules`. The `positions` field on `Rule` returned by the API is now informational only (used to know which tab a rule appears in); the frontend does not let users edit it.

Add a new type for per-position state in `App.tsx`:

```typescript
// Per-position rule override map. Outer key: position string ("QB", "RB", etc.)
// Inner array: only rules whose settings differ from built-in defaults.
export type PositionRulesState = Record<string, PositionRuleOverride[]>;

export interface PositionRuleOverride {
  name: string;
  enabled: boolean;
  weight: number;
}
```

Update the `Profile.rules_json` type to match the new storage format:

```typescript
export interface Profile {
  id: string;
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Record<string, Array<{ name: string; enabled: boolean; weight: number }>>;
  linked_league: LinkedLeague | null;
}
```

Update `GenerateRequest.rules` field:

```typescript
export interface GenerateRequest {
  // ... (other fields unchanged)
  rules: Record<string, Array<{ name: string; enabled: boolean; weight: number }>>;
}
```

### 4.2 New constant file

**`web/src/lib/positionRulesMap.ts`** — new file:

```typescript
export const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const;
export type Position = typeof POSITIONS[number];

// Authoritative mapping of which rule names appear under each position tab.
// Order within each array determines display order within a category group.
export const POSITION_RULES_MAP: Record<Position, readonly string[]> = {
  QB: [
    "New Team Penalty", "New Head Coach", "Sophomore Leap", "Bad Offense",
    "Follow the Money", "Injury History", "TD Regression",
    "Opportunity Over-Producer", "Opportunity Under-Producer",
    "Red Zone Usage Premium", "Projection Unavailable",
    "Year After the Year After", "Over the Hill", "Favorites",
  ],
  RB: [
    "RB Committee Penalty", "Target Share Premium", "Declining Snap%",
    "New Team Penalty", "New Head Coach", "Sophomore Leap", "Bad Offense",
    "Follow the Money", "Injury History", "TD Regression",
    "Opportunity Over-Producer", "Opportunity Under-Producer",
    "Red Zone Usage Premium", "Projection Unavailable",
    "Year After the Year After", "Over the Hill", "Favorites",
  ],
  WR: [
    "Target Share Premium", "Declining Snap%", "New Team Penalty",
    "New Head Coach", "Sophomore Leap", "Bad Offense", "Follow the Money",
    "Injury History", "TD Regression", "Opportunity Over-Producer",
    "Opportunity Under-Producer", "Red Zone Usage Premium",
    "Projection Unavailable", "Year After the Year After",
    "Over the Hill", "Favorites",
  ],
  TE: [
    "Target Share Premium", "Declining Snap%", "New Team Penalty",
    "New Head Coach", "Sophomore Leap", "Bad Offense", "Follow the Money",
    "Injury History", "TD Regression", "Opportunity Over-Producer",
    "Opportunity Under-Producer", "Red Zone Usage Premium",
    "Projection Unavailable", "Year After the Year After",
    "Over the Hill", "Favorites",
  ],
  K: [
    "Projection Unavailable", "Year After the Year After",
    "Over the Hill", "Favorites",
  ],
  DST: [
    "Projection Unavailable", "Favorites",
  ],
};
```

### 4.3 New Python schemas

**`backend/app/schemas/rules.py`** — add `RuleOverrideSchema`:

```python
class RuleOverrideSchema(BaseModel):
    name: str
    enabled: bool
    weight: float = 1.0
```

Keep `RuleSchema` unchanged — it is still used by `GET /rules` to return the full rule definition (conditions, effect, etc.) to the frontend.

### 4.4 Updated Python generate schema

**`backend/app/schemas/generate.py`** — change `rules` field:

```python
# OLD
rules: list[RuleSchema] = Field(default_factory=list)

# NEW
from app.schemas.rules import RuleOverrideSchema

rules: dict[str, list[RuleOverrideSchema]] = Field(default_factory=dict)
```

The dict key is a position string; no enum constraint needed — unknown positions are ignored silently during merge.

### 4.5 Updated Python profile schemas

**`backend/app/schemas/profile.py`** — change `rules_json` type throughout:

```python
# OLD
class ProfileOut(BaseModel):
    rules_json: list[dict[str, Any]]

class ProfileCreate(BaseModel):
    rules_json: list[dict[str, Any]]

class ProfileUpdate(BaseModel):
    rules_json: Optional[list[dict[str, Any]]] = None

# NEW (all three)
class ProfileOut(BaseModel):
    rules_json: dict[str, list[dict[str, Any]]]

class ProfileCreate(BaseModel):
    rules_json: dict[str, list[dict[str, Any]]]

class ProfileUpdate(BaseModel):
    rules_json: Optional[dict[str, list[dict[str, Any]]]] = None
```

### 4.6 Updated ORM annotation

**`backend/app/models/profile.py`** — the ORM column annotation:

```python
# OLD
rules_json: Mapped[list] = mapped_column(_JSON_OR_JSONB, nullable=False)

# NEW
rules_json: Mapped[dict] = mapped_column(_JSON_OR_JSONB, nullable=False)
```

No DB migration. The column is JSONB (schemaless). The ORM annotation is a Python-side hint; changing it from `Mapped[list]` to `Mapped[dict]` does not affect the stored bytes.

### 4.7 Updated generate.py backend logic

**`backend/app/api/generate.py`** — replace the rule-merge pre-pass and per-player rule application:

Remove:
- `_merge_positions` function
- `LOCKED_POSITIONS` set
- `user_rule_map` dict comprehension
- `custom_rules` list
- `merged` dict
- The single `rules = list(merged.values())` line

Add:

```python
def _build_rules_for_position(position: str, req: "GenerateRequest") -> list[Rule]:
    """Return the full BUILTIN_RULES list with per-position overrides applied.

    For each built-in rule, apply the client's enabled/weight for this position
    if an override exists. Otherwise use the built-in default. The built-in
    `positions` field on each Rule is preserved unchanged — the engine's
    position gate still applies.
    """
    override_map: dict[str, "RuleOverrideSchema"] = {
        o.name: o for o in req.rules.get(position, [])
    }
    result: list[Rule] = []
    for builtin in BUILTIN_RULES:
        o = override_map.get(builtin.name)
        if o is not None:
            result.append(dataclasses.replace(builtin, enabled=o.enabled, weight=o.weight))
        else:
            result.append(builtin)
    return result
```

Then inside the player loop, replace `rule_result = apply_rules(blended, ctx, rules)` with:

```python
rules_for_player = _build_rules_for_position(player.position, req)
rule_result = apply_rules(blended, ctx, rules_for_player)
```

Note: `_build_rules_for_position` is called per player. With ~500 players and ~20 built-in rules this is ~10,000 dict lookups — negligible. The function could be memoized by position (only 6 distinct positions), but this is a premature optimization; do not add it unless benchmarks show a regression.

Also update the import of `_merge_positions` is removed from the file. The `_schema_to_rule` helper (used for custom rules) is also removed.

**`injured_two_years_ago` extension for QB/TE/K:** Change the position guard in `_run_generate`:

```python
# OLD
if player.position in ("RB", "WR"):
    two_seasons_ago = ...
    injured_two_years_ago = ...

# NEW
if player.position in ("QB", "RB", "WR", "TE", "K"):
    two_seasons_ago = ...
    injured_two_years_ago = ...
```

This enables the `Year After the Year After` rule to fire correctly for QB/TE/K players who appear under those tabs.

### 4.8 Updated builtin_rules.py

**`backend/app/engine/builtin_rules.py`** — change `positions` values per the table in section 2.4:

```python
# Target Share Premium: add "RB"
Rule(
    name="Target Share Premium",
    ...
    positions=["RB", "WR", "TE"],
)

# Declining Snap%: was None (all), now RB/WR/TE only
Rule(
    name="Declining Snap%",
    ...
    positions=["RB", "WR", "TE"],
)

# Year After the Year After: was ["RB", "WR"], now QB/RB/WR/TE/K
Rule(
    name="Year After the Year After",
    ...
    positions=["QB", "RB", "WR", "TE", "K"],
)

# Over the Hill: was ["QB","RB","WR","TE"], now also K
# (see open question in section 7 for K age threshold)
Rule(
    name="Over the Hill",
    ...
    positions=["QB", "RB", "WR", "TE", "K"],
)
```

Also update the description for `Over the Hill` to mention K.

### 4.9 Updated generate.py OVER_THE_HILL_AGE

**`backend/app/api/generate.py`** — in the `OVER_THE_HILL_AGE` import from `builtin_rules`, the dict currently lives at the top of that file. The K entry must be added. See open question 7.1 for the threshold value. Once resolved, add:

```python
OVER_THE_HILL_AGE = {"RB": 28, "WR": 30, "TE": 31, "QB": 36, "K": <threshold>}
```

And the position guard using it in `_run_generate`:

```python
# OLD
if player.age is not None and player.position in OVER_THE_HILL_AGE:
    is_over_the_hill = player.age >= OVER_THE_HILL_AGE[player.position]

# Unchanged — adding K to OVER_THE_HILL_AGE dict is sufficient
```

### 4.10 Updated App.tsx state shape

**`web/src/App.tsx`** — the `rules` state changes from `Rule[]` to a two-part design:

```typescript
// Canonical rule definitions from GET /rules (used to seed defaults and display)
const [canonicalRules, setCanonicalRules] = useState<Rule[]>([]);

// Per-position override state — this is what gets saved and sent to generate
const [positionRules, setPositionRules] = useState<PositionRulesState>({});
const [seeded, setSeeded] = useState(false);
```

- `canonicalRules` is the full rule list from the API (conditions, effect, description, category). Used by RulesPanel to render rule names, descriptions, and impact calculations. Never mutated directly by the user.
- `positionRules` is the sparse override dict. Keyed by position, each value is the list of rules the user has changed from defaults. Sent as the `rules` field in GenerateRequest and stored as `rules_json`.

**Seeding:** On first load, `canonicalRules` is set from `fetchedRules`. `positionRules` starts as `{}` (empty) — all rules at their defaults.

**Profile hydration:** When a profile is loaded, its `rules_json` (now a dict) is set directly as `positionRules`. No merging needed — the dict format is already the override format.

```typescript
// In the activeProfileId effect:
setPositionRules(active.rules_json as unknown as PositionRulesState);
```

**Autosave payload:**

```typescript
const autosavePayload = useMemo(() => ({
  settings_json: settings as unknown as Record<string, unknown>,
  rules_json: positionRules as unknown as Record<string, unknown>,
}), [settings, positionRules]);
```

**Undo history:** The `Snapshot` type's `rules_json` field changes from `Array<Record<string, unknown>>` to `Record<string, unknown>`. The undo logic restores `positionRules` directly from the snapshot's `rules_json` field (no re-merge needed).

**buildRequest:**

```typescript
const buildRequest = (): GenerateRequest => {
  ...
  return {
    ...
    rules: positionRules,  // already the correct shape
    ...
  };
};
```

**canGenerate:** The condition `rules.length > 0` must change. `canonicalRules.length > 0` is the correct check — the canonical list being loaded means the backend is reachable and rules are ready.

### 4.11 Updated RulesPanel

**`web/src/components/RulesPanel.tsx`** — full rewrite:

```typescript
interface RulesPanelProps {
  canonicalRules: Rule[];
  positionRules: PositionRulesState;
  onChange: (next: PositionRulesState) => void;
}
```

Internal state: `const [activePosition, setActivePosition] = useState<Position>("RB");`

Rendering:
1. Tab strip at the top: 6 buttons, one per position in order `QB RB WR TE K DST`. Active tab uses `bg-primary text-primary-foreground`; inactive uses `bg-muted text-muted-foreground hover:bg-muted/80`. No shadcn Tabs component is needed — plain buttons with `role="tab"`, `aria-selected`, and a containing `role="tablist"`.
2. Below the tab strip: the rule list for the active position, derived by filtering `canonicalRules` to the names in `POSITION_RULES_MAP[activePosition]`, then grouping by category as before.
3. Rules absent from `canonicalRules` (e.g., Favorites for unauthenticated users) are silently skipped — they won't appear in the filtered list.

The `updateRule` callback for a rule change:

```typescript
function updateRule(positionName: string, updated: PositionRuleOverride) {
  const current = positionRules[positionName] ?? [];
  const exists = current.findIndex(r => r.name === updated.name);
  let next: PositionRuleOverride[];
  if (exists >= 0) {
    next = current.map((r, i) => i === exists ? updated : r);
  } else {
    next = [...current, updated];
  }
  onChange({ ...positionRules, [positionName]: next });
}
```

Rules at their default state (enabled=true, weight=1.0) can remain in the override list — the backend handles defaults correctly whether or not the override entry exists. Pruning defaults from the array is an optimization that is NOT in scope for this implementation (adds code complexity with no user-visible benefit).

### 4.12 Updated RuleItem

**`web/src/components/RuleItem.tsx`** — remove the positions toggle section entirely.

The component now receives a `PositionRuleOverride`-shaped object (name, enabled, weight) rather than a full `Rule`. But it still needs the full `Rule` for description and impact calculations.

Proposed prop shape:

```typescript
interface RuleItemProps {
  rule: Rule;           // full canonical rule (for description, effect, category)
  override: PositionRuleOverride;  // current enabled/weight for this position
  onChange: (next: PositionRuleOverride) => void;
}
```

All existing impact calculation logic (`getImpactInfo`, `formatMagnitude`, the weight input, Low/High buttons) remains unchanged — it reads from `rule.effect` and the current weight from `override.weight`.

The switch reads `override.enabled` and calls `onChange({ ...override, enabled: v })`.

Remove: the entire positions toggle section (the `LOCKED_POSITION_RULES` set, the `role="group"` div, all position buttons, the `All` button, and their aria attributes).

Remove: the `ALL_POSITIONS` constant.

### 4.13 Updated RuleCategory

**`web/src/components/RuleCategory.tsx`** — prop change only:

```typescript
// OLD
interface RuleCategoryProps {
  name: string;
  rules: Rule[];
  onChangeRule: (next: Rule) => void;
}

// NEW
interface RuleCategoryProps {
  name: string;
  rules: Rule[];
  overrides: Record<string, PositionRuleOverride>;  // keyed by rule name
  onChangeRule: (next: PositionRuleOverride) => void;
}
```

The component passes the matching override (or a default) down to each `RuleItem`.

### 4.14 Complete file change list

| File | Change type | Summary |
|---|---|---|
| `web/src/lib/positionRulesMap.ts` | New | `POSITIONS`, `Position`, `POSITION_RULES_MAP` constants |
| `web/src/api/types.ts` | Edit | `PositionRulesState`, `PositionRuleOverride` types; update `Profile.rules_json` and `GenerateRequest.rules` |
| `web/src/App.tsx` | Edit | Split `rules: Rule[]` into `canonicalRules: Rule[]` + `positionRules: PositionRulesState`; update hydration, autosave, buildRequest, canGenerate |
| `web/src/components/RulesPanel.tsx` | Rewrite | Position tab strip; filter canonical rules by position map; updated props |
| `web/src/components/RuleCategory.tsx` | Edit | Add `overrides` prop; pass override down to RuleItem |
| `web/src/components/RuleItem.tsx` | Edit | Replace `rule: Rule` + single onChange with `rule: Rule` + `override: PositionRuleOverride` + onChange; remove positions section entirely |
| `web/src/tests/components/RuleItem.test.tsx` | Rewrite | Tests now assert on override-shaped props; remove all position-toggle tests; add tests for override-mode enabled/weight |
| `web/src/tests/App.test.tsx` | Edit | Update rule reference: `screen.getByText("Target Share Premium")` still works since RB tab shows that rule by default |
| `web/src/tests/integration/app-authenticated.test.tsx` | Edit | `PROFILE_ONE.rules_json` changes from array to dict; update Undo test's type assertion |
| `backend/app/schemas/rules.py` | Edit | Add `RuleOverrideSchema` |
| `backend/app/schemas/generate.py` | Edit | Change `rules` field from `list[RuleSchema]` to `dict[str, list[RuleOverrideSchema]]` |
| `backend/app/schemas/profile.py` | Edit | Change `rules_json` from `list[dict]` to `dict[str, list[dict]]` in all three schema classes |
| `backend/app/models/profile.py` | Edit | Change `Mapped[list]` to `Mapped[dict]` on `rules_json` |
| `backend/app/api/generate.py` | Edit | Add `_build_rules_for_position`; remove `_merge_positions`, `LOCKED_POSITIONS`, `_schema_to_rule`, old merge block; extend `injured_two_years_ago` to QB/TE/K |
| `backend/app/engine/builtin_rules.py` | Edit | Update positions on 4 rules; update `OVER_THE_HILL_AGE` to add K |
| `backend/tests/test_per_position_rules_merge.py` | Rewrite | Old tests tested `_merge_positions` and `LOCKED_POSITIONS` which are removed; replace with tests for `_build_rules_for_position` covering: (a) override applied, (b) default preserved when absent, (c) unknown position returns builtin defaults, (d) unknown rule name in override is ignored |

Files that do NOT change:
- `web/src/hooks/useAutoSave.ts` — watches payload reference; shape change is transparent
- `web/src/api/hooks.ts` — `useRules` fetches canonical rules; no change
- `backend/app/api/rules.py` — `GET /rules` still returns full `RuleSchema` list; no change
- `backend/app/engine/rules.py` — `apply_rules` is unchanged
- `backend/app/api/profiles_api.py` — PATCH/POST handlers accept `rules_json` as opaque; only the schema types change

---

## 5. Migration strategy — old format to new

### 5.1 The problem

Existing stored profiles have `rules_json` as an array:
```json
[{ "name": "Target Share Premium", "enabled": false, "weight": 1.0, "positions": ["WR","TE"] }]
```

The new code expects:
```json
{ "RB": [...], "WR": [...] }
```

### 5.2 Chosen approach: read-time migration in the frontend, with backend tolerance

**No Alembic DB migration.** The column is JSONB — it stores whatever JSON the application writes. Changing the stored format does not require a schema change.

**Backend tolerance:** The backend's `ProfileOut.rules_json` is typed as `dict[str, list[dict]]`. If an old profile row is read, its `list` value fails Pydantic validation. Therefore the backend API layer needs a compatibility shim.

Add a migration helper in `backend/app/api/profiles_api.py` (or in `ProfileOut`'s `model_validator`):

```python
@model_validator(mode="before")
@classmethod
def migrate_rules_json(cls, values):
    rj = values.get("rules_json") if isinstance(values, dict) else getattr(values, "rules_json", None)
    if isinstance(rj, list):
        # Old format: flat list. Cannot reliably convert to per-position
        # without knowing which positions each rule applied to.
        # Strategy: discard the old overrides — return empty dict.
        # Users will see all rules at their defaults on next open.
        if isinstance(values, dict):
            values["rules_json"] = {}
        else:
            values.rules_json = {}
    return values
```

**Why discard instead of convert?** The old format stored a flat override with a `positions` list (e.g., `positions: ["WR","TE"]`). Converting that to per-position format would require placing the override in every position that contains that rule AND that was in the `positions` list. The result would be semantically incorrect for the new model (same weight for all positions was the old behavior; users may now want different weights). Starting from defaults is honest: users see the rule enabled/at default weight, can immediately reconfigure per position. A conversion that silently re-applies old weights would look like a bug if the weights diverged from expectations.

**Frontend read-time migration:** After the backend shim, the frontend receives `rules_json` as a dict (possibly empty). If it's empty, `positionRules` initializes to `{}`. No frontend migration code needed beyond the type change.

**First-write migration:** On the user's next rule change, the autosave PATCH writes the new dict format. After that first write, the profile row is in the new format.

**For new profiles:** `ProfileCreate.rules_json` defaults to `{}` in the frontend (`positionRules` starts as `{}`).

### 5.3 No server-side mass migration

Running an Alembic migration to convert every existing profile's `rules_json` from list to dict would be destructive (same lossy conversion problem) and requires a deploy window. The read-time shim is safer and recoverable if something goes wrong.

---

## 6. Out of scope

- **Custom user-created rules.** No UI exists for this. The new model removes the `custom_rules` code path from `generate.py`. If this feature is added later, the dict format accommodates it by adding a `"CUSTOM"` pseudo-position key or by a separate mechanism.
- **Per-position weight sliders in a single view.** "Show me New Team Penalty's weight for all positions at once" — this would require a different layout (e.g., a rule-first view with position columns). Not in this design.
- **Persisting the active position tab across sessions.** The last-selected tab is session-only state. Adding persistence (localStorage or profile settings) is a separate concern.
- **Importing / exporting rule configurations.** Profile export is not a current product feature.
- **Reordering rules within a position tab.** Display order is fixed by `POSITION_RULES_MAP`.
- **Analytics on per-position rule impact.** The existing `rule_applications` array on `TieredPlayer` already records which rules fired. No changes to that output.
- **The `PositionFilter` in `TiersPanel.tsx`.** This changes how rules are evaluated before scoring; the tiers display filter is independent.
- **K and DST offensive custom rules.** The position mapping for K/DST intentionally contains only the 2-4 most applicable rules. No new built-in rules are being created.
- **The `370 Touches`, `Contract Year Flag`, `Handcuff RB`, and `Availability Risk` rules.** These remain in the backend but are not surfaced in the new UI. No configuration UI is provided for them.

---

## 7. Open questions

All questions must be resolved before the Engineer begins backend changes. Frontend work on the UX shell (tab strip, RulesPanel rewrite, RuleItem simplification) can proceed in parallel since it does not depend on the K age threshold.

### 7.1 Over the Hill age threshold for K (blocking for backend)

The `OVER_THE_HILL_AGE` dict currently has entries for RB/WR/TE/QB. The product owner mapping places "Over the Hill" in the K tab. What age is "over the hill" for a kicker?

**Options:**
- `40` — consistent with the observation that elite kickers (Tucker, Butker, McPherson) play into their late 30s but decline around 40.
- `38` — more conservative; aligns with where kick accuracy typically starts declining in available data.
- Skip adding K to `OVER_THE_HILL_AGE` and instead update the product owner mapping to remove "Over the Hill" from the K tab. This avoids the question entirely.

**Recommendation:** Consult `autotiers-researcher` for source-attributed evidence on kicker age curves before committing. If research is not available quickly, remove "Over the Hill" from the K tab until it is answered. The mapping in `POSITION_RULES_MAP` is a frontend constant — it can be updated without a backend deploy.

### 7.2 Target Share Premium for RB — condition validity (informational, not blocking)

The rule fires when `target_share >= 0.25`. For RBs, target share is a meaningful PPR metric — but the product owner's decision to add this to the RB tab may surprise users who expect it to be WR/TE-centric. No action required on this question before implementation; the product owner has decided. Document in the rule's description that it also applies to RBs in PPR formats.

### 7.3 Year After the Year After for K — condition data availability (blocking for backend)

The condition reads `injured_two_years_ago == True`, which requires `player.stats` to include a stat row for `season = current_year - 2` with `games_played < 12`. Kicker stat ingestion must include `games_played` for this to fire. Confirm that the data pipeline populates kicker stats at all before extending the `injured_two_years_ago` computation to `K`. If kicker stats are not ingested, the condition will always return `None → False` and the rule will never fire — safe but misleading in the UI. If kicker stats are absent, remove K from the "Year After the Year After" entry in `POSITION_RULES_MAP`.

### 7.4 Declining Snap% for K/DST (informational, not blocking)

The product owner mapping does not include "Declining Snap%" for K or DST, which is correct — snap% is not tracked for special teams. The `BUILTIN_RULES.positions` change (from `None` to `["RB","WR","TE"]`) enforces this at the scoring level. No user action needed.

---

## Appendix A — State machine for positionRules in App.tsx

```
Initial load
  canonicalRules = []
  positionRules = {}

GET /rules resolves
  canonicalRules = fetchedRules
  positionRules unchanged = {}
  (all rules display at defaults)

User authenticates, active profile loads
  canonicalRules unchanged
  positionRules = profile.rules_json (dict from server)
  (possibly {} if new profile or migrated profile)

User changes a rule (e.g., toggles enabled on "RB Committee Penalty" under RB tab)
  positionRules = {
    ...positionRules,
    RB: [...(positionRules.RB ?? []).filter excluding existing entry, new entry]
  }
  autosave debounces → PATCH /profiles/{id} with new rules_json

User switches profile
  positionRules = new profile's rules_json
  canonicalRules unchanged

User clicks Undo
  positionRules = history[activeProfileId][tip-1].rules_json
  PATCH fires immediately with prior snapshot
```

---

## Appendix B — Accessibility specification for position tab strip

```
<div role="tablist" aria-label="Position">
  <button
    role="tab"
    aria-selected={activePosition === "QB"}
    aria-controls="rules-tabpanel"
    id="tab-QB"
    onClick={() => setActivePosition("QB")}
  >QB</button>
  ... repeat for RB, WR, TE, K, DST ...
</div>

<div
  role="tabpanel"
  id="rules-tabpanel"
  aria-labelledby={`tab-${activePosition}`}
>
  {/* rule list */}
</div>
```

- Keyboard: `Tab` reaches the tablist. Arrow keys (`ArrowLeft`/`ArrowRight`) move between tabs. `Enter`/`Space` activates the focused tab.
- Focus: the active tab retains focus after keyboard activation. The tabpanel does not receive focus automatically on tab switch (the list is not a roving focus context — users tab into the rule items directly).
- ARIA: `aria-selected="true"` on the active tab. `aria-selected="false"` on inactive tabs. No `aria-disabled` since all tabs are always enabled.
- The `aria-controls` / `id` pairing links the tab to its panel for screen readers.
