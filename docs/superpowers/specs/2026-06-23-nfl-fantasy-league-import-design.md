# NFL.com Fantasy League Import — Design

GitHub issue: #91 (Deliverable B — league linking only). NFL expert/draft rankings is split to a follow-up issue and is explicitly out of scope here, mirroring exactly how the CBS deliverable (issue #90) split its rankings half to #422 and shipped "league linking only."

## Goal

Let a user link their NFL.com fantasy league by pasting the league's numeric League ID, so AutoTiers can import that league's identity (name, season) and roster/league size into the active profile — the same outcome Sleeper, ESPN, Yahoo, and CBS linking already deliver. This is the lowest-friction provider yet: NFL.com's read API is anonymous for league metadata, so no credentials are collected at all.

## Approach

NFL.com fantasy exposes an **anonymous-read** v2 JSON API at `api.fantasy.nfl.com/v2/league/*`. Confirmed live this session (2026-06-23): `GET /v2/league/standings?leagueId={id}&season={year}` and `GET /v2/league/teams?leagueId={id}&season={year}` both return HTTP 200 with full league metadata (name, leagueType, numTeams, divisions, teams) for BOTH public and private leagues, with no app key, no cookie, no OAuth. This makes NFL the simplest integration in the series: a single text input (League ID) plus a season, no credential exchange (unlike CBS), no cookie paste (unlike ESPN), no OAuth redirect (unlike Yahoo). It follows the **Sleeper public-league precedent** most closely (league_id in, public JSON out), NOT the CBS credential-exchange precedent — the architectural mirror request from the Manager is satisfied at the *file/endpoint/wiring layer* (new `integrations/nfl.py`, new `nfl_to_settings`, new `post_nfl` + `/refresh` branch, new `NflConnectForm`), while the auth model is deliberately simpler because NFL's API does not require auth.

Because no credentials are collected, `LinkedLeague.credentials_encrypted` is `None` and `username_or_swid` is `""` for NFL — exactly as Sleeper does today.

## User-facing impact

### Flow

`LinkedAccountsDialog` → NFL Fantasy tab (currently a "Coming Soon" stub with `comingSoon: true`) → `NflConnectForm` renders one of two states based on `activeProfile.linked_league?.provider === "nfl"`.

**State 1 — Not linked.** A form with two fields:
- **League ID** — text input, `aria-label="League ID"`, placeholder `e.g. 123456`, helper copy: "Find it in your NFL.com league URL: https://fantasy.nfl.com/league/{league_id}".
- **Season** — number input, `aria-label="Season"`, defaulting to the current NFL season via the existing `currentSeason()` helper (`web/src/lib/season.ts`), mirroring how Sleeper/ESPN pre-fill season. NFL's API requires a season in the path, so it is required (not optional).

A short explanatory line above the form, matching ESPN's instruction-block tone:
> "We read your NFL.com league's public info — name, size, and teams. No NFL.com login needed."

This sentence is load-bearing trust copy: it must NOT promise scoring import (see Out of scope — scoring is appKey-gated and not imported in this deliverable). Honest copy per bug-class #1.

Connect button disabled until League ID is non-blank after `.trim()` AND season is a valid 4-digit year (bug-class #2 — whitespace-only / empty / non-numeric season must fail).

**State 2 — Linked** (`linked_league.provider === "nfl"`). Green "Connected!" card, same visual structure as `EspnConnectedState`/`CbsConnectedState`:
- Green checkmark badge + "Connected!"
- League name + season (from `league_metadata_json`)
- "NFL Fantasy" provider label
- Refresh button (only shown when `linked.league_id` is set — mirrors the sibling conditional)
- Disconnect button (always shown)

No credential field is ever rendered. The form never echoes back any input on success.

### Loading state

While connect is in flight: Connect button `disabled`, label stays "Connect" (no spinner component exists for inline buttons; consistent with siblings). Refresh/Disconnect follow the `busy` disable pattern.

### Error states

All error copy is the backend's `HTTPException.detail` surfaced verbatim via `ApiError` (bug-class #1), per the `_provider_http_error` pattern. Cases the backend must distinguish:

| Condition | Backend status | Detail text (verbatim) |
|---|---|---|
| Empty / whitespace-only League ID, or invalid season | 400 | "Provide your NFL.com League ID and a valid season. Nothing to link without both." |
| League ID not found (NFL returns a JSON `errors` array `LEAGUE_INVALID` "League does not exist." — NOT a 4xx; embedded in a 200 body) | 404 | "NFL.com couldn't find league {id} for {season}. Check the League ID and season." |
| NFL API times out | 504 | via `_provider_http_error`: "NFL.com timed out. Try again in a moment." |
| NFL API returns a non-200 / unexpected shape | 502 | via `_provider_http_error`: "NFL.com returned HTTP {status}. Verify the league id." |

CRITICAL parity with the CBS auth quirk: NFL's `/v2` API returns **HTTP 200 with an embedded `{"errors":[{"messageStringId":"LEAGUE_INVALID",...}]}` body** for a non-existent league (confirmed live: `leagueId=999999999` → 200 with `LEAGUE_INVALID`). The Engineer must inspect the JSON body for an `errors` array, NOT rely on `raise_for_status()`, exactly as `cbs.get_access_token` does for CBS's 200-with-errors auth quirk. This is bug-class #4 (third-party defaults) — the status code lies.

### Empty / first-visit & accessibility

- The NFL tab always shows the form (State 1) or the connected card (State 2) — never blank.
- Keyboard reach: League ID → Season → Connect in document order; native `<input>`/`<button>`. Focus-visible relies on existing shadcn defaults (no new `outline: none`).
- `aria-label` on both inputs and on Connect/Refresh/Disconnect ("Disconnect NFL", "Connect NFL" analogues).
- Mobile width (~375px): two stacked inputs + button, same layout as `CbsConnectForm` minus one field.

## Code-facing impact

### New: `backend/app/integrations/nfl.py`

One function (no auth step — divergence from CBS, which needed `get_access_token`):

```python
async def fetch_league(league_id: str, season: int) -> LeagueData:
    """GET api.fantasy.nfl.com/v2/league/{standings,teams}. Anonymous read.
    Raises NflLeagueNotFound when NFL returns a 200 body with an
    errors array (LEAGUE_INVALID) — NFL does not 404 a bad league id."""
```

- Base: `https://api.fantasy.nfl.com/v2/league`
- Views: `standings` (league name, leagueType, numTeams, divisions, teams) and `teams` (roster detail; confirmed HTTP 200 anonymously). Query: `?leagueId={id}&season={season}`.
- The response nests the league under `games.{gameKey}.leagues.{leagueId}` — the Engineer reads the single league out of `games` regardless of the synthetic gameKey (e.g. `102025`), since the gameKey is derived from season and not known a priori. Defensive: iterate `games.values()` → first `leagues.values()` rather than hardcoding a gameKey.
- New exception `NflLeagueNotFound(Exception)` — raised when the body carries an `errors` array (mirrors `CbsAuthRequired`'s role of distinguishing a known provider-side condition from a generic failure). The API layer maps it to HTTP 404.
- A browser `User-Agent` is pinned on every request (bug-class #4 — mirror `espn.py`'s `_BROWSER_UA`; NFL's edge may reject the default `python-httpx/x.y` UA). `timeout=10.0`, matching every sibling client.
- Returns the shared `LeagueData` dataclass. `league_size = int(numTeams)`. `name = league name`. `season = the requested season` (NFL has no separate season field in the body; the caller supplied it — same honest-source pattern as CBS's `_current_season`). `raw_scoring = {}` (scoring is appKey-gated and not fetched — see Out of scope). `keepers = []` (no keeper field on the anonymous endpoints). `adp_json = None` (no draft endpoint anonymously).

### New: `nfl_to_settings(raw_scoring, league_size) -> dict` in `backend/app/integrations/scoring_mappers.py`

Same class as the four existing mappers. BUT: because NFL scoring is not fetchable in this deliverable (`raw_scoring` is `{}`), `nfl_to_settings` emits ONLY `league_size` and NO scoring keys at all. This matters because `_apply_settings` does `settings_json.update(mapped)`: if the mapper emitted placeholder scoring keys (`scoring_format="standard"`, `qb_td_points=4.0`, ...), linking NFL would SILENTLY OVERWRITE a user's existing PPR / 6pt-TD scoring with standard defaults — a real regression (bug-class #1; caught in QA on first pass and corrected). Emitting only `league_size` leaves the user's prior scoring untouched. The scoring path stays wired for the future appKey case: if `raw_scoring` ever carries real data, the same `_classify_ppr` path the other mappers use honors it. This MUST be called out so the Engineer does not invent NFL stat-key constants for keys that aren't in the payload.

### Modified: `backend/app/api/linked_league.py`

New `NflConnectBody`:
```python
class NflConnectBody(BaseModel):
    league_id: str
    season: int
```
Both required (no pre-link state — NFL needs a league_id to fetch anything, like CBS, unlike ESPN's cookies-only pre-link).

New endpoint `POST /profiles/{profile_id}/link/nfl`, mirroring `post_sleeper` (the closest precedent — public read, no credentials):
1. Validate `league_id.strip()` non-blank and `season` is a plausible 4-digit year; else 400.
2. `data = await fetch_nfl_league(league_id, season)`. On `NflLeagueNotFound` → `HTTPException(404, "NFL.com couldn't find league {id} for {season}. Check the League ID and season.")`. On other exceptions → `_provider_http_error("NFL.com", e)`.
3. `ll.provider = "nfl"`; `ll.username_or_swid = ""`; `ll.credentials_encrypted = None` (NO credentials — like Sleeper).
4. `mapped = nfl_to_settings(data.raw_scoring, league_size=data.league_size)`, `_apply_settings`.
5. Populate `league_id`, `league_metadata_json={"name":..., "season":...}`, `keepers_json=data.keepers` (`[]`), `adp_json=data.adp_json` (`None`), `last_synced_at`.
6. Commit, refresh, return `_build_response`.

New `nfl` branch in `POST /link/refresh`, mirroring the `sleeper` branch (re-fetch by league_id + stored season; no credential decrypt needed):
```python
elif ll.provider == "nfl":
    try:
        data = await fetch_nfl_league(ll.league_id, stored_season)
    except NflLeagueNotFound:
        raise HTTPException(status_code=404, detail="NFL.com couldn't find this league anymore — it may have been deleted or made private.")
    except Exception as e:
        raise _provider_http_error("NFL.com", e)
    mapped = nfl_to_settings(data.raw_scoring, league_size=data.league_size)
```
The existing `stored_season` guard (lines 418-420) already protects against missing season metadata — reused, no change.

### Modified: `web/src/api/linkedLeague.ts`
Add `connectNfl(profileId, { league_id, season })` mirroring `connectSleeper`/`connectCbs`. No `listNflLeagues` (no list endpoint; user supplies league_id, like ESPN/CBS public path). MUST have a real fetch-level test (bug-class #7 — the CBS/Yahoo spy-mock coverage gap; see `web/src/tests/api/linkedLeague.test.ts`).

### Modified: `web/src/api/types.ts`
`LinkedLeague.provider` widens to `... | "cbs" | "nfl"`.

### Modified: `web/src/components/LinkedAccountsDialog.tsx`
- Remove `comingSoon: true` from the `nfl` TABS entry (line 42).
- Replace the `case "nfl"` "Coming Soon" block with `<NflConnectForm .../>`, gated by the same "select a profile first" guard the other providers use. Bug-class #6 invariant preserved: all five tabs still render.

### New: `web/src/components/NflConnectForm.tsx`
Mirrors `CbsConnectForm.tsx` structurally (default export + internal `NflConnectedState`, `useState` for `leagueId`, `season`, `error`, `busy`), minus the email/password fields. Props identical: `{ profile, onLinked, onRefresh }`.

### Schema / data-model — explicit non-change
`backend/app/schemas/linked_league.py` `LinkedLeagueOut` is unchanged (already omits credential fields; NFL adds none). Update the `provider` docstring comment to include `"nfl"`. `backend/app/models/linked_league.py` and `user.py` are NOT touched — no new columns, no Alembic migration (NFL reuses the generic columns exactly as Sleeper does).

## Math / statistical claims
None. `nfl_to_settings` is field-mapping with honest defaults — no formula, no Mathematician consult needed (consistent with CBS).

## FF heuristic basis
None new. This imports a league's own identity/size. The Researcher consult here was a technical "what does the NFL.com API look like" question (resolved live this session, findings logged to `autotiers-ff-knowledge`), not an FF-domain heuristic.

## Out of scope
- **NFL expert/draft rankings** — the rankings half of issue #91. No anonymous JSON rankings/projections feed was found (the v1 stats feed is dead, HTTP 404, mirroring AutoTiers' already-dead cbs/spotrac scrapers). Split to a NEW follow-up issue (the #422 analogue), filed by the Manager in Stage 3.6. MUST be filed — issue #91's third line ("Pull NFL ranking data") is real deferred user value.
- **NFL scoring-settings import** — `/v2/league/settings` is gated behind an NFL `appKey` (confirmed live: returns `INPUT_INVALID_APP_KEY` "Must be between 1 and 40 chars" without one). AutoTiers has no app key and NFL's developer-registration path is not a clean public flow. Until an appKey is obtained, NFL contributes only `league_size`; scoring stays at the user's existing settings. File as a follow-up issue (depends on obtaining an NFL Fantasy API app key).
- **NFL keepers / ADP** — not exposed on the anonymous endpoints; `keepers=[]`, `adp_json=None`, exactly as Sleeper/ESPN/Yahoo degrade when a platform doesn't expose them. Not a blocking gap.
- **Private-league auth** — not needed: NFL's read API returns metadata for private leagues anonymously (confirmed live). No cookie/OAuth path is designed. If NFL later gates private leagues, that is a future v2 design.
- **Multi-league NFL accounts in one profile** — one profile, one linked league (existing invariant); re-linking overwrites. No special handling.

## Open questions
1. **NFL appKey acquisition for scoring** — resolving this is what unblocks the scoring-import follow-up. Non-blocking for this deliverable (league linking ships without it; scoring stays user-controlled).
2. **gameKey derivation** — the league nests under a synthetic `games.{gameKey}` key (e.g. `102025` for 2025). The design instructs the Engineer to iterate `games.values()` rather than compute the gameKey, sidestepping the question. If a season with multiple game entries ever appears, the Engineer reports back; not expected for a single leagueId+season query.
3. **Copy review** — the two trust sentences ("We read your NFL.com league's public info..." and the not-found error) should get a product read before merge; load-bearing for a flow that imports a league with no login. Non-blocking.
