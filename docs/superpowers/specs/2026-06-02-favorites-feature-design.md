# Favorites Feature — Design

## Goal

Allow logged-in users to mark up to 20 individual players and 4 teams as favorites on their account page, causing a personal +5% score boost (MULTIPLIER 1.05, user-adjustable) whenever a favorited player or a player on a favorited team appears in tier generation.

---

## Approach

Favorites are stored as two user-scoped lists (`favorite_player_ids`, `favorite_teams`) in a new `user_favorites` table, keyed to the `users` table. At generate time, the backend injects a synthetic `is_favorite` boolean into each `PlayerContext`, which a new builtin rule named `"Favorites"` evaluates as a standard MULTIPLIER. The rule is omitted from the `GET /rules` list for anonymous users and never fires when `is_favorite` is `None` (the default for unauthenticated sessions). The frontend surfaces favorites management inside the existing account page (the `LinkedAccountsDialog` or a new sibling section), and exposes the Favorites rule in `RulesPanel` only when the user is logged in.

---

## User-facing impact

### Where it lives

Favorites management lives on a new **"Favorites" tab** inside the existing **`LinkedAccountsDialog`**. This modal is already the user's account hub (it hosts the league-linking tabs). Adding a tab here keeps account-scoped settings colocated and avoids a separate page or a second modal.

The tab label is **"Favorites"**. It sits after the existing "Linked League" tab(s) and before any future tabs.

### The Favorites tab — layout

The tab is split into two sections, visually separated by a divider:

**Favorite Players** (top section)

- Section heading: `"Favorite Players"` with count badge: `"3 / 20"`
- A search-by-name input (placeholder: `"Search players…"`). Client-side filter against the current generate result's player list, OR a future `/players` endpoint. For v1, the generate result is used — players must have been generated at least once for the search to populate.
- Each matched player renders as a one-line row: jersey number / position badge, name, team abbreviation, and an **Add** button (or a **Remove** button if already favorited).
- Players at cap (20 added) render Add buttons as disabled with tooltip: `"Limit reached (20 players). Remove one to add another."`
- Already-favorited players appear at the top of the search results with a filled star icon and a Remove button.

**Favorite Teams** (bottom section)

- Section heading: `"Favorite Teams"` with count badge: `"1 / 4"`
- A 32-team NFL grid or dropdown. Display team abbreviation + city. Tapping a team toggles it. Selected teams show a filled star.
- At cap (4 teams), unselected teams are greyed out with tooltip: `"Limit reached (4 teams). Remove one to add another."`

### UI states

| State | What the user sees |
|---|---|
| **Empty (no favorites yet)** | Both sections show the empty-state copy below their headings. Players section: `"No favorite players yet. Search above to add one."` Teams section: `"No favorite teams yet. Select up to 4 teams."` |
| **Partial (some added)** | Normal interactive state. Count badge updates live. |
| **At cap — players** | Add buttons disabled. Tooltip explains the limit. Badge shows `"20 / 20"` in amber. |
| **At cap — teams** | Unselected team tiles greyed + non-interactive. Badge shows `"4 / 4"` in amber. |
| **Loading (initial fetch)** | Spinner inside the section while favorites are being fetched. |
| **Save error** | Inline error below the relevant section: `"Couldn't save. Try again."` The optimistic UI reverts (the item is removed or re-added to match server state). |

### Anonymous users

The Favorites tab is **not rendered** for anonymous users (when `user` from `useAuth()` is `null`). The tab simply doesn't appear in the `LinkedAccountsDialog` tab list. No locked-state placeholder is shown — anonymous users aren't expected to reach the account dialog's league-linking tabs either.

In `RulesPanel`, the Favorites rule is **omitted from the rule list** when the user is not logged in. It does not appear as a disabled row — it is simply absent. The rule is a personal preference signal, not a universal heuristic, and showing it to anonymous users creates confusion about what it does.

If an anonymous user generates tiers, the backend never sets `is_favorite = True` on any player (the field defaults to `None`), so the rule never fires even if the frontend somehow included it in the rule payload.

### The Favorites rule in RulesPanel

When logged in, a new category **"Personal"** appears at the top of `RulesPanel` (above "Age/Longevity") containing a single rule: **"Favorites"**.

- Rule name displayed as-is: `"Favorites"`
- Toggle switch: enabled by default when any favorites exist, disabled by default when the user has no favorites.
- Description (shown on expand): `"Boosts players you've marked as favorites — either directly by player or by team. +5% at default weight."`
- Weight input follows the existing `RuleItem` pattern: the user edits the magnitude directly (default shows `5`, unit `%`). Low preset: `+2.5%`, High preset: `+10%`.
- The category `"Personal"` is only rendered when the user is logged in. If the user logs out mid-session, the category and its rule are dropped from the visible rules list on the next rule fetch.

### Copy summary

| Location | Copy |
|---|---|
| Tab label | `Favorites` |
| Player section heading | `Favorite Players` |
| Team section heading | `Favorite Teams` |
| Empty state — players | `No favorite players yet. Search above to add one.` |
| Empty state — teams | `No favorite teams yet. Select up to 4 teams.` |
| At-cap tooltip — players | `Limit reached (20 players). Remove one to add another.` |
| At-cap tooltip — teams | `Limit reached (4 teams). Remove one to add another.` |
| Save error | `Couldn't save. Try again.` |
| Rule description | `Boosts players you've marked as favorites — either directly by player or by team. +5% at default weight.` |

---

## Code-facing impact

### Data model

**New table: `user_favorites`**

```sql
CREATE TABLE user_favorites (
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    favorite_player_ids  JSONB NOT NULL DEFAULT '[]',
    favorite_teams       JSONB NOT NULL DEFAULT '[]',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id)
);
```

- One row per user; `user_id` is both PK and FK.
- `favorite_player_ids`: JSON array of `player.id` strings (e.g. `["4046", "7564"]`). Max 20 entries enforced in backend logic, not a DB constraint.
- `favorite_teams`: JSON array of team abbreviation strings (e.g. `["KC", "SF"]`). Max 4 entries enforced in backend logic.
- `updated_at`: kept for cache-invalidation and debugging. Not exposed to frontend.
- No row is created on signup. Endpoints use UPSERT (`INSERT … ON CONFLICT DO UPDATE`) so the first write creates the row.
- Uses `JSONB().with_variant(JSON(), "sqlite")` pattern (same as `Profile` model) to support the SQLite test engine.

**New SQLAlchemy model: `backend/app/models/user_favorites.py`**

```python
class UserFavorites(Base):
    __tablename__ = "user_favorites"
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    favorite_player_ids: Mapped[list] = mapped_column(_JSON_OR_JSONB, nullable=False, default=list)
    favorite_teams: Mapped[list]      = mapped_column(_JSON_OR_JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), …)
```

Add to `backend/app/models/__init__.py` exports and to `__all__`.

**Alembic migration: `008_user_favorites.py`**

- `revision = "008"`, `down_revision = "007"`
- `upgrade()`: create `user_favorites` table.
- `downgrade()`: drop `user_favorites` table.
- Filename convention matches the repo: descriptive name, short numeric revision string.

### API endpoints

All endpoints are auth-gated via `require_user`. Pattern mirrors `profiles_api.py`.

**`GET /favorites`**
- Returns the current user's favorites (or defaults if no row exists).
- Response:
  ```json
  { "favorite_player_ids": ["4046"], "favorite_teams": ["KC"] }
  ```
- If no row exists for the user, returns `{ "favorite_player_ids": [], "favorite_teams": [] }` (do not 404).

**`PUT /favorites`**
- Full replacement. Body:
  ```json
  { "favorite_player_ids": ["4046", "7564"], "favorite_teams": ["KC"] }
  ```
- Backend validates:
  - `favorite_player_ids` is a list of strings, max 20.
  - `favorite_teams` is a list of strings matching known NFL abbreviations (32 teams), max 4.
  - Neither list contains blank/whitespace-only strings (Class 2 guard).
  - Duplicate entries are deduplicated before persisting.
- Uses UPSERT: `INSERT INTO user_favorites … ON CONFLICT (user_id) DO UPDATE SET …`.
- Returns the persisted record (same shape as GET response).
- Error responses:
  - `422` with FastAPI validation detail when body shape is wrong.
  - `409 "Too many favorite players (max 20)."` when `len(favorite_player_ids) > 20`.
  - `409 "Too many favorite teams (max 4)."` when `len(favorite_teams) > 4`.
  - `422 "Unknown team: XYZ"` when a team abbreviation is not in the canonical 32-team set.

**Pydantic schemas: `backend/app/schemas/favorites.py`**

```python
class FavoritesUpdate(BaseModel):
    favorite_player_ids: list[str] = []
    favorite_teams: list[str] = []

class FavoritesOut(BaseModel):
    favorite_player_ids: list[str]
    favorite_teams: list[str]
    model_config = {"from_attributes": True}
```

**Router registration**: `backend/app/api/favorites_api.py`, prefix `/favorites`, included in `backend/app/main.py` under `/api`.

### Rule engine integration

**New `PlayerContext` field:**

```python
is_favorite: Optional[bool] = None
```

Add to `backend/app/engine/rules.py` `PlayerContext` dataclass. Defaults to `None`. The existing `_evaluate()` uses `getattr(ctx, field, None)` and returns `False` when `val is None`, so a `None` field never triggers the condition — the rule silently no-ops for unauthenticated requests.

**New builtin rule: `backend/app/engine/builtin_rules.py`**

```python
Rule(
    name="Favorites",
    conditions=[RuleCondition(field="is_favorite", operator="==", value=True)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.05),
    description="Boosts players you've marked as favorites — either directly by player or by team. +5% at default weight.",
)
```

Append at the end of `BUILTIN_RULES`.

**Categorization: `backend/app/api/rules.py`**

Add `"Favorites": "Personal"` to `_CATEGORIES`. The `GET /rules` endpoint must **only return** the Favorites rule when the requesting user is logged in. This requires the rules endpoint to become auth-aware:

- Change `GET /rules` to accept an optional `current_user` via `get_current_user` (not `require_user` — anonymous users still need the other rules).
- Filter out the `"Favorites"` rule from the response when `current_user is None`.

**Generate endpoint integration: `backend/app/api/generate.py`**

The `/generate` endpoint must now accept the user's favorites and inject `is_favorite` into each `PlayerContext`. Two options:

1. **Preferred:** Add `favorite_player_ids: list[str] = []` and `favorite_teams: list[str] = []` to `GenerateRequest`. The frontend passes them from the locally-cached favorites state. This keeps the generate endpoint stateless and avoids a DB lookup per-generation.
2. Alternative: Backend looks up favorites from DB using `get_current_user`. Adds a DB round-trip but doesn't widen the generate request contract.

**Option 1 is recommended** (matches the existing pattern: `keepers` are passed in the generate request body rather than stored per-profile). The frontend already has a `useAutoSave` pattern — it can hold favorites in context and include them in the generate payload.

The `is_favorite` logic in `_run_generate`:

```python
favorite_pids_set = set(req.favorite_player_ids)
favorite_teams_set = set(req.favorite_teams)

# … inside the per-player loop:
is_favorite = (
    player.id in favorite_pids_set
    or (player.team is not None and player.team in favorite_teams_set)
)
ctx = PlayerContext(
    …
    is_favorite=is_favorite if (favorite_pids_set or favorite_teams_set) else None,
)
```

Setting `is_favorite = None` (rather than `False`) when the user has no favorites ensures the rule condition evaluates to `False` via the existing `_evaluate` guard, avoiding any performance cost.

### Frontend changes

**New component: `web/src/components/FavoritesPanel.tsx`**

Renders the Favorites tab content inside `LinkedAccountsDialog`. Props:

```tsx
interface FavoritesPanelProps {
  favoritePlayers: string[];          // player IDs
  favoriteTeams: string[];            // team abbreviations
  players: TieredPlayerOut[];         // from last generate result — for search
  onSave: (fav: FavoritesUpdate) => Promise<void>;
}
```

Internal state: search query string, optimistic list of favorites (updated on Add/Remove before the server confirms). On save error, revert optimistic state and show inline error.

**Modified: `web/src/components/LinkedAccountsDialog.tsx`**

Add a "Favorites" tab (after existing league-linking tabs). Only render this tab when `user !== null`. Pass favorites state and the `onSave` handler down from the dialog.

**Modified: `web/src/components/RulesPanel.tsx`**

The rules list already filters by `r.effect.type !== "flag"` and groups by `r.category`. No structural change needed — `RulesPanel` just needs to receive a rules list that omits `"Favorites"` when the user is anonymous. The parent (either `App.tsx` or the profile context) handles fetching rules from `GET /rules` (which already omits Favorites for anon users). No `RulesPanel` code change required.

**Modified: `web/src/api/types.ts`**

Add `FavoritesOut` and `FavoritesUpdate` types. Add `favorite_player_ids` and `favorite_teams` optional fields to `GenerateRequest`.

**New: `web/src/api/favorites.ts`**

API client for `GET /favorites` and `PUT /favorites`. Mirrors `web/src/api/profiles.ts` pattern.

**Modified: `web/src/contexts/AuthContext.tsx`** (optional — may instead use a local hook)

Either add favorites state to `AuthContext` (if it needs to be globally available, e.g., for the generate hook) or create a `useFavorites()` hook that fetches on mount and exposes the current favorites + a save function. The generate hook needs access to the current favorites to include them in the POST body.

**Autosave behavior**: Favorites are saved immediately on Add/Remove (each toggle triggers a `PUT /favorites`). This matches the product's "no save button" convention. The save is optimistic: the UI updates immediately; on error, revert and show the inline error string.

---

## Math / statistical claims

**Question posed to autotiers-mathematician:**

> User feature adds a Favorites rule (MULTIPLIER 1.05 = +5%) per user. Cap is 20 favorite players + 4 favorite teams (a team boost applies to all ~15-25 players on the team). Worst case: a user favorites 4 teams + 20 players = up to ~100 players boosted. Question: with ~600 active skill-position players in the pool, does +5% on ~17% of players materially distort the adjusted_score distribution enough to compromise tier integrity? Specifically, would jenkspy natural-breaks find new spurious breaks at the favorited/unfavorited boundary? Quantify with sample numbers if you can. If the cap should be lower or higher to avoid distortion, propose a value and your reasoning.

**Mathematician's response (run 2026-06-02, simulation on synthetic pool of 574 players matching empirical projection distributions):**

```
Assumptions:
- 600 active skill-position players in pool (simulation: 574 — QB 50, RB 160, WR 200, TE 100, K 32, DST 32)
- Score distributions: QB N(280,60), RB N(160,80), WR N(140,70), TE N(90,50), clipped at 5
- Favorites rule: MULTIPLIER 1.05 (+5%), cap 20 players + 4 teams
- Worst case per simulation: ~100 boosted skill-position players (~17% of 510 skill-pos players)
- Tier engine clusters on VBD score per position (not raw scores); max tiers QB=3, RB=5, WR=5, TE=3
- Replacement rank multipliers: QB×1.0, RB×2.5, WR×2.5, TE×1.25 at league_size=12

Key results:

Per-position VBD tier break shifts at worst case (50 WRs / 40 RBs boosted):
  QB  (3 tiers): max break shift 10-11 pts, 10-18% of players changing tier
  RB  (5 tiers): max break shift 10-11 pts,  2-12% of players changing tier
  WR  (5 tiers): max break shift  5-12 pts,  2-10% of players changing tier
  TE  (3 tiers): max break shift  4-15 pts,  2-8% of players changing tier

A 10pt shift on WR VBD tiers of typical width 46-55 pts = 18-22% of tier width — meaningful
but not catastrophic. At realistic favorites counts (30 WRs, 26 RBs), shifts are 5-11 pts.

Spurious break finding:
  No new tier COUNTS emerge (5 WR tiers remain 5). Breaks shift, they do not multiply.
  The +5% multiplier is identical in magnitude to the existing "Follow the Money" rule and
  is smaller than "Target Share Premium" (+7%), "Sophomore Leap" (+8%), and
  "Year After the Year After" (+10%). Those rules can flip 10-20% of a position's tier
  assignments simultaneously across ALL users; the Favorites rule affects only the
  individual user's personal view. The structural concern is therefore no greater than
  the concern already accepted for existing rules.

Adjacent-score gap (skill positions, raw scores): median 0.38 pts, mean 0.91 pts.
At score 160 (median WR), +5% = +8 pts — much larger than the adjacent-player gap,
so a favorite will reliably leapfrog neighbors. This is INTENDED: the user is expressing
preference, not making a precision claim.

Cap adequacy:
  The 20-player + 4-team cap produces at most ~100 boosted players at +5% multiplier.
  Simulation confirms no spurious breaks emerge across all tested cap sizes (20 to 200).
  Cap is SAFE at 1.05.

Recommendation:
  Cap of 20 players + 4 teams is adequate for the 1.05 multiplier. No reduction needed.
  If the multiplier were raised to 1.10+, consider reducing team cap to 2-3 to keep
  per-position shift below 10 pts. Document clearly that this is a personalization layer
  (user preference), not a statistical claim — the boost should be understood as
  "I want to see these players ranked higher FOR ME," not "these players are objectively
  5% better."
```

**Designer's verdict:** The cap is sound. The boost magnitude matches "Follow the Money" (1.05), which is already shipped. No math changes required. The design correctly frames Favorites as a personalization layer, which the rule description copy reflects.

---

## FF heuristic basis

N/A — this is a UX personalization feature, not a heuristic-driven scoring signal. The Favorites rule does not model any fantasy football domain claim (e.g., "team loyalty correlates with player upside"). It expresses a user's explicit preference. No Researcher consultation required.

---

## Out of scope

The following are explicitly NOT part of this design and should not be built by the implementing engineer:

- **Recommendation engine**: No automated "players you might want to favorite" suggestions based on historical preferences, ADP rank, or projected score.
- **Social sharing of favorites**: No public favorite lists, no "share my favorites" feature, no league-wide favorite counts.
- **Multi-user / league-level favorites**: A league commissioner cannot set shared favorites that apply to all league members.
- **Favorites-as-watchlist**: No separate "watchlist" concept with notes, alerts, or injury tracking.
- **Favorites persistence across profiles**: Favorites are stored at the user level, not per-profile. All of a user's profiles share the same favorites list. (This is a deliberate simplification — if per-profile favorites become desirable, it is a separate feature.)
- **Import favorites from linked league**: No feature to auto-import a user's drafted players or watchlist from Sleeper/ESPN/Yahoo as favorites.
- **Bulk add by position or team performance**: No "add all WRs on KC" shortcut.
- **Anonymous-user favorites (persisted via localStorage)**: Not in scope. Anonymous users get no favorites functionality at all.
- **Player photo / avatar in the favorites UI**: Not in scope. Use position badge and name only.
- **Un-favoriting all at once**: No "clear all" button in v1. Users remove favorites individually.

---

## Open questions — resolved by Manager triage

All five questions resolved before Engineer dispatch. Locked decisions:

1. **Player search data source** → **New `GET /players?q=<name>` endpoint.** Auth-gated (favorites are auth-gated, so the search affordance is too). Returns matching players (player_id, name, position, team) capped at 25 results. Avoids the chicken-and-egg first-time-user problem.

2. **Favorites scope** → **User-level. Locked.** One favorites list per user, shared across all profiles. Per-profile favorites is explicitly out of scope.

3. **Generate request shape** → **Server-side lookup via auth cookie.** Backend resolves favorites from the authenticated user inside the generate handler. Frontend does NOT pass `favorite_player_ids` or `favorite_teams` in `GenerateRequest`. Anonymous calls: lookup yields empty sets, the Favorites rule's condition field stays `None` and the rule silently doesn't fire.

4. **Favorites tab placement** → **Tab in `LinkedAccountsDialog`.** New tab next to the existing linked-accounts rows. Same modal users already open from the header.

5. **Auto-enable Favorites rule on first add** → **Backend, inside `PUT /favorites`.** When a user transitions from 0 favorites to 1+, the same transaction enables the Favorites rule in their currently-active profile's `rules_json`. Single source of truth, no race condition with the frontend autosave.

These resolutions are inputs to the implementation plan that follows from this spec.
