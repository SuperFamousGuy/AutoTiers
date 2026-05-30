# Fantasy League Linking (Sleeper + ESPN) — Design

## Goal

Let users link a fantasy league to a profile so AutoTiers can auto-detect scoring settings, mark keepers, and use league-side draft positions as an additional consensus input. Sleeper and ESPN are in scope. NFL Fantasy and CBS are shown as "coming soon" placeholders — they would require scraping with stored login credentials, which is out of scope.

## Decisions (locked)

- **Scope:** Sleeper + ESPN. NFL Fantasy + CBS are UI placeholders only.
- **Linkage granularity:** per-profile. A user with two leagues makes two profiles. Each profile has at most one linked league.
- **Use cases:** auto-detect scoring, league-specific ADP as a consensus input, mark keepers (excluded from tier output).
- **Refresh policy:** fetch on link, plus a manual Refresh button. No background scheduler.
- **ESPN auth:** League ID with a "Private league?" toggle that reveals SWID + espn_s2 cookie fields and help text on where to find them.
- **Secret storage:** Fernet (symmetric AES) encryption at rest using a server-side `secret_key`. Only the espn_s2 cookie is encrypted — league_id and SWID are stored in plaintext.
- **UI location:** extend the existing `LinkedAccountsDialog` with a second section labelled for the active profile. Sign-in providers stay per-user; fantasy leagues are per-profile.

## Data model

New table `linked_leagues` with a 1:1 relationship to `profiles`:

```python
class LinkedLeague(Base):
    profile_id: UUID PK FK profiles.id ON DELETE CASCADE  (unique)
    provider: str                    # "sleeper" | "espn"
    league_id: str                   # platform's league identifier
    username_or_swid: str            # Sleeper username, or ESPN SWID (kept raw — not a secret on its own)
    credentials_encrypted: str | None  # Fernet-encrypted espn_s2 cookie; null for Sleeper
    league_metadata_json: dict       # {name, season, scoring_digest, ...}
    keepers_json: list[dict]         # [{player_name, position, team}, ...]
    adp_json: dict | None            # {player_name: avg_pick_overall} — only when platform exposes draft data
    last_synced_at: datetime
```

Alembic migration `006_linked_league.py` creates the table with an FK cascade so deleting a profile drops its linked league.

A separate table (rather than columns on `Profile`) keeps Profile clean, makes "disconnect" a single row delete, and gives the linked league its own clear refresh lifecycle.

## Backend

### Secret storage

New config setting `secret_key: str` (Fernet key — base64-urlsafe 32-byte string). For dev we ship a default and document overriding it for production. Helper module `backend/app/security/fernet.py` exposes `encrypt(plaintext: str) -> str` and `decrypt(ciphertext: str) -> str`. The helper uses `cryptography.fernet.Fernet`.

### Provider integrations

A new package `backend/app/integrations/` — distinct from `backend/app/data/sources/` which holds global-population fetchers run on a schedule. The integrations package holds per-user-league clients invoked synchronously on connect/refresh.

- `integrations/sleeper.py`
  - `async list_user_leagues(username: str, season: int) -> list[LeagueSummary]` — calls the public Sleeper API: GET `/v1/user/{username}` then `/v1/user/{user_id}/leagues/nfl/{season}`.
  - `async fetch_league(league_id: str) -> LeagueData` — pulls league settings, owners, keepers, and (if a draft exists) draft picks.
- `integrations/espn.py`
  - `async fetch_league(league_id: str, season: int, swid: str | None, espn_s2: str | None) -> LeagueData` — issues one call to `https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}?view=mSettings&view=mTeam&view=mDraftDetail`. Public leagues work without cookies; private leagues require both.
- `integrations/scoring_mappers.py`
  - `sleeper_to_settings(raw_scoring: dict) -> SettingsState`
  - `espn_to_settings(raw_scoring: dict) -> SettingsState`
  - Each derives `scoring_format` (PPR / half / standard), `qb_td_points`, `bonus_100yd_rushing`, `bonus_100yd_receiving`, `bonus_first_downs`, and `league_size`. They do NOT touch `weights` (those are user preferences, not league-defined).
- `integrations/types.py` defines `LeagueSummary` (id, name, season) and `LeagueData` (metadata + raw_scoring + keepers + adp_json or None).

### Endpoints

All under `/api/profiles/{id}/link/`. All require `require_user` and verify the profile belongs to the caller.

- `GET /sleeper/leagues?username={X}&season={year}` — preview helper. Calls `list_user_leagues`. Returns `[{id, name, season}, ...]`. Used by the frontend to populate a dropdown when the user enters their Sleeper username.
- `POST /sleeper` — body `{username, league_id, season}`. Calls `fetch_league`, runs `sleeper_to_settings`, writes the mapped settings into `profile.settings_json`, upserts the `LinkedLeague` row. Returns `{linked_league, profile}`.
- `POST /espn` — body `{league_id, season, swid?, espn_s2?}`. Calls `fetch_league`. Encrypts `espn_s2` (if present) before storing. Runs `espn_to_settings`. Same return shape.
- `POST /refresh` — re-fetches from the linked provider using the stored credentials. Returns the updated record. Re-applies the auto-detected settings to `profile.settings_json` (overwriting any user edits to the four mapped fields — this is the trade-off for refresh).
- `DELETE /` — deletes the `LinkedLeague` row. `profile.settings_json` is untouched (the user keeps whatever values were last auto-detected; they can edit freely after disconnect).

`MeResponse` already returns `profiles[]` — extend `ProfileOut` with `linked_league: LinkedLeagueOut | None` so the frontend has the linked-league state in the same payload.

### Error handling

- Provider call failures: 502 with detail `"Couldn't reach Sleeper"` / `"ESPN couldn't verify those cookies — they may be expired"`.
- Sleeper username not found: 404 from the leagues-listing endpoint.
- ESPN private league without cookies: 403 from ESPN → translated to 400 with the cookie-expired message + a hint that the league may be private.
- All endpoints validate that the profile id belongs to the authenticated user — 404 otherwise.

## Tier-equation integration

Three integration points in the existing tier flow:

1. **Auto-detected scoring.** Handled entirely at link/refresh time on the backend (overwrites `profile.settings_json`'s mapped fields). The frontend re-reads `/me` and the Settings panel reflects the new values. A new chip in the Settings panel reads "Auto-detected from <provider> league <name>" with a Refresh action.

2. **League ADP.** `GenerateRequest` gains an optional `league_adp: dict[str, float] | None`. When the active profile has a linked league with a non-null `adp_json`, the frontend includes it. The tier engine blends league ADP 50/50 with the existing consensus input when both exist; uses league ADP alone if FantasyPros consensus is missing; uses FantasyPros consensus alone if league ADP is missing. The user-facing `weight_consensus` slider continues to control the overall consensus weight — we just changed how the consensus signal is computed when a league is linked.

3. **Keepers.** `GenerateRequest` gains an optional `keepers: list[str] | None` (player names matching AutoTiers' canonical naming). When present, the engine filters them out of the candidate pool before tier computation. Keepers also appear as a small read-only "Keeper picks (excluded)" list in the TiersPanel for visibility.

### Player name reconciliation

Sleeper and ESPN return their own player IDs and name spellings. We use the existing `app/data/name_normalize.py` fuzzy matcher (built for the data pipeline) to map provider player names to our canonical `Player` rows. Unmatched names get logged and excluded with a warning rather than crashing the link.

## Frontend

### `LinkedAccountsDialog` (extended)

Two sections separated by a `<DialogSeparator>` (or simple horizontal rule):

- **Sign-in providers** (existing): Email + Google + Yahoo. Unchanged.
- **Fantasy league for "<active profile name>"** (new): Either Connect buttons for Sleeper + ESPN (plus grayed-out NFL Fantasy + CBS rows marked "Coming soon"), or a connected-state row showing provider + league name + Refresh + Disconnect.

The Connect buttons open inline sub-forms within the dialog (don't open a second modal — keeps the UX inside one place).

The "Fantasy league" section operates on the currently-active profile only. To link a different profile, the user switches profiles via the existing ProfilePicker, then reopens the dialog. If no profile is active (rare edge case — signup creates one), the section shows a small "Select a profile first" message.

#### Sleeper sub-form

Two steps. Step 1: username input → Continue. Frontend calls `GET /sleeper/leagues?username=...`. Step 2: dropdown of returned leagues → Connect. Frontend calls `POST /sleeper` with chosen league_id.

#### ESPN sub-form

Single step. League ID input, "Private league?" toggle. When toggled on, SWID and espn_s2 password-style inputs appear with a help link to "How to find these in your browser" (a small inline popover with instructions). Connect → `POST /espn`.

### State integration

`AuthContext.refresh()` re-fetches `/me` and the new `linked_league` field flows through `profiles[]`. After connect/refresh/disconnect succeed, the dialog calls `refresh()` to update the profile's `linked_league` and `settings_json` everywhere they're read.

### Settings-panel chip

When the active profile has a linked league, show a small chip above the Settings panel: "Auto-detected from <provider> · <league name>" with a Refresh icon button. Clicking Refresh calls `POST /api/profiles/{id}/link/refresh` then `refresh()`.

### Tier-equation wiring

`buildRequest()` in `App.tsx` already constructs the `GenerateRequest`. It gains two new optional fields when the active profile has a linked league:
- `league_adp` from `activeProfile.linked_league.adp_json`
- `keepers` derived from `activeProfile.linked_league.keepers_json[].player_name`

### TiersPanel keepers display

When `keepers` was passed to the generate request, the result panel renders a small "Keepers (excluded from tiers)" list at the top. Read-only.

## Testing

### Backend

`backend/tests/test_integrations/`:
- `test_sleeper.py` — mocks Sleeper API with respx. Covers: user lookup, list_user_leagues, fetch_league (with + without draft data), scoring mapper happy paths (PPR / half / standard / non-standard QB TD), keeper extraction.
- `test_espn.py` — mocks ESPN with respx. Covers: public league fetch, private league fetch with cookies, scoring mapper, expired-cookie error path, keeper extraction.
- `test_scoring_mappers.py` — table-driven tests for each provider's scoring → SettingsState mapping.

`backend/tests/test_linked_league_endpoints.py`:
- Connect Sleeper happy path (settings get written, LinkedLeague row created).
- Connect Sleeper username-not-found → 404.
- Connect Sleeper with username having multiple leagues — list endpoint returns all, connect picks the chosen one.
- Connect ESPN public league happy path.
- Connect ESPN private without cookies → 400 with the cookie hint.
- Refresh re-runs the fetch and updates `last_synced_at` + settings.
- Disconnect deletes the row, leaves `profile.settings_json` intact.
- Cross-user access: profile owned by another user → 404.

### Frontend

`web/src/tests/components/LinkedAccountsDialog.test.tsx` (extended):
- Renders the "Fantasy league" section with active profile name.
- Sleeper sub-form: username submit lists leagues, picks one, confirms.
- ESPN sub-form: private toggle reveals cookie fields, submission posts with cookies.
- Connected state shows provider + league name + Refresh + Disconnect.
- Disconnect triggers `refresh()` and re-renders to "Connect" state.

`web/src/tests/integration/app-authenticated.test.tsx` (extended):
- When the active profile has `linked_league`, `buildRequest` includes `league_adp` and `keepers` in the generate POST.
- Settings panel shows the auto-detected chip.

## Not doing (YAGNI)

- NFL Fantasy and CBS scrapers — security and reliability hazards without public APIs.
- Background-scheduled refresh.
- Live draft-state polling (live picks during a draft).
- Multiple linked leagues per profile.
- New ADP-weight slider (reuses existing `weight_consensus`).
- Encrypting league_id and Sleeper username — not credentials.
- Letting users override individual auto-detected settings without disconnecting (the chip + Refresh model is enough for v1).
- League roster sync beyond keepers.
