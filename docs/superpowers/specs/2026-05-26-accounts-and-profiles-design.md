# Accounts and Profiles Design

**Date:** 2026-05-26
**Status:** Approved

## Summary

Add user accounts to AutoTiers. The current anonymous flow is the default and stays unchanged — users can interact fully without an account. Authenticated users gain the ability to save up to **5 named profiles**, each capturing the full configuration of the Settings and Rules panels.

Auth supports two paths: **email + password**, and **Yahoo OAuth** (chosen over Google because the user base skews toward fantasy-football platforms, and Yahoo's OAuth is an explicit v2 hook into pulling actual league settings).

Email-based flows (verification, password reset) are explicitly **deferred** for v1.

## Goals

- Anonymous users keep the existing UX with zero friction added
- Authenticated users can save and switch between up to 5 named configurations
- Auto-save commits edits to the active profile so users never lose work
- Authentication stack is simple enough for a single maintainer to operate without ongoing email/SMTP costs

## Non-goals (explicit YAGNI for v1)

- Email verification on signup
- Password reset email
- Google OAuth (Yahoo is chosen instead for this audience)
- Refresh tokens
- Multi-factor authentication
- Password change while logged in
- Account deletion endpoint (workaround: contact maintainer)
- Sharing profiles between users
- Linking an email/password account with a Yahoo OAuth account
- Yahoo Fantasy data import (a great v2 hook, not v1 scope)
- Profile reordering (sorted by `last_used_at`)
- Admin / user roles
- Audit log of profile changes
- Concurrent-edit conflict resolution beyond last-write-wins

---

## Architecture

### Data model

Two new tables. Both use UUID primary keys.

```sql
users
  id                       uuid PK
  email                    text UNIQUE NULLABLE  -- NULL when Yahoo-only account
  password_hash            text NULLABLE         -- NULL when OAuth-only account; argon2id
  yahoo_subject            text UNIQUE NULLABLE  -- Yahoo's `sub` claim
  created_at               timestamptz NOT NULL
  last_active_profile_id   uuid NULLABLE FK -> profiles.id

profiles
  id            uuid PK
  user_id       uuid NOT NULL FK -> users.id ON DELETE CASCADE
  name          text NOT NULL
  settings_json jsonb NOT NULL
  rules_json    jsonb NOT NULL
  created_at    timestamptz NOT NULL
  updated_at    timestamptz NOT NULL
  UNIQUE (user_id, name)
```

The 5-profile cap is enforced at the API layer (`COUNT(*) WHERE user_id = ?` before insert), not as a DB constraint. Cascade delete on user removal.

### Profile payload shape

```jsonc
// settings_json
{
  "scoring_format": "ppr",
  "league_size": 12,
  "draft_rounds": 15,
  "qb_td_points": 4,
  "bonus_100yd_rushing": false,
  "bonus_100yd_receiving": false,
  "bonus_first_downs": false,
  "weights": { "prior": 30, "consensus": 70 }
}

// rules_json — only user-mutable fields per rule
[
  { "name": "RB Committee Penalty", "enabled": true, "weight": 1.0 },
  { "name": "Red Zone Usage Premium", "enabled": false, "weight": 1.5 },
  ...
]
```

Built-in rule definitions (conditions, effects, descriptions) come from the backend on every render. Profiles store only the user's toggles and magnitudes so a built-in rule edit ships to every profile automatically.

---

## Authentication

### Email + password

**`POST /api/auth/signup`** — Body `{ email, password }` plus optional client state (current settings + rules).
- Validates email format and password ≥ 10 characters
- Hashes password with `argon2-cffi` (argon2id)
- Inserts `users` row
- If anonymous state was supplied in the body, creates the first `profiles` row named `"My setup"` in the same transaction and sets it as `last_active_profile_id`
- Sets the JWT cookie and returns the user

**`POST /api/auth/login`** — Body `{ email, password }`.
- Argon2 verify
- Sets JWT cookie and returns the user + profile list + active id
- Rate-limited at **5 failures per email per 15 minutes** (in-memory bucket; Redis-ready later)

**`POST /api/auth/logout`** — Clears the cookie. No server-side session to invalidate.

**`GET /api/auth/me`** — Returns user + profiles + active id, or 401 if unauthenticated.

### Yahoo OAuth

**`GET /api/auth/yahoo/authorize`** — Builds Yahoo's auth URL with a random `state` (stored in a short-lived cookie for CSRF), redirects the user to Yahoo.

**`GET /api/auth/yahoo/callback`** — Validates state, exchanges the code for tokens, fetches `sub` from Yahoo's userinfo endpoint.
- First-time: creates a `users` row with `yahoo_subject` only. **Email is intentionally not pulled from Yahoo** — see "Email-collision avoidance" below.
- Returning: looks up by `yahoo_subject`
- Sets the JWT cookie and redirects back to the frontend
- **Yahoo access/refresh tokens are not stored** in v1 — Yahoo is used solely for identity. v2 may persist them to pull Yahoo Fantasy data.

### Email-collision avoidance

`users.email` is populated **only** by the email/password signup path. Yahoo accounts have `email = NULL`. This eliminates the takeover vector where a Yahoo account at `alice@example.com` could match an existing email/password account at the same address. The two identifier columns (`email`, `yahoo_subject`) are independent and never need to be reconciled.

A user who wants both auth methods on one account will have to wait until v2 ships a "link account" flow. In v1 they're separate accounts.

### JWT and session

- Signed HS256 with a 32-byte secret from `JWT_SECRET` env var
- Cookie: `HttpOnly`, `Secure` in prod, `SameSite=lax`, `Path=/`, 30-day Max-Age
- Sliding renewal on each authenticated request (re-issue with fresh 30d expiry)
- Stateless — rotating `JWT_SECRET` invalidates all sessions (acceptable trade-off for v1)
- Frontend never touches the token directly. `withCredentials: true` on fetch handles the cookie.

---

## Profile API

All routes require auth (return 401 otherwise):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/profiles` | List the user's profiles + active id |
| `POST` | `/api/profiles` | Create a profile (409 if already 5) |
| `PATCH` | `/api/profiles/{id}` | Update name / settings_json / rules_json |
| `DELETE` | `/api/profiles/{id}` | Delete |
| `POST` | `/api/profiles/{id}/activate` | Set as `last_active_profile_id` |

Cross-user access returns 403. Deletion is allowed even when it's the user's only profile — they'll fall back to running anonymously until they create a new one or switch.

---

## Frontend

### Hamburger menu

A `lucide-react` `Menu` icon in the `Header` component on the right side, opening a shadcn `DropdownMenu`.

**Logged-out menu:**
```
[Menu ▼]
  Log in
  Sign up
```

**Logged-in menu:**
```
[Menu ▼]
  user@example.com    (greyed, not clickable)
  ───
  Profiles ▶          (submenu: list of 5, active checkmarked, "Manage…")
  ───
  Log out
```

### Login modal

A shadcn `Dialog` with two tabs (`Log in` / `Sign up`) and a Yahoo button:

```
┌──────────────────────────────────┐
│  Log in   │   Sign up            │
├──────────────────────────────────┤
│  Email     [___________________] │
│  Password  [___________________] │
│                                  │
│           [ Log in ]             │
│                                  │
│  ── or ──                        │
│                                  │
│  [ Continue with Yahoo ]         │
└──────────────────────────────────┘
```

The Yahoo button navigates to `/api/auth/yahoo/authorize`. The modal stays open with a spinner until the redirect lands. On return, `useMe()` re-fetches and the modal closes.

### Profile picker

Lives in the Header next to the hamburger:

```
Profile: My Setup ▼          [Reset to saved]   [• Saving…]
        └─ My Setup ✓
           PPR 12-team
           Standard Keeper
           + New profile
           Manage profiles…
```

- `Reset to saved` only renders when local state differs from `lastSavedSnapshot`
- The chip toggles between `Saved` / `Saving…` / `Unsaved` based on diff
- `+ New profile` is disabled (with tooltip) when the user has 5

### Manage profiles modal

A list view with inline rename, delete with confirm. No reordering for v1 — profiles sort by `last_used_at` descending.

### Anonymous flow

Unchanged from current. The hamburger menu replaces the existing right-side area in the Header. Anonymous users see only Login / Sign up entries. On signup, their current in-browser state is sent as the request body and becomes the new account's first profile named `"My setup"`.

### Auto-save behavior

- A debounced effect (800ms idle) watches `settings` and `rules` state
- When (a) authenticated and (b) a profile is active, fires `PATCH /api/profiles/{activeId}` with the deltas
- An in-memory `lastSavedSnapshot` tracks the server's view; the chip reflects diff status
- On profile switch: PATCH any pending dirty state first (best-effort), then `POST /activate`, then `GET /api/profiles/{newId}` and hydrate

**Conflict handling:** Last-write-wins. If two tabs are open, the most recent PATCH overwrites the older. Acceptable for v1.

### New frontend modules

- `src/api/auth.ts` — `signup`, `login`, `logout`, `getMe`, `yahooAuthorizeUrl`
- `src/api/profiles.ts` — `listProfiles`, `createProfile`, `updateProfile`, `deleteProfile`, `activateProfile`
- `src/contexts/AuthContext.tsx` — exposes `user`, `profiles`, `activeProfile`, mutations
- `src/components/Header.tsx` — gains hamburger + profile picker
- `src/components/AuthDialog.tsx` — login + signup modal
- `src/components/ProfilePicker.tsx` — dropdown + manage modal trigger
- `src/components/ManageProfilesDialog.tsx` — rename / delete
- `src/hooks/useAutoSave.ts` — debounced PATCH effect

---

## Security

- **Password hashing:** argon2id via `argon2-cffi`, low-memory profile (sufficient for our scale)
- **JWT:** HS256, 32-byte secret in `JWT_SECRET`. Rotation invalidates all sessions
- **Cookie:** `HttpOnly`, `Secure` (prod), `SameSite=lax`, 30-day Max-Age, sliding renewal
- **CORS:** Restrict `Access-Control-Allow-Credentials: true` to pinned origins in prod
- **CSRF:** SameSite=lax + JSON-only POST bodies. Add double-submit token if we ever serve cross-origin forms
- **Rate limit:** in-memory IP+email bucket on `/login` (5 / 15min). Redis-backed in a future PR
- **Yahoo OAuth state:** random `state` cookie validated on callback (CSRF protection)
- **Password validation:** min 10 characters, no other constraints (per OWASP 2024 — length is the only rule that helps; composition rules don't)

---

## Testing

### Backend (pytest)

- **`test_auth.py`**
  - signup happy path
  - duplicate email rejection
  - password too short
  - wrong-password login fails
  - correct-password login succeeds
  - rate-limit triggers after 5 fails
  - signup with anonymous state creates `"My setup"` profile in the same transaction
  - JWT cookie set on login

- **`test_yahoo_oauth.py`** (respx-mocked)
  - `/authorize` returns redirect with state cookie
  - `/callback` rejects on bad state
  - `/callback` rejects on bad code
  - `/callback` creates user on first auth
  - `/callback` finds existing user on repeat auth

- **`test_profiles.py`**
  - list returns user's own only
  - create rejects when at 5
  - PATCH updates fields
  - DELETE cascades correctly
  - activate sets `last_active_profile_id`
  - all endpoints 401 without auth
  - all endpoints 403 when accessing another user's profile

### Frontend (vitest + MSW)

- **`AuthDialog.test.tsx`** — tab switch, login submits credentials, signup sends current state for migration, Yahoo button navigates to authorize URL
- **`ProfilePicker.test.tsx`** — renders active profile, switching loads new state, "+ New profile" creates from current state, disabled when at 5
- **`useAutoSave.test.ts`** — debounce timing, dirty indicator transitions saved → saving → saved, "Reset to saved" reverts
- **`ManageProfilesDialog.test.tsx`** — rename updates list, delete confirms

Coverage target: maintain the existing 80% diff-coverage threshold (CI workflow enforces).

---

## Migration & rollout

- Alembic migration `004_users_and_profiles.py` creates both tables
- `JWT_SECRET` and Yahoo OAuth env vars (`YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REDIRECT_URI`) added to `.env.example` and Railway config
- `argon2-cffi` added as a backend dependency
- No data migration required — existing anonymous users keep working as-is

---

## Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Auth method | Email/password + Yahoo OAuth | User chose; Yahoo over Google for the fantasy audience |
| Profile scope | Settings + rules (full snapshot) | One source of truth per profile; no hybrid boundary confusion |
| Anonymous → signup | Auto-save current state as `"My setup"` | Don't make users lose their tweaks |
| Save behavior | Auto-save + "Reset to saved" button | Best UX, debounced 800ms |
| Email flows | Defer all of them | No SMTP provider needed for v1 |
| OAuth provider | Yahoo (ESPN has no public OAuth) | Fantasy-football alignment + v2 league-import hook |
| Profile cap behavior | Block create when at 5, force delete | Simpler than auto-evict |
| Profile reordering | None; sort by `last_used_at` | Pure YAGNI |
| Concurrent edits | Last-write-wins | Single-user-with-multiple-tabs is rare; not worth conflict UI |
