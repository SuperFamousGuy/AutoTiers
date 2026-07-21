# Strip Accounts, League Linking, and SES — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn AutoTiers into an anonymous, login-free v1 — users set league settings by hand (persisted in browser `localStorage`), generate tiers, and export; no accounts, no OAuth, no SES.

**Architecture:** Delete the account/auth/OAuth/email/league-linking subsystems from backend and frontend. `/generate` becomes always-anonymous. Named settings profiles and favorites move from server tables to `localStorage`. A destructive Alembic migration drops the account tables; Terraform tears down SES + OAuth/SES secrets. The public data-ingest pipeline (`data/sources/`) and tier engine are untouched.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic (backend), React + TypeScript + Vitest + Tailwind (web), Terraform + AWS (SES/ECS/Secrets Manager).

**Reference spec:** `docs/superpowers/specs/2026-07-21-strip-accounts-league-linking-ses-design.md`

**Locked decisions:** settings + favorites → `localStorage`; full teardown incl. destructive migration + Terraform apply (both human-gated at execution); feedback kept as anonymous persist-only.

---

## Environment notes (read before starting)

- Backend venv is at `backend/venv` (NOT `.venv`). Run pytest as
  `cd backend && venv/bin/python -m pytest ...`. Do **not** run the full suite
  at once (OOM) — run per-file/dir. See skill `autotiers-test-running`.
- Web tests: `cd web && npm run test` (vitest), `npm run build` / `npx tsc -p tsconfig.json --noEmit` for types.
- Keep `auth/admin.py` — it is the shared ops `X-Api-Key` gate used by
  `api/data.py` and `api/feedback.py`, not a personal account.
- `data/sources/` (Sleeper player table, `nfl_data`, `fantasypros`, `cbs`
  scraper) is the public ingest that powers tiers. **Do not touch it.** The
  thing being deleted is `integrations/` (the per-user league-import clients).

---

## File Structure

**Backend — delete**
- `app/api/auth.py`, `app/api/linked_league.py`, `app/api/profiles_api.py`, `app/api/favorites_api.py`
- `app/auth/jwt.py`, `app/auth/google.py`, `app/auth/yahoo.py`, `app/auth/hashing.py`, `app/auth/email_dep.py`, `app/auth/dependencies.py` (keep `admin.py`; `rate_limit.py` — see Task 3)
- `app/email/` (whole package)
- `app/integrations/` (whole package)
- `app/security/fernet.py`
- `app/models/user.py`, `app/models/auth_token.py`, `app/models/linked_league.py`, `app/models/profile.py`, `app/models/user_favorites.py`
- `app/schemas/auth.py`, `app/schemas/profile.py`, `app/schemas/favorites.py`, `app/schemas/linked_league.py`

**Backend — modify**
- `app/main.py` (router registrations + email sender wiring)
- `app/api/generate.py` (drop auth/favorites coupling)
- `app/api/feedback.py` (anonymous persist-only)
- `app/models/feedback.py` (drop `user_id`)
- `app/models/__init__.py` (drop deleted exports)
- `app/config.py` (drop OAuth/JWT/SES/Fernet settings)
- `app/schemas/generate.py` (drop favorite fields — see Task 2)

**Backend — create**
- `app/alembic/versions/015_drop_account_tables.py` (migration; number per `alembic heads`)

**Web — delete** (components)
- `AuthDialog`, `EmailVerificationBanner`, `LinkedAccountsDialog`, `LinkedLeagueChip`,
  `ManageProfilesDialog`, `ProfilePicker`, `NoProfileBanner`,
  `PasswordManagementSection`, `PasswordResetPanel`,
  `CbsConnectForm`, `EspnConnectForm`, `NflConnectForm`, `SleeperConnectForm`, `YahooConnectForm`
- `src/api/auth.ts`, `src/api/profiles.ts`, `src/api/favorites.ts` (server calls), `src/api/linkedLeague.ts`
- `src/hooks/useFavorites.ts` (server-backed) and any AuthContext

**Web — create**
- `src/hooks/useLocalProfiles.ts` (+ test)
- `src/hooks/useLocalFavorites.ts` (+ test)

**Web — modify**
- `src/components/SettingsPanel.tsx`, `src/components/RulesPanel.tsx` (use local profiles)
- `src/components/FavoritesPanel.tsx`, `src/components/FavoritesDialog.tsx` (use local favorites)
- `src/components/Header.tsx`, `src/components/MobileProfileMenuItems.tsx` (remove account/login items)
- `src/api/hooks.ts`, `src/api/types.ts` (drop removed types/queries)
- Client-side `is_favorite` marking after `/generate`

**Infra — modify**
- Terraform SES resources + OAuth/SES/JWT/Fernet secrets + ECS task-def `valueFrom` wiring

---

## Phase 1 — Backend teardown

### Task 1: Unregister removed routers

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Remove the router imports and registrations**

In `backend/app/main.py`, delete these import lines (5–14 region):
```python
from app.api import auth as auth_api
from app.api import profiles_api
from app.api import favorites_api
from app.api.linked_league import router as linked_league_router
from app.email import make_email_sender
```
And delete these registration lines (46–55 region):
```python
app.include_router(auth_api.router, prefix="/api")
app.include_router(profiles_api.router, prefix="/api")
app.include_router(favorites_api.router, prefix="/api")
app.include_router(linked_league_router, prefix="/api")
```
Also remove any `app.state`/lifespan wiring that calls `make_email_sender(...)`
or stores an email sender (search `main.py` for `email` and `sender`).

- [ ] **Step 2: Verify the app still imports**

Run: `cd backend && venv/bin/python -c "import app.main"`
Expected: an `ImportError` from `generate.py`/`feedback.py` still importing
auth is acceptable *only until* Tasks 2–3 land; if you do Task 1 first, expect
failures until then. Prefer doing Tasks 1–5 as one branch, committing after
each, and running the import check after Task 5.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "refactor(backend): unregister auth/profiles/favorites/linked-league routers"
```

### Task 2: Make `/generate` always-anonymous

**Files:**
- Modify: `backend/app/api/generate.py`
- Modify: `backend/app/schemas/generate.py`
- Test: `backend/tests/` (existing generate tests)

- [ ] **Step 1: Write/adjust the failing test — anonymous generate returns no favorite flags**

In the generate test module (find it: `grep -rl "def test_.*generate" backend/tests`),
add:
```python
def test_generate_has_no_favorite_fields(client):
    # Reuse the shared canonical body to avoid 422 on CI (weight_prior_year etc.)
    resp = client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    player = resp.json()["players"][0]
    assert "is_favorite" not in player
    assert "is_favorite_player" not in player
    assert "is_favorite_team" not in player
```
(`_GENERATE_BODY` is the existing canonical request body — see memory
`feedback_ci_test_bodies`. Do NOT hand-roll a body with `weight_prior_year=0.0`.)

- [ ] **Step 2: Run it — expect FAIL (fields still present / auth import error)**

Run: `cd backend && venv/bin/python -m pytest tests/<generate_test_file>.py -k favorite -v`
Expected: FAIL.

- [ ] **Step 3: Remove the auth + favorites coupling in `generate.py`**

- Delete imports: `from app.auth.dependencies import _get_current_user_impl`
  and remove `UserFavorites, User` from the `from app.models import ...` line
  (line 16). Keep `TeamSeason, PlayerContract`.
- Change `_run_generate` signature (line ~377) from
  `async def _run_generate(req, db, current_user: Optional[User] = None)` to
  `async def _run_generate(req, db)`.
- Delete the favorites-lookup block (lines ~412–423) and always use empty sets;
  simplest: delete the `favorite_pids_set`/`favorite_teams_set` computation and
  their propagation into `_project_player`/response. Remove `is_favorite`,
  `is_favorite_player`, `is_favorite_team` from the per-player output (lines
  ~624–719) and the `has_any_favorites` branch.
- Change the endpoint (line ~833) from
  `current_user: Optional[User] = Depends(_get_current_user_impl)` +
  `_run_generate(req, db, current_user)` to just `_run_generate(req, db)`.

- [ ] **Step 4: Drop favorite fields from the response schema**

In `backend/app/schemas/generate.py`, remove `is_favorite`,
`is_favorite_player`, `is_favorite_team` from `TieredPlayerOut` (grep for them).

- [ ] **Step 5: Run generate tests — expect PASS**

Run: `cd backend && venv/bin/python -m pytest tests/<generate_test_file>.py -v`
Expected: PASS. Remove/adjust any existing test that asserted authenticated
favorites behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/generate.py backend/app/schemas/generate.py backend/tests
git commit -m "refactor(backend): make /generate anonymous, drop favorites coupling"
```

### Task 3: Feedback → anonymous persist-only

**Files:**
- Modify: `backend/app/api/feedback.py`
- Modify: `backend/app/models/feedback.py`
- Test: existing feedback tests

- [ ] **Step 1: Write the failing test — anonymous submit persists, no email sender**

```python
def test_feedback_persists_without_email(client, db_session):
    resp = client.post("/api/feedback", json={"category": "bug", "message": "hi"})
    assert resp.status_code == 202
    rows = db_session.execute(select(Feedback)).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id_removed is False  # placeholder — see step 3, user_id column is gone
```
(Adjust the assertion to your test harness; the real check is: 202 + a persisted
row + no `EmailSender` dependency required.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `cd backend && venv/bin/python -m pytest tests/<feedback_test_file>.py -v`
Expected: FAIL (endpoint still requires `get_email_sender` / `get_current_user`).

- [ ] **Step 3: Strip user + email from the endpoint**

In `backend/app/api/feedback.py`:
- Remove imports of `User`, `get_current_user`, `EmailSender`, `get_email_sender`,
  `feedback_email`, and the screenshot/`EmailAttachment` helpers (screenshots
  were only ever emailed, never stored — drop `_decode_screenshot` and the
  `screenshot_*` fields handling).
- Remove `current_user` and `email_sender` params from `submit_feedback`.
- Rate-limit by IP only: `rate_key = f"ip:{_client_ip(request)}"`.
- Persist with `user_id`/`submitter_email` removed:
  `record = Feedback(category=body.category.value, message=message)`.
- Delete the entire `try: await email_sender.send(...)` block and its 502
  handling. Return `{"status": "accepted"}` (or existing shape) with 202.
- Keep the `require_admin`-gated admin read route as-is.

- [ ] **Step 4: Drop `user_id` from the Feedback model**

In `backend/app/models/feedback.py`, remove the `user_id` mapped column and its
`ForeignKey("users.id", ...)`. Keep `submitter_email` nullable OR remove it too
(prefer remove — no user to derive it from). The DB column drop is handled by
the migration in Task 13.

- [ ] **Step 5: Run feedback tests — expect PASS**

Run: `cd backend && venv/bin/python -m pytest tests/<feedback_test_file>.py -v`
Expected: PASS.

- [ ] **Step 6: Decide `rate_limit.py` fate**

Run: `grep -rn "auth.rate_limit\|from app.auth import rate_limit\|feedback_rate_limiter" backend/app`
If `feedback.py` is the only consumer and it uses an inline limiter, and nothing
imports `app/auth/rate_limit.py`, delete `app/auth/rate_limit.py`. Otherwise keep it.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/feedback.py backend/app/models/feedback.py backend/tests
git commit -m "refactor(backend): feedback anonymous + persist-only, drop SES notify"
```

### Task 4: Delete account/auth/email/integrations source

**Files:**
- Delete: the files listed under "Backend — delete" (except keep `auth/admin.py`)
- Modify: `backend/app/models/__init__.py`, `backend/app/auth/__init__.py`, `backend/app/schemas/__init__.py`

- [ ] **Step 1: Delete the modules**

```bash
cd backend
git rm app/api/auth.py app/api/linked_league.py app/api/profiles_api.py app/api/favorites_api.py
git rm app/auth/jwt.py app/auth/google.py app/auth/yahoo.py app/auth/hashing.py app/auth/email_dep.py app/auth/dependencies.py
git rm -r app/email app/integrations
git rm app/security/fernet.py
git rm app/models/user.py app/models/auth_token.py app/models/linked_league.py app/models/profile.py app/models/user_favorites.py
git rm app/schemas/auth.py app/schemas/profile.py app/schemas/favorites.py app/schemas/linked_league.py
```
(If `app/security/` is now empty, `git rm` its `__init__.py` too.)

- [ ] **Step 2: Fix the barrel exports**

In `app/models/__init__.py` remove `User`, `AuthToken`, `LinkedLeague`,
`Profile`, `UserFavorites` from imports and `__all__`. In `app/auth/__init__.py`
and `app/schemas/__init__.py` remove references to the deleted modules.

- [ ] **Step 3: Dangling-import sweep**

Run:
```bash
grep -rn "app.auth.jwt\|app.auth.google\|app.auth.yahoo\|app.auth.hashing\|app.auth.email_dep\|app.auth.dependencies\|app.email\|app.integrations\|app.security.fernet\|models.user\b\|models.profile\|models.linked_league\|models.user_favorites\|models.auth_token\|UserFavorites\|LinkedLeague\b" backend/app
```
Expected: no matches (except `auth/admin.py` and kept files). Fix any straggler.

- [ ] **Step 4: Verify import**

Run: `cd backend && venv/bin/python -c "import app.main; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app
git commit -m "refactor(backend): delete accounts, auth, OAuth, email, league-linking modules"
```

### Task 5: Clean `config.py`

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Remove dead settings**

Delete these fields (lines ~18–36): `jwt_secret`, the Fernet key field,
`yahoo_client_id/secret/redirect_uri`, `google_client_id/secret/redirect_uri`,
`email_sender_backend`, `ses_from_address`, `ses_region`, and any
`feedback_recipient`/`ses_*` fields. Remove `frontend_url` **only if** grep shows
no remaining non-OAuth/email consumer:
```bash
grep -rn "settings.frontend_url\|settings.jwt_secret\|settings.yahoo_\|settings.google_\|settings.ses_\|settings.email_sender_backend\|fernet\|feedback_recipient" backend/app
```
Keep `cors_origins`, `admin_api_key`, DB settings, and data-source settings.

- [ ] **Step 2: Verify + backend test sweep**

Run: `cd backend && venv/bin/python -c "import app.main; print('ok')"`
Then run the surviving suites directory-by-directory (avoid full-suite OOM):
```bash
cd backend && for d in tests/api tests/engine tests/data; do venv/bin/python -m pytest $d -q || break; done
```
Expected: passing (after deleting obsolete suites in Task 6).

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "chore(backend): drop OAuth/JWT/SES/Fernet config"
```

### Task 6: Delete obsolete backend tests

**Files:**
- Delete: test files for auth, oauth, linked-league, profiles, favorites, email

- [ ] **Step 1: Find and remove them**

```bash
cd backend
grep -rl "app.auth.jwt\|app.email\|app.integrations\|profiles_api\|favorites_api\|linked_league\|/api/auth\|/api/profiles\|/api/favorites" tests | xargs git rm
```
Review the list before committing — keep tests that only *incidentally* mention
these (e.g. a generate test you already fixed in Task 2).

- [ ] **Step 2: Run remaining backend suites**

```bash
cd backend && for d in tests/api tests/engine tests/data tests; do venv/bin/python -m pytest $d -q --ignore=tests/api --ignore=tests/engine --ignore=tests/data 2>/dev/null; done
# simpler: run each subdir individually
venv/bin/python -m pytest tests/api -q
venv/bin/python -m pytest tests/engine -q
venv/bin/python -m pytest tests/data -q
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git commit -am "test(backend): remove auth/oauth/linked-league/profiles/favorites suites"
```

---

## Phase 2 — Frontend teardown + localStorage

### Task 7: `useLocalProfiles` store (TDD)

**Files:**
- Create: `web/src/hooks/useLocalProfiles.ts`
- Test: `web/src/hooks/useLocalProfiles.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useLocalProfiles } from "./useLocalProfiles";

beforeEach(() => localStorage.clear());

describe("useLocalProfiles", () => {
  it("creates, persists, and switches profiles", () => {
    const { result } = renderHook(() => useLocalProfiles());
    act(() => result.current.create("PPR", { scoring: "ppr" }, {}));
    expect(result.current.profiles.map((p) => p.name)).toContain("PPR");
    expect(result.current.active?.name).toBe("PPR");
    // persisted
    const raw = localStorage.getItem("autotiers.profiles.v1");
    expect(raw).toContain("PPR");
  });

  it("renames and deletes", () => {
    const { result } = renderHook(() => useLocalProfiles());
    let id = "";
    act(() => { id = result.current.create("A", {}, {}); });
    act(() => result.current.rename(id, "B"));
    expect(result.current.profiles[0].name).toBe("B");
    act(() => result.current.remove(id));
    expect(result.current.profiles).toHaveLength(0);
  });

  it("rejects duplicate names", () => {
    const { result } = renderHook(() => useLocalProfiles());
    act(() => result.current.create("A", {}, {}));
    expect(() => act(() => result.current.create("A", {}, {}))).toThrow();
  });
});
```

- [ ] **Step 2: Run — expect FAIL (module missing)**

Run: `cd web && npx vitest run src/hooks/useLocalProfiles.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement the store**

```ts
// web/src/hooks/useLocalProfiles.ts
import { useCallback, useEffect, useState } from "react";

const KEY = "autotiers.profiles.v1";
const ACTIVE_KEY = "autotiers.activeProfile.v1";

export interface LocalProfile {
  id: string;
  name: string;
  settings: Record<string, unknown>;
  rules: Record<string, unknown>;
}

function load(): LocalProfile[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LocalProfile[]) : [];
  } catch {
    return [];
  }
}

export function useLocalProfiles() {
  const [profiles, setProfiles] = useState<LocalProfile[]>(load);
  const [activeId, setActiveId] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_KEY),
  );

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(profiles));
  }, [profiles]);
  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
    else localStorage.removeItem(ACTIVE_KEY);
  }, [activeId]);

  const create = useCallback(
    (name: string, settings: Record<string, unknown>, rules: Record<string, unknown>) => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error("Profile name required");
      const id = crypto.randomUUID();
      setProfiles((prev) => {
        if (prev.some((p) => p.name === trimmed)) throw new Error("Duplicate profile name");
        return [...prev, { id, name: trimmed, settings, rules }];
      });
      setActiveId(id);
      return id;
    },
    [],
  );

  const update = useCallback(
    (id: string, patch: Partial<Pick<LocalProfile, "settings" | "rules">>) =>
      setProfiles((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p))),
    [],
  );

  const rename = useCallback(
    (id: string, name: string) =>
      setProfiles((prev) => prev.map((p) => (p.id === id ? { ...p, name: name.trim() } : p))),
    [],
  );

  const remove = useCallback((id: string) => {
    setProfiles((prev) => prev.filter((p) => p.id !== id));
    setActiveId((cur) => (cur === id ? null : cur));
  }, []);

  const activate = useCallback((id: string) => setActiveId(id), []);

  const active = profiles.find((p) => p.id === activeId) ?? null;

  return { profiles, active, create, update, rename, remove, activate };
}
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd web && npx vitest run src/hooks/useLocalProfiles.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useLocalProfiles.ts web/src/hooks/useLocalProfiles.test.ts
git commit -m "feat(web): localStorage-backed named settings profiles"
```

### Task 8: `useLocalFavorites` store (TDD)

**Files:**
- Create: `web/src/hooks/useLocalFavorites.ts`
- Test: `web/src/hooks/useLocalFavorites.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useLocalFavorites } from "./useLocalFavorites";

beforeEach(() => localStorage.clear());

describe("useLocalFavorites", () => {
  it("toggles players and persists, capped at 20", () => {
    const { result } = renderHook(() => useLocalFavorites());
    act(() => result.current.togglePlayer("p1"));
    expect(result.current.isFavoritePlayer("p1")).toBe(true);
    act(() => result.current.togglePlayer("p1"));
    expect(result.current.isFavoritePlayer("p1")).toBe(false);
    act(() => {
      for (let i = 0; i < 25; i++) result.current.togglePlayer(`x${i}`);
    });
    expect(result.current.players.length).toBeLessThanOrEqual(20);
  });

  it("caps teams at 4", () => {
    const { result } = renderHook(() => useLocalFavorites());
    act(() => ["BUF", "KC", "SF", "DAL", "PHI"].forEach((t) => result.current.toggleTeam(t)));
    expect(result.current.teams.length).toBeLessThanOrEqual(4);
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd web && npx vitest run src/hooks/useLocalFavorites.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement the store**

```ts
// web/src/hooks/useLocalFavorites.ts
import { useCallback, useEffect, useMemo, useState } from "react";

const KEY = "autotiers.favorites.v1";
const MAX_PLAYERS = 20;
const MAX_TEAMS = 4;

interface Favorites { players: string[]; teams: string[]; }

function load(): Favorites {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { players: [], teams: [] };
    const p = JSON.parse(raw) as Favorites;
    return { players: p.players ?? [], teams: p.teams ?? [] };
  } catch {
    return { players: [], teams: [] };
  }
}

export function useLocalFavorites() {
  const [fav, setFav] = useState<Favorites>(load);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(fav));
  }, [fav]);

  const togglePlayer = useCallback((id: string) => {
    setFav((prev) => {
      if (prev.players.includes(id)) return { ...prev, players: prev.players.filter((x) => x !== id) };
      if (prev.players.length >= MAX_PLAYERS) return prev;
      return { ...prev, players: [...prev.players, id] };
    });
  }, []);

  const toggleTeam = useCallback((abbr: string) => {
    setFav((prev) => {
      if (prev.teams.includes(abbr)) return { ...prev, teams: prev.teams.filter((x) => x !== abbr) };
      if (prev.teams.length >= MAX_TEAMS) return prev;
      return { ...prev, teams: [...prev.teams, abbr] };
    });
  }, []);

  const playerSet = useMemo(() => new Set(fav.players), [fav.players]);
  const teamSet = useMemo(() => new Set(fav.teams), [fav.teams]);

  return {
    players: fav.players,
    teams: fav.teams,
    isFavoritePlayer: (id: string) => playerSet.has(id),
    isFavoriteTeam: (abbr: string) => teamSet.has(abbr),
    togglePlayer,
    toggleTeam,
  };
}
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd web && npx vitest run src/hooks/useLocalFavorites.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useLocalFavorites.ts web/src/hooks/useLocalFavorites.test.ts
git commit -m "feat(web): localStorage-backed favorites store"
```

### Task 9: Rewire settings/rules panels to local profiles

**Files:**
- Modify: `web/src/components/SettingsPanel.tsx`, `web/src/components/RulesPanel.tsx`
- Modify: whatever component currently renders the server `ProfilePicker`/`ManageProfilesDialog`

- [ ] **Step 1: Replace the profiles data source**

Find current usage: `grep -rn "listProfiles\|createProfile\|activateProfile\|useProfiles\|ProfilePicker\|ManageProfilesDialog" web/src`.
Replace those calls/props with `useLocalProfiles()`. The active profile's
`settings`/`rules` seed the panels; on change, call `update(active.id, { settings, rules })`.
Provide a lightweight profile switcher (dropdown of `profiles`, "New", rename,
delete) inline — reuse existing panel styling; do not resurrect the server dialog.

- [ ] **Step 2: Typecheck + run web tests**

Run: `cd web && npx tsc -p tsconfig.json --noEmit && npx vitest run`
Expected: PASS (fix any references to deleted profile APIs).

- [ ] **Step 3: Commit**

```bash
git add web/src/components/SettingsPanel.tsx web/src/components/RulesPanel.tsx web/src
git commit -m "feat(web): drive settings/rules from local profiles"
```

### Task 10: Rewire favorites UI + client-side `is_favorite`

**Files:**
- Modify: `web/src/components/FavoritesPanel.tsx`, `web/src/components/FavoritesDialog.tsx`
- Modify: the tier/player rendering path that consumed server `is_favorite*`

- [ ] **Step 1: Back favorites UI with the local store**

Replace `useFavorites(authenticated)` usage with `useLocalFavorites()`. The star
toggles call `togglePlayer` / `toggleTeam`.

- [ ] **Step 2: Mark favorites client-side after generate**

Where player cards render (`grep -rn "is_favorite" web/src`), stop reading the
server field; instead compute from the store:
`const fav = isFavoritePlayer(player.id) || isFavoriteTeam(player.team)`.
Remove `is_favorite*` from `web/src/api/types.ts`.

- [ ] **Step 3: Typecheck + tests**

Run: `cd web && npx tsc -p tsconfig.json --noEmit && npx vitest run`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(web): favorites from localStorage, client-side is_favorite marking"
```

### Task 11: Delete account/link/auth frontend

**Files:**
- Delete: the components + api clients listed under "Web — delete"

- [ ] **Step 1: Remove components + API clients**

```bash
cd web
git rm src/components/AuthDialog.tsx src/components/EmailVerificationBanner.tsx \
  src/components/LinkedAccountsDialog.tsx src/components/LinkedLeagueChip.tsx \
  src/components/ManageProfilesDialog.tsx src/components/ProfilePicker.tsx \
  src/components/NoProfileBanner.tsx src/components/PasswordManagementSection.tsx \
  src/components/PasswordResetPanel.tsx \
  src/components/CbsConnectForm.tsx src/components/EspnConnectForm.tsx \
  src/components/NflConnectForm.tsx src/components/SleeperConnectForm.tsx \
  src/components/YahooConnectForm.tsx \
  src/api/auth.ts src/api/profiles.ts src/api/linkedLeague.ts src/hooks/useFavorites.ts
# favorites.ts: keep searchPlayers/batchPlayers, delete getFavorites/putFavorites
```
For `src/api/favorites.ts`, keep the `searchPlayers`/`batchPlayers` helpers
(used by favorites search) but delete `getFavorites`/`putFavorites`. Delete any
`AuthContext`/`useAuth` and its provider.

- [ ] **Step 2: Strip account/login from Header + menus**

In `Header.tsx` and `MobileProfileMenuItems.tsx` remove Sign-in/Account/Link-league
menu items and any `AuthDialog`/`LinkedAccountsDialog` triggers. Remove any
`EmailVerificationBanner`/`NoProfileBanner` renders from the app shell.

- [ ] **Step 3: Dangling-reference sweep + build**

```bash
cd web
grep -rn "AuthDialog\|LinkedAccounts\|ConnectForm\|useAuth\|AuthContext\|getFavorites\|listProfiles\|linkedLeague\|EmailVerification\|NoProfileBanner\|PasswordReset\|PasswordManagement" src
```
Expected: no matches. Then:
```bash
npx tsc -p tsconfig.json --noEmit && npm run build && npx vitest run
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A web
git commit -m "refactor(web): delete auth, account, and league-linking UI"
```

---

## Phase 3 — Destructive DB migration (authored now, run gated)

### Task 13: Alembic migration dropping account tables

**Files:**
- Create: `backend/alembic/versions/015_drop_account_tables.py`

- [ ] **Step 1: Find the current head revision(s)**

Run: `cd backend && venv/bin/python -m alembic heads`
There are two `014_*` files in `versions/` — if `heads` shows **two** heads,
first author a merge revision (`venv/bin/python -m alembic merge -m "merge heads" <rev1> <rev2>`)
and use its id as `down_revision`. Otherwise use the single head id.

- [ ] **Step 2: Write the migration**

```python
"""drop account/auth/linked-league/favorites/profiles tables

Revision ID: 015_drop_account_tables
Down revision: <HEAD_FROM_STEP_1>
"""
from alembic import op

revision = "015_drop_account_tables"
down_revision = "<HEAD_FROM_STEP_1>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Feedback keeps its rows; only the user linkage goes.
    with op.batch_alter_table("feedback") as batch:
        # Constraint name may differ — check `\d feedback` in prod first.
        batch.drop_constraint("feedback_user_id_fkey", type_="foreignkey")
        batch.drop_column("user_id")
        # submitter_email was captured from the user; drop if the model dropped it.
        batch.drop_column("submitter_email")

    # 2. Drop dependents before parents (FK-safe order).
    op.drop_table("linked_leagues")   # FK -> profiles
    op.drop_table("profiles")         # FK -> users
    op.drop_table("user_favorites")   # FK -> users
    op.drop_table("auth_tokens")      # FK -> users
    op.drop_table("users")


def downgrade() -> None:
    # Best-effort, data-less. Account data is unrecoverable after upgrade.
    raise NotImplementedError("irreversible teardown; restore from DB snapshot instead")
```
Verify the actual FK constraint name and any extra columns/indexes on these
tables (`grep -rn "ForeignKey\|Index" backend/app/models/*.py` before deleting
the models in Task 4 — capture names first, or read the earlier migrations
008–012 that created them).

- [ ] **Step 3: Test the migration against a scratch SQLite/Postgres DB**

```bash
cd backend
# Apply against a throwaway DB to prove upgrade runs clean:
DATABASE_URL="postgresql+asyncpg://...scratch..." venv/bin/python -m alembic upgrade head
```
Expected: upgrade completes; `\dt` shows the 5 tables gone and `feedback`
without `user_id`. Do this on a scratch DB, NOT prod.

- [ ] **Step 4: Commit (do not run on prod yet)**

```bash
git add backend/alembic/versions/015_drop_account_tables.py
git commit -m "feat(db): migration dropping account/auth/linked-league/favorites tables"
```

---

## Phase 4 — Terraform teardown (authored now, applied gated)

### Task 14: Remove SES + secrets from Terraform

**Files:**
- Modify: `infra/*.tf` (SES resources, Secrets Manager entries, ECS task-def wiring)

- [ ] **Step 1: Locate the resources**

```bash
grep -rn "aws_ses\|ses_\|ses:SendEmail\|jwt_secret\|fernet\|google_client\|yahoo_client\|smtp\|noreply" infra
```
Identify: SES domain identity, DKIM, verification DNS records, and the Secrets
Manager secrets for OAuth (google/yahoo), JWT, Fernet, and SES config, plus
their `secrets`/`valueFrom` entries in the ECS backend task definition.

- [ ] **Step 2: Remove the SES + secret resources and task-def wiring**

Delete the SES resources, the dead secret resources, and the corresponding
`valueFrom` entries in the backend container definition. Leave `manage_dns`,
ACM/TLS, Route53 zone, and the DB/CloudFront/ECS core untouched.

- [ ] **Step 3: Plan and review (DO NOT APPLY)**

```bash
cd infra && terraform plan -out=teardown.plan
```
Review the plan carefully. **It must show ONLY** SES resources + the listed
secrets + task-def revision being destroyed/updated — NOT route53 zone records
(beyond SES verification records), ACM certs, the ALB, or the DB. If the plan
proposes destroying DNS/TLS/domain resources, STOP — the `manage_dns`/ACM guard
(see memory `project_tfstate-s3-bootstrap-pending`) is being tripped; fix
before proceeding.

- [ ] **Step 4: Commit the Terraform changes (still not applied)**

```bash
git add infra
git commit -m "infra: remove SES and OAuth/JWT/Fernet secrets (plan only, not applied)"
```

---

## Phase 5 — Execution gate (human-approved prod changes)

### Task 15: Apply migration + Terraform on prod

> **HUMAN GATE:** Do not run any step in this task without an explicit go from
> the user in the current session. These changes are irreversible on prod data
> and infrastructure. Take a DB snapshot first.

- [ ] **Step 1: Snapshot the prod DB** (RDS/Aurora manual snapshot) and confirm it completed.

- [ ] **Step 1a: Reconcile the alembic chain on prod BEFORE upgrading (do not blind-`upgrade head`).**
  The repo previously had a duplicate `revision="014"` on two files; this branch
  linearized them to `014` → `014a`. Prod's `alembic_version` likely records
  `"014"`. Inspect prod first:
  - `SELECT version_num FROM alembic_version;`
  - Check whether BOTH column sets already exist:
    `\d player_stats` (expect `first_down_rush`/`first_down_rec` from the file
    now numbered `014a`) and `\d players` (expect `draft_round`/`draft_pick`
    from `014`).
  - If prod is at `014` and the `014a` columns already exist (old single-file
    behavior applied them), a plain `upgrade head` will try to re-add existing
    columns and error. In that case `alembic stamp 014a` first, then
    `upgrade head` (which then runs only `015`).
  - If the `014a` columns are genuinely MISSING (only one of the old dup-014
    files actually applied), let `upgrade head` apply `014a` then `015`.
  Decide based on the actual inspected schema — do not assume.

- [ ] **Step 1b: Verify the feedback FK name before running 015.**
  `015` drops `feedback_user_id_fkey` (Postgres default auto-name, inferred
  from `012_feedback.py` which used an unnamed inline FK). Confirm on prod with
  `\d feedback`; if the actual constraint name differs, edit the migration to
  match before running.

- [ ] **Step 2: Run the migration on prod**

Follow the repo's existing migration-run path (see memory
`project_deploy-migrate-taskdef-trap` — historically migrations were run via a
`run-task` against a migrate task-def that was never applied; use the
established working mechanism, e.g. exec into the backend task or the CI migrate
step). Run `alembic upgrade head`. Verify the 5 tables are gone.

- [ ] **Step 3: Apply Terraform**

```bash
cd infra && terraform apply teardown.plan
```
Confirm only SES + secrets + task-def changed; DNS/TLS/domain intact.

- [ ] **Step 4: Force a new backend deployment**

The task def no longer references the deleted `valueFrom` secrets; force the
service to roll onto the new revision so the running task stops resolving them
(see memory `project_secrets-rotation-ecs` and `project_cors-oauth-regression-incident`
— `force-new-deployment` alone won't pick a new task-def rev when
`ignore_changes=[task_definition]`; deploy the explicit new revision).

- [ ] **Step 5: Smoke test prod**

- Load the site anonymously; set league settings; generate tiers; export.
- Confirm settings + favorites persist across reload (localStorage).
- Confirm `/api/feedback` returns 202 and persists (admin read via `X-Api-Key`).
- Confirm no 5xx from removed endpoints; `/api/data/status` healthy.

- [ ] **Step 6: Final branch integration**

Use `superpowers:finishing-a-development-branch` to open the PR / merge.

---

## Self-review notes

- **Spec coverage:** backend removal (Tasks 1,4,5,6), generate decouple (2),
  feedback persist-only (3), localStorage profiles (7,9) + favorites (8,10),
  frontend removal (11), migration (13), Terraform+secrets (14), gated apply
  (15). All spec sections mapped.
- **Kept-not-deleted:** `auth/admin.py`, `data/sources/`, scheduler, engine —
  explicitly called out to prevent over-deletion.
- **Known unknowns flagged inline** (not placeholders): exact test file names
  (grep given), exact `feedback` FK constraint name (verify against prod),
  alembic head id (two `014`s → `alembic heads` + possible merge), `frontend_url`
  fate (grep-gated), `rate_limit.py` fate (grep-gated). Each has a concrete
  command to resolve at execution time.
