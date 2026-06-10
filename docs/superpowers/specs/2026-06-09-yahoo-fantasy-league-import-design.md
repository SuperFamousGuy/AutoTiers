# Yahoo Fantasy League Import — Design

## Goal

Allow users who have linked their Yahoo account to also connect a Yahoo Fantasy Football league, importing scoring settings and keeper data into a profile — the same outcome Sleeper and ESPN linking already deliver.

## Approach

Extend the existing Yahoo OAuth link flow with an `intent=yahoo_fantasy` path that requests the `fspt-r` (Fantasy Sports read) scope in addition to `openid email`. Store encrypted access + refresh tokens on the `User` model. A new Yahoo Fantasy API client lists the user's leagues; the user picks one; scoring settings are stored on `LinkedLeague` exactly as Sleeper and ESPN do today. Token refresh is handled transparently on 401 responses.

Sign-in flow (`AuthDialog`) is unchanged — identity scopes only.

## User-facing impact

**LinkedAccountsDialog — Yahoo tab, four states:**

1. **No Yahoo linked**: "Continue with Yahoo" button (unchanged — redirects to `/api/auth/yahoo/authorize?intent=link`).
2. **Yahoo linked, no fantasy token**: "Yahoo account linked" badge + "Connect Yahoo Fantasy" button → redirects to `/api/auth/yahoo/authorize?intent=yahoo_fantasy`.
3. **Fantasy token present, no league selected**: League picker — dropdown of the user's NFL leagues fetched from Yahoo Fantasy API + "Link League" button.
4. **League linked** (`linked_league.provider === "yahoo"`): Green "Connected!" card showing league name + season + Disconnect button.

Error states:
- Yahoo Fantasy API unreachable / timeout → 504, surface as "Yahoo timed out. Try again."
- 401 after token refresh fails → surface as "Yahoo session expired — reconnect Yahoo Fantasy."
- League not found → 404, surface as "League not found."

Loading state: spinner while fetching league list (same pattern as `SleeperConnectForm`).

## Code-facing impact

### New: `backend/app/models/user.py`
Two new nullable columns on `User`:
```python
yahoo_access_token: Mapped[Optional[str]]   # Fernet-encrypted
yahoo_refresh_token: Mapped[Optional[str]]  # Fernet-encrypted
```

### New: `backend/alembic/versions/009_yahoo_tokens.py`
Adds `yahoo_access_token` and `yahoo_refresh_token` to `users` table.

### Modified: `backend/app/auth/yahoo.py`
- `build_authorize_url(state, fantasy=False)` — includes `fspt-r` in scope when `fantasy=True`
- `exchange_code(code) -> tuple[str, str | None]` — returns `(access_token, refresh_token)`. Yahoo only returns a refresh token when offline-access-capable scopes (e.g. `fspt-r`) are requested; identity-only flows get `None`. Existing callers in the sign-in/link callback discard the second element.
- New: `refresh_access_token(refresh_token) -> str` — POSTs to `TOKEN_URL` with `grant_type=refresh_token`, returns new access token

### Modified: `backend/app/api/auth.py`
- `/yahoo/authorize`: when `intent=yahoo_fantasy`, calls `build_authorize_url(state, fantasy=True)` and sets `autotiers_oauth_intent=yahoo_fantasy` cookie
- `/yahoo/callback`: when `autotiers_oauth_intent == "yahoo_fantasy"`, stores encrypted tokens on `User`, then redirects to frontend

### Modified: `backend/app/schemas/auth.py`
- `UserOut` gains `yahoo_fantasy_connected: bool` — true when `yahoo_access_token IS NOT NULL`; raw token never exposed

### New: `backend/app/integrations/yahoo_fantasy.py`
```python
async def list_user_leagues(access_token, refresh_token, user, db) -> list[LeagueSummary]
async def fetch_league(league_key, access_token, refresh_token, user, db) -> LeagueData
```
Both call `refresh_access_token` transparently on 401, persist new tokens to `user`, commit `db`.

Yahoo Fantasy API endpoints:
- `GET https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues?format=json`
- `GET https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings?format=json`

`LeagueData` shape: `league_id`, `name`, `season`, `league_size`, `raw_scoring`, `keepers`, `adp_json` — identical to `SleeperLeagueData` / `EspnLeagueData`.

### New: `yahoo_to_settings` in `backend/app/integrations/scoring_mappers.py`
Maps Yahoo's stat modifier format (`stat_modifiers.stats.stat[].value` keyed by `stat_id`) to AutoTiers settings fields. Stat IDs of interest (engineer must verify against a real Yahoo league response before hardcoding): 4 (passing TDs), 5 (passing yards), 24 (rushing TDs), 25 (rushing yards), 42 (receiving TDs), 43 (receiving yards), 31 (receptions). Default PPR = 1.0 if `stat_id 11` (receptions) has a 1.0 modifier.

### Modified: `backend/app/api/linked_league.py`
Two new endpoints:
- `GET /profiles/{profile_id}/link/yahoo/leagues?season={year}` — returns `list[YahooLeagueSummaryOut]`
- `POST /profiles/{profile_id}/link/yahoo` — body: `{league_key: str, season: int}` — fetches league, stores `LinkedLeague`, returns `LinkedLeagueResponse`

Error handling follows `_provider_http_error` pattern.

### New: `web/src/components/YahooConnectForm.tsx`
Mirrors `SleeperConnectForm`. Props: `profile`, `user`, `onLinked`, `onRefresh`. Handles states 3 and 4 above. Calls `GET /api/profiles/{id}/link/yahoo/leagues` on mount when no league is linked.

### Modified: `web/src/components/LinkedAccountsDialog.tsx`
Yahoo tab renders `<YahooConnectForm>` instead of the hardcoded "coming soon" message.

### Modified: `web/src/api/auth.ts` / `web/src/api/types.ts`
`User` type gains `yahoo_fantasy_connected: boolean`.

## Out of scope

- Keeper data import from Yahoo (Yahoo keeper config lives in draft settings, not league settings — requires a separate API call and is complex; file as follow-up issue)
- ADP data from Yahoo leagues (Yahoo doesn't expose live ADP via public API)
- Token revocation on Yahoo unlink (unlink already deletes `yahoo_subject`; should also clear tokens — file as follow-up)
- Google sign-in users linking Yahoo Fantasy without a Yahoo identity link (not a real flow)
- NFL Fantasy and CBS imports (explicitly "coming soon" in the UI)

## Open questions

None — all resolved during design.
