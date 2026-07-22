# Strip Accounts, League Linking, and SES — Design

**Date:** 2026-07-21
**Status:** Approved (design), pending implementation plan
**Author:** AutoTiers team

## Goal

Ship a launch-ready v1 that drops per-user accounts, league-account linking,
and transactional email. Users interact anonymously: they set their league
settings by hand, generate tiers, and export. This shrinks the database,
removes the SES dependency (and its cost), and cuts the OAuth surface.

## Decisions (locked)

1. **Manual settings + favorites live in browser `localStorage`.** No accounts,
   no server-side user/profile/favorites tables. Named profiles are preserved
   as a client-only feature.
2. **Full teardown in one initiative:** app code, a destructive DB migration
   dropping the account tables, and prod infra (SES + OAuth/SES secrets).
   The migration and `terraform apply` are **irreversible on prod** and run
   only behind an explicit human go at execution time.
3. **Feedback is kept as persist-only.** The row is retained (still useful),
   `user_id` is removed, and the SES email notification is dropped. Admins
   read feedback through the existing `X-Api-Key`-gated route.

## Scope

### Backend — remove

- **Routers/APIs** (unregister in `main.py`, delete files):
  `api/auth.py`, `api/linked_league.py`, `api/profiles_api.py`,
  `api/favorites_api.py`.
- **`auth/`:** delete `jwt.py`, `google.py`, `yahoo.py`, `hashing.py`,
  `email_dep.py`, `dependencies.py`. **Keep `auth/admin.py`** (shared ops
  `X-Api-Key` gate — not a personal account). Keep `auth/rate_limit.py` only
  if still referenced by a kept endpoint; otherwise delete.
- **`email/`:** delete the whole package (`sender.py`, `fake_sender.py`,
  `ses_sender.py`, `templates.py`, `__init__.py` / `make_email_sender`).
- **`integrations/`:** delete the whole package (`sleeper.py`, `espn.py`,
  `cbs.py`, `yahoo_fantasy.py`, `nfl.py`, `scoring_mappers.py`, `types.py`).
  These are the *league-import* clients driven by a user's linked account.
- **Models:** delete `user.py`, `auth_token.py`, `linked_league.py`,
  `profile.py`, `user_favorites.py`. Update `models/__init__.py`.
- **`security/fernet.py`:** delete — only used to encrypt linked-league creds.
- **Schemas:** delete `schemas/auth.py`, `schemas/profile.py`,
  `schemas/favorites.py`, `schemas/linked_league.py`.

### Backend — keep / adjust

- **`data/sources/` public ingest is untouched.** Sleeper (player table +
  cross-IDs), `nfl_data`, `fantasypros`, and the `cbs` scraper require no
  login and power the tier engine. The scheduler and `DataFetcher` stay as-is.
  (These are distinct from the deleted `integrations/` league-import clients.)
- **`/generate`:** remove the `current_user: Optional[User]` dependency and the
  `UserFavorites` / `User` imports; the endpoint is always anonymous. The
  server no longer computes or returns `is_favorite*` flags — the client
  derives them from localStorage after the response. Remove the favorites
  fields from `GenerateResponse`/`TieredPlayerOut` (or keep the fields but
  always `None`; prefer removal for a smaller contract — confirm in the plan).
- **Feedback:** keep `api/feedback.py` + `models/feedback.py`. Drop the
  `user_id` column and its FK to `users`; make submission fully anonymous.
  Rate-limit by client IP only. Remove the `EmailSender` dependency and the
  notification send — the endpoint just persists the row.
- **`config.py`:** strip settings that only served removed subsystems — OAuth
  client id/secret/redirect (google + yahoo), JWT secret, SES/email config,
  Fernet key, and `frontend_url` if only used by email links / OAuth redirects.
  Keep `admin_api_key`, `CORS_ORIGINS`, DB, and data-source settings.

### Frontend — remove

Delete these components and any imports/tests:
`AuthDialog`, `EmailVerificationBanner`, `LinkedAccountsDialog`,
`LinkedLeagueChip`, `ManageProfilesDialog` (server version), `ProfilePicker`
(server version), `NoProfileBanner`, `PasswordManagementSection`,
`PasswordResetPanel`, and every `*ConnectForm` (`Cbs`, `Espn`, `Nfl`,
`Sleeper`, `Yahoo`).

Remove account/login/link entries from `Header`, `MobileProfileMenuItems`, and
any settings menus. Remove the API client calls to the deleted endpoints.

### Frontend — localStorage stores

- **`useLocalProfiles`:** a client-only store of named profiles
  `{ name, settings, rules }` persisted to `localStorage`, replacing the server
  profiles API. `SettingsPanel` / `RulesPanel` read and write the active
  profile. Provide create / rename / delete / switch. A reworked local profile
  picker (no account concept) selects the active one.
- **`useLocalFavorites`:** a client-only set of favorite player ids + team
  abbreviations persisted to `localStorage`, replacing the server favorites
  API. `FavoritesPanel` / `FavoritesDialog` are kept but backed by this store.
  After `/generate` returns, the client marks `is_favorite` badges by
  intersecting results with the local favorites set.
- Caps (existing: 20 players, 4 teams) enforced in the store.

### Database migration (destructive, gated)

One Alembic migration that, in FK-safe order:

1. Drops `feedback.user_id` (and its FK constraint) — leaves feedback intact.
2. Drops `profiles` (→ cascades to `linked_leagues`), `user_favorites`,
   `auth_tokens`, then `users`.

The downgrade path is best-effort table recreation without data (data is
unrecoverable). **This migration is irreversible on prod data and runs only
after explicit human approval at execution time.**

### Infrastructure / Terraform (gated apply)

- Remove SES resources: domain identity, DKIM records, verification DNS
  records, and any sandbox/production-access-related config.
- Remove secrets no longer read by the app: Google + Yahoo OAuth client
  id/secret, JWT secret, SES/email config, Fernet key. Remove their
  `valueFrom` wiring from the ECS task definition.
- **Guard the DNS/TLS trap** (see project memory
  `project_tfstate-s3-bootstrap-pending`): confirm `manage_dns` / ACM stay
  intact so removing SES does not cascade into route53 / TLS / domain
  destruction. Review the full `terraform plan` before any apply.
- After the task-def secret wiring changes, the backend service needs a
  new task-def revision + force-new-deployment to stop referencing deleted
  secrets (see `project_secrets-rotation-ecs`).

## Non-goals

- No re-introduction of any auth in a different form (anonymous tokens, etc.).
- No changes to the tier math, scoring engine, or public data ingest.
- No new persistence backend for settings beyond `localStorage`.

## Testing

- **Delete** backend suites for auth, OAuth, linked-league, profiles, favorites.
- **Update** `/generate` tests: drop authenticated-favorites cases; keep and
  extend the anonymous path. Reuse `_GENERATE_BODY` (see memory
  `feedback_ci_test_bodies`) to avoid 422s on CI.
- **Update** feedback tests: anonymous-only submission, no email side effect.
- **Add** frontend (vitest) tests for `useLocalProfiles` and
  `useLocalFavorites` (persistence, caps, switching, favorites badge marking).
- Run pytest via the worktree venv at `backend/venv` (not `.venv`); avoid the
  full-suite OOM per `autotiers-test-running`.

## Sequencing

1. Backend code removal + `/generate` decouple + feedback fix. Tests green.
2. Frontend removal + localStorage stores. vitest + tsc green.
3. Alembic migration authored + reviewed (not run on prod).
4. Terraform + secrets teardown authored; `terraform plan` reviewed
   (not applied).
5. **Execution gate:** explicit human go → run the migration and
   `terraform apply` on prod, then force-new-deployment on the backend.

## Risks & mitigations

- **Irreversible prod changes** (migration + SES/secret destroy): staged last,
  behind an explicit go, with `plan`/migration SQL reviewed first.
- **Terraform DNS/TLS cascade** when removing SES: verify plan touches only SES
  + secret resources; `manage_dns`/ACM untouched.
- **Stale secret references** post-teardown: force a new backend deployment so
  the running task stops resolving deleted `valueFrom` secrets.
- **Hidden couplings** to deleted modules (imports elsewhere): rely on
  `tsc`, `pytest` collection, and a grep sweep for dangling imports before
  claiming done.
