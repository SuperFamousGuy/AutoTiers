# CBS Fantasy League Import — Design

GitHub issue: #90 (Deliverable A — league linking only). CBS expert rankings is split to #422 and explicitly out of scope here.

## Goal

Let a user link their CBS Sports fantasy league by pasting their CBS email + password once, so AutoTiers can import that league's scoring settings, roster/teams, and keepers into the active profile — the same outcome Sleeper, ESPN, and Yahoo linking already deliver.

## Approach

CBS has no public OAuth program. Authentication is a credential exchange against an unofficial mobile-app endpoint: the user's CBS email + password are POSTed server-side and exchanged for an opaque access token. That token — not the password — is what AutoTiers persists, Fernet-encrypted, in `LinkedLeague.credentials_encrypted`, exactly as ESPN stores its `espn_s2` session cookie. This is a **per-league credential exchange, not an identity/OAuth flow**, so it follows the ESPN persistence precedent, not the Yahoo one: no new `User` columns, no Alembic migration, no sign-in-flow changes. The frontend gets a credential-paste form (`CbsConnectForm`) mirroring `EspnConnectForm`'s private-league block — not an OAuth redirect button like Yahoo's.

Keepers have no dedicated CBS settings field; they are derived from the league's transaction log, a new code path with no ESPN/Yahoo precedent (Sleeper and ESPN keepers come from roster/draft-strategy fields; CBS requires walking `/league/transaction-list/log`).

## User-facing impact

### Flow

`LinkedAccountsDialog` → CBS tab (currently a "Coming Soon" stub) → `CbsConnectForm` renders one of two states based on `activeProfile.linked_league?.provider === "cbs"`.

**State 1 — Not linked.** A form with three fields:
- **CBS email** — `type="email"`, `aria-label="CBS email"`, placeholder `you@example.com`.
- **CBS password** — `type="password"`, `aria-label="CBS password"`, placeholder `••••••••`. Never pre-filled, never echoed back in any success or error state, never logged (see Code-facing impact — security).
- **League ID** — text input, `aria-label="League ID"`, placeholder `e.g. 123456`, with helper copy: "Find it in your CBS league URL: https://{league_id}.football.cbssports.com/...".

A short explanatory line above the password field, matching the tone of ESPN's cookie-instructions block (not scary, not hand-wavy):
> "We send your email and password directly to CBS to get a league access token. We don't store your password — only the token CBS gives back."

This sentence is doing real security communication, not just UX — it must ship verbatim or in equivalent plain language; see "Truthful copy" constraint below.

Connect button disabled until all three fields are non-blank (mirrors ESPN's `connectDisabled` pattern — `.trim() === ""` checks, not just non-empty, to reject whitespace-only input per bug-class #2).

**State 2 — Linked** (`linked_league.provider === "cbs"`). Green "Connected!" card, same visual structure as `EspnConnectedState`:
- Header: green checkmark badge + "Connected!"
- League name + season (from `league_metadata_json`)
- "CBS" provider label
- Refresh button (only shown when `linked.league_id` is set — mirrors ESPN's conditional)
- Disconnect button (always shown)

No password field is ever rendered in the linked state. The form never re-displays or pre-fills the email/password used to connect — only `league_metadata_json.name` / `.season`, which come from the backend's `LinkedLeagueOut` response (which already omits `credentials_encrypted` and `username_or_swid`).

### Loading state

While the connect request is in flight: Connect button shows `disabled` + the existing busy-button text pattern used by `EspnConnectForm`/`YahooConnectForm` (button stays labeled "Connect", just disabled — no spinner component exists in this codebase for inline buttons, consistent with siblings). Refresh/Disconnect buttons in the connected state follow the same `busy` disable pattern already in `EspnConnectedState`.

### Error states

All error copy is the backend's `HTTPException.detail` surfaced verbatim via `ApiError`, per the `_provider_http_error` pattern and bug-class #1 (misleading copy). Specific cases the backend must distinguish:

| Condition | Backend status | Detail text (verbatim, surfaced as-is) |
|---|---|---|
| Bad CBS email/password (CBS returns HTTP 200 with an embedded `errors` array — see Researcher findings) | 400 | "CBS rejected your email or password — check both and try again." |
| CBS token request times out | 504 | via `_provider_http_error`: "CBS timed out. Try again in a moment." |
| CBS league fetch returns invalid/expired token (HTTP 400 "Failed Authentication") | 400 | "CBS session expired — reconnect your CBS account." (mirrors `EspnAuthRequired` → "ESPN cookies expired — please reconnect.") |
| League ID not found / wrong league | 502 (falls into `_provider_http_error`'s generic HTTPStatusError branch) | "CBS returned HTTP {status}. Verify the league id and your credentials." |
| Missing required field (email, password, or league_id absent from body) | 422 | Pydantic validation error — `CbsConnectBody`'s three fields are all required, so a missing field is rejected before the handler runs (tests assert 422). |
| Whitespace-only values (fields present but blank after `.strip()`) | 400 | "Provide your CBS email, password, and league ID. Nothing to link without all three." (mirrors the ESPN empty-body guard, bug-class #2) |

The frontend never hand-crafts a "your password might be wrong" guess — it renders `e.message` from `ApiError` directly, same as `EspnConnectForm`/`YahooConnectForm` do today.

### Empty / first-visit state

The CBS tab itself is never blank — it always shows the form (State 1) or the connected card (State 2). No third "nothing here yet" state is needed since the form IS the empty-state affordance.

### Accessibility

- Keyboard reach: all three inputs and the Connect button are native `<input>`/`<button>` elements, reachable via `Tab` in document order (email → password → league ID → Connect), matching `EspnConnectForm`'s layout pattern.
- Focus visible: no new `outline: none` introduced; relies on the existing Tailwind/shadcn focus-ring defaults already used by sibling forms.
- `type="password"` on the password field is non-negotiable per the security posture — confirmed required by the request and matches `EspnConnectForm`'s SWID/espn_s2 fields (lines 194–213 of that file use the same `type="password"` treatment for opaque secrets, even though those aren't literally passwords — CBS's field IS a real password, so the bar is at least as high).
- `aria-label` on every input (email, password, league ID). For the buttons, the Connect and Refresh buttons rely on their visible text label (matching the ESPN/Sleeper/Yahoo forms), while only the icon-ambiguous Disconnect button gets an explicit `aria-label="Disconnect CBS"` — the same pattern the sibling forms use (`aria-label="Disconnect ESPN"` etc.).

## Code-facing impact

### New: `backend/app/integrations/cbs.py`

Two functions, mirroring `yahoo_fantasy.py`'s shape (auth + fetch), not `espn.py`'s shape (cookie-pass-through only — CBS needs an explicit token-exchange step ESPN doesn't):

```python
async def get_access_token(email: str, password: str) -> str:
    """POST .../oauth/mobile/login. Raises CbsAuthRequired on bad credentials."""

async def fetch_league(league_id: str, access_token: str) -> LeagueData:
    """GET league/{details,rules,teams,rosters,transaction-list/log} with
    Authorization: <access_token> header. Raises CbsAuthRequired on 400
    'Failed Authentication: error - invalid access token'."""
```

Endpoints (confirmed live by Researcher this session — use verbatim):
- Auth: `POST https://api.cbssports.com/general/oauth/mobile/login?response_format=json`, body `{"client_id":"cbssports","client_secret":"sportsallthetime","user_id":"<email>","password":"<password>"}` → 200 JSON with `access_token` on success; 200 JSON with `{"body":{"errors":["The member ID or password entered is incorrect."]}}` on bad credentials (NOT a 4xx — the Engineer must inspect the response body, not rely on status code, to detect this failure).
- League data: `GET https://{league_id}.football.cbssports.com/api/league/{details,rules,teams,rosters,standings/overall,schedules,transactions/waiver-order,transaction-list/log}?version=3.0&response_format=json&sport=football&league_id={id}`, header `Authorization: <access_token>`. Invalid/expired token → HTTP 400 `"Failed Authentication: error - invalid access token"`.

New exception class `CbsAuthRequired(Exception)` mirroring `EspnAuthRequired` — raised by both `get_access_token` (bad email/password) and `fetch_league` (expired/invalid token), so the API layer can distinguish "reconnect needed" from generic provider failure. The 200-with-embedded-errors quirk on the auth endpoint means `get_access_token` must raise `CbsAuthRequired` itself (it cannot rely on `httpx.raise_for_status()`, which won't fire on a 200).

Returns the shared `LeagueData` dataclass from `backend/app/integrations/types.py` — no new dataclass needed; scoring lives under `/league/details` + `/league/rules` per Researcher findings, mapped into `raw_scoring`.

**Reference implementation to mine for exact payload shapes and field names**: `uberfastman/fantasy-football-metrics-weekly-report`, file `ffmwr/dao/platforms/cbs.py`. The Engineer must verify CBS's actual JSON field names against a live payload before hardcoding — this design names the AutoTiers-side fields that must be populated, not the CBS-side key names (those are TBD-by-Engineer, consistent with how the Yahoo design treated stat IDs as "verify against a real league response").

### New: `cbs_to_settings(raw_scoring, league_size) -> dict` in `backend/app/integrations/scoring_mappers.py`

Same class as `espn_to_settings`/`yahoo_to_settings` — field mapping, no new math, no Mathematician consult needed. Must populate the same AutoTiers settings keys the other two mappers populate:
- `scoring_format` (derived via the existing `_classify_ppr(rec_value)` helper — reuse it, don't reimplement)
- `league_size`
- `qb_td_points` (passing TD point value)
- `bonus_100yd_rushing`, `bonus_100yd_receiving`, `bonus_first_downs` (booleans; ESPN and Yahoo currently both hardcode these `False` pending key verification — CBS may do the same as an honest placeholder until the Engineer confirms CBS exposes equivalent stat keys under `/league/rules`)

The CBS stat-key names that feed `rec` (receptions value) and `qb_td_points` are TBD-by-Engineer — verify against a live `/league/rules` payload, same caveat the Yahoo design carried for stat IDs.

### Modified: `backend/app/api/linked_league.py`

New `CbsConnectBody` schema (alongside `EspnConnectBody`, `YahooConnectBody`):
```python
class CbsConnectBody(BaseModel):
    email: str
    password: str
    league_id: str
```
Unlike `EspnConnectBody`, all three fields are **required** (not optional) — there is no meaningful "pre-link account without a league" state for CBS, because the league_id is part of the URL path for every CBS API call (no "list my leagues" endpoint was found by the Researcher), so a league must be specified up front. This is a deliberate divergence from ESPN's optional-league pattern — call it out explicitly so the Engineer doesn't try to replicate ESPN's pre-link branch.

New endpoint `POST /profiles/{profile_id}/link/cbs`, mirroring `post_espn` (lines 215–263):
```python
@router.post("/cbs", response_model=LinkedLeagueResponse)
async def post_cbs(
    profile_id: uuid.UUID,
    body: CbsConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
```
Behavior:
1. Validate all three fields non-blank after `.strip()` (bug-class #2 — whitespace-only must fail the same as empty).
2. Call `get_access_token(email, password)`. On `CbsAuthRequired`, raise `HTTPException(400, detail="CBS rejected your email or password — check both and try again.")`. **The plaintext password is used only as a function argument here and is never assigned to a variable that outlives this call, never logged, never persisted.**
3. Call `fetch_league(league_id, access_token)`. On `CbsAuthRequired` (token rejected immediately — unlikely right after exchange, but defensive), raise `HTTPException(400, detail="CBS session expired — reconnect your CBS account.")`. On other exceptions, `_provider_http_error("CBS", e)`.
4. `ll.provider = "cbs"`; `ll.username_or_swid = email` (the model column is `nullable=False` — CBS has no SWID-equivalent, so store the email the same way ESPN stores `swid or ""`; this is metadata, not a secret, and is never exposed via `LinkedLeagueOut` per the schema's existing omission of that field).
5. `ll.credentials_encrypted = encrypt(access_token)` — **the access token, not the password.** The password variable goes out of scope at the end of the request handler and is never written anywhere.
6. Map scoring via `cbs_to_settings`, apply via `_apply_settings`, populate `league_id`, `league_metadata_json`, `keepers_json`, `adp_json` (CBS ADP — see Out of scope), `last_synced_at`.
7. Commit, refresh, return `_build_response`.

Add a `cbs` branch to `POST /link/refresh` (existing branches at lines 349–376), mirroring the `espn` branch:
```python
elif ll.provider == "cbs":
    access_token = decrypt(ll.credentials_encrypted) if ll.credentials_encrypted else None
    if not access_token:
        raise HTTPException(status_code=400, detail="CBS access token missing — please reconnect.")
    try:
        data = await fetch_cbs_league(ll.league_id, access_token)
    except CbsAuthRequired:
        raise HTTPException(status_code=400, detail="CBS session expired — reconnect your CBS account.")
    except Exception as e:
        raise _provider_http_error("CBS", e)
    mapped = cbs_to_settings(data.raw_scoring, league_size=data.league_size)
```
Reuses the stored token — does not re-prompt for email/password on refresh. This is the "store token-only" decision (see token-expiry section below).

### Keepers via transaction log — its own code-facing item

CBS exposes no dedicated keepers field in league settings (unlike ESPN's `draftStrategy.keepers` per team). Keepers must be derived by walking `/league/transaction-list/log` for keeper-designated transactions. The Engineer mines `ffmwr/dao/platforms/cbs.py` for the exact transaction-type discriminator and shape, then populates `LeagueData.keepers` in the same `[{player_name, position, team}]` shape ESPN already uses (`backend/app/integrations/espn.py` lines 67–77) — no new shape, no schema change.

**Effort decision, made explicitly here**: keepers are IN SCOPE for this design (issue #90 names "keepers" as part of Deliverable A, and the user's task framing lists it alongside scoring/roster). If the Engineer's investigation of the transaction log shape proves substantially higher-effort than the FFMWR reference implementation suggests (e.g., the log requires pagination across full season history, or keeper-vs-trade-vs-waiver are not cleanly discriminable from the log alone), that is an **Engineer escalation** back through the Manager — not a silent `keepers=[]`. If escalated, the fallback is `LeagueData.keepers = []` (empty, not broken) and a follow-up issue, exactly like the Yahoo design deferred Yahoo's keepers to a follow-up issue when draft-settings access proved out of scope.

### New: `web/src/components/CbsConnectForm.tsx`

Mirrors `EspnConnectForm.tsx` structurally: a default export function component, an internal `CbsConnectedState` sub-component (mirrors `EspnConnectedState`), `useState` for `email`, `password`, `leagueId`, `error`, `busy`. Props: `{ profile: Profile; onLinked: (result: LinkedLeagueResponse) => void; onRefresh: () => Promise<void> }` — identical prop shape to `EspnConnectForm`, no `user` prop needed (unlike `YahooConnectForm`, since CBS auth is not tied to the AutoTiers `User` identity).

`connectDisabled = busy || email.trim() === "" || password.trim() === "" || leagueId.trim() === ""` — all three required, no optional-credential branching like ESPN's public/private toggle.

### Modified: `web/src/components/LinkedAccountsDialog.tsx`

- Remove `comingSoon: true` from the `cbs` entry in `TABS` (line 42). NFL Fantasy's entry (line 41) is untouched — it stays `comingSoon: true`.
- Replace the `case "cbs"` branch inside the `nfl`/`cbs` combined stub (lines 125–136) — split it so `case "cbs"` renders `<CbsConnectForm profile={activeProfile!} onLinked={() => onRefresh()} onRefresh={onRefresh} />` (with the same "select a profile first" guard the `sleeper`/`espn`/`yahoo` cases already have), and `case "nfl"` keeps the existing "Coming Soon" block alone.
- The "always render all providers" invariant (bug-class #6) is preserved by construction: all five tabs (Sleeper, ESPN, Yahoo, NFL Fantasy, CBS) still render in the tab strip regardless of state; only CBS's per-tab content and its `comingSoon` flag change. The connected-indicator dot logic (`activeProfile?.linked_league?.provider === id`, line 202) already works for any provider string including `"cbs"` with no change needed.

### Modified: `web/src/api/linkedLeague.ts`

```typescript
export function connectCbs(
  profileId: string,
  body: { email: string; password: string; league_id: string },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/cbs`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
```
Mirrors `connectEspn` (line 37–45). No `listCbsLeagues` function — CBS has no "list my leagues" endpoint (per Researcher findings), so unlike Yahoo there is no league-picker step; the user supplies `league_id` directly in the connect form, same as ESPN's public-league path.

### Modified: `web/src/api/types.ts`

`LinkedLeague.provider` type widens from `"sleeper" | "espn" | "yahoo"` to `"sleeper" | "espn" | "yahoo" | "cbs"` (line 134). No new fields needed — `CbsConnectBody` doesn't need a frontend type export since it's only used as an inline object literal in `connectCbs`'s signature, matching `connectEspn`'s pattern.

### Schema — explicit non-change

`backend/app/schemas/linked_league.py`'s `LinkedLeagueOut` is **not modified**. It already omits `credentials_encrypted` and `username_or_swid` from the wire shape — the CBS design adds no new field to that schema and must not add `access_token`, `email`, or `password` to it or to any response type. The `provider` field's docstring comment (`# "sleeper" | "espn"`, line 13) should be updated to include `"yahoo" | "cbs"` for accuracy (the Yahoo design apparently missed updating this comment too — flagging as a one-line touch-up here, not a new design decision).

### Data model — explicit non-change

`backend/app/models/linked_league.py` (`LinkedLeague`) requires **no new columns and no Alembic migration**. CBS reuses the existing generic columns exactly as ESPN does:
- `provider = "cbs"`
- `username_or_swid = email` (repurposed field — see step 4 above)
- `credentials_encrypted = encrypt(access_token)` (repurposed field — holds the CBS token instead of an ESPN cookie)
- `league_id`, `league_metadata_json`, `keepers_json`, `adp_json`, `last_synced_at` — used identically to every other provider

`backend/app/models/user.py` is **not touched**. This is the central divergence from the Yahoo design and is called out explicitly per the task's instruction.

## Math / statistical claims

None. `cbs_to_settings` is field-mapping (provider stat keys → AutoTiers settings keys), identical in kind to `espn_to_settings`/`yahoo_to_settings`. No new formula, weight, or distribution shift. Mathematician consult not needed, consistent with the task's framing.

## FF heuristic basis

None new. This design does not introduce or rely on a debatable fantasy-football heuristic — it imports a league's own configured scoring rules and its own keeper designations verbatim. The Researcher was already consulted (live session, findings reproduced in Code-facing impact above) for the technical question of "what does the CBS API look like," not for an FF-domain heuristic question, so no `autotiers-ff-knowledge` citation applies here.

## Out of scope

- **CBS expert rankings** — split to issue #422, blocked separately (client-side-rendered rankings pages, no discovered JSON endpoint). Not designed here.
- **CBS ADP**, if CBS's API doesn't expose draft-pick-level data the way ESPN's `draftDetail.picks` does. The Engineer determines this while implementing `fetch_league`; if unavailable, `LeagueData.adp_json = None`, exactly as Sleeper/ESPN/Yahoo already do when a platform doesn't expose it. Not a blocking gap — `adp_json` is optional in `LeagueData` today.
- **Password-fallback credential storage.** If live testing proves the CBS access token is single-use (i.e., cannot be reused across `/refresh` calls), the fix is NOT to store the password instead — that would be a meaningful security regression. Re-running the full email+password exchange on every refresh would require storing the password, which this design explicitly forbids. If the token proves single-use, that is an Engineer escalation back to the Designer/Manager for a v2 design (e.g., prompting the user to re-enter credentials at refresh time), not a silent workaround. Recorded as an Open Question below, not resolved here.
- **CBS "list my leagues" picker.** No such endpoint was found; the user must know and paste their `league_id`. If a future Researcher pass discovers a leagues-list endpoint, a Yahoo-style picker step could be added later — not designed now.
- **Token revocation on disconnect.** `DELETE /profiles/{id}/link` already deletes the `LinkedLeague` row (and therefore the encrypted token) for every provider, including CBS once implemented — no CBS-specific revocation call to CBS's servers is designed, matching the fact that ESPN's disconnect doesn't call ESPN either.
- **CBS keepers, if transaction-log mining proves substantially higher-effort than expected** — see the explicit escalation/fallback path under "Keepers via transaction log" above. The default expectation is keepers ARE delivered in this design; this bullet exists only to name the fallback if the Engineer hits a wall.
- **Multi-league CBS accounts in one profile.** A profile links exactly one league at a time (existing "one profile, one linked league" invariant, true for every provider) — re-linking CBS with a different `league_id` overwrites the prior CBS link, same as re-linking Sleeper/ESPN/Yahoo does today. Not a new constraint, just confirming CBS doesn't need special handling here.

## Open questions

1. **CBS access-token reusability/expiry is UNVERIFIED.** The FFMWR reference implementation treats the token as static/indefinitely reusable with no refresh logic, but this has not been confirmed against a live, aged token. This design works correctly under either assumption for the *initial* connect and the *first* refresh (token is fetched once, stored, reused). If the token turns out to expire or be single-use, `/refresh`'s `fetch_league` call will raise `CbsAuthRequired` (via the 400 "Failed Authentication" response), and the user sees "CBS session expired — reconnect your CBS account" — a safe, non-broken degradation, just a worse UX than Yahoo's silent token-refresh. **Non-blocking** — the Engineer resolves this empirically against live CBS during implementation and reports back if the single-use case is confirmed (which would trigger the password-fallback-storage discussion explicitly deferred above).
2. **Exact CBS JSON field names for scoring (`/league/rules`) and the transaction-log keeper-type discriminator are TBD-by-Engineer.** This design names the target AutoTiers fields and points to the FFMWR reference implementation; it does not hardcode CBS-side key names, consistent with how the Yahoo design treated stat IDs ("verify against a real league response before hardcoding").
3. **Copy review** — the two sentences explaining the credential exchange ("We send your email and password directly to CBS...") and the reconnect-needed error ("CBS session expired — reconnect your CBS account.") should get a product read before merge; they're load-bearing for user trust in a password-paste flow. Not blocking implementation, but flagging since this design can't "read it aloud" on the user's behalf.
