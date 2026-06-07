---
name: autotiers-bug-classes
description: Catalogue of bug classes that have actually reached AutoTiers users, with concrete recipes for detecting each before shipping. Invoke when reviewing a non-trivial change — the QA agent uses this to probe the categories most likely to fail in practice.
---

# Bug classes we've shipped

Every entry below is a real bug that reached the user. Use these as the QA checklist — for each change, ask whether the new code could fail in any of these ways.

## 1. Misleading error copy

**Canonical case:** `web/src/components/AuthDialog.tsx` once said *"Email may already be in use, or password may be too short (min 10 chars)"* on ANY signup failure. A user with a perfectly valid 16-char password was told their password was too short — the real cause was a 409 (email already used). The fix added a `describe()` helper that unpacks the FastAPI `{detail: ...}` shape; see the same file for the current pattern.

**How to detect during review:**
- Read every user-facing string that appears in an error path. The frontend lives in `web/src/components/`; backend `HTTPException(detail=...)` strings in `backend/app/api/`.
- For each one, list the conditions that trigger it. If it claims a specific cause ("password too short") but actually fires for multiple causes, that's a bug.
- Prefer surfacing the backend's actual error detail over hand-crafted messages. The `_provider_http_error` helper in `backend/app/api/linked_league.py` is the reference pattern for structured upstream errors.

## 2. Empty / blank validation gap

**Canonical case:** `post_espn` in `backend/app/api/linked_league.py` once accepted an empty body and persisted a `LinkedLeague` row with no `league_id`, no SWID, no `espn_s2`. The UI reported "linked." The fix added an explicit guard rejecting bodies that have neither a league_id nor both cookies.

**How to detect:**
- For each connect-form-style endpoint (`/link/sleeper`, `/link/espn`, `/profiles`, `/auth/signup`), submit with every required field blank. Does the backend persist anything? If yes, that's likely a bug.
- Submit with whitespace-only strings — they pass `min_length` checks because they have non-zero length but mean nothing semantically.
- The frontend pair of this validation: `EspnConnectForm`'s `disabled={busy || (leagueId.trim() === "" && (!isPrivate || swid.trim() === "" || espnS2.trim() === ""))}`. Frontend and backend validation must agree.

## 3. Identity / session loss → phantom account

**Canonical case:** `yahoo_callback` / `google_callback` in `backend/app/api/auth.py`. While linking from inside the app, if the `autotiers_session` cookie failed the OAuth round-trip, the callback resolved `current_user` to `None` and fell through to the sign-in branch — silently creating a brand-new user and orphaning the original (Sleeper-linked) account.

The fix introduced an `intent=link` query param + `autotiers_oauth_intent` cookie. When intent is `"link"` and `current_user` is `None`, the callback now redirects with `?linking_error=session_lost` instead of creating an account. Use this pattern for any future OAuth providers.

**How to detect:**
- For any OAuth or session-bearing flow, ask: "What happens if `current_user` is None?" Read `_resolve_user` in `backend/app/auth/dependencies.py` to see the failure modes.
- If the answer is "create a new user," that's likely wrong for the link path. Linking must distinguish from sign-up via `intent=link` and an intent cookie.
- Reproduce by deleting the `autotiers_session` cookie in DevTools before clicking Connect. See `autotiers-flow-fixtures` for the manual reproduction steps. After Yahoo bounces back you should land on `?linking_error=session_lost`, not be silently signed in as a new account. Verify via psql: no new row in `users` for the Yahoo subject you just signed in with.

## 4. Third-party library defaults

**Canonical case:** `backend/app/integrations/espn.py` rejected all private-league connects. Two unverified assumptions:
1. httpx's default `python-httpx/0.x` User-Agent triggered ESPN's bot-block (302 to login).
2. Passing `cookies={...}` to `httpx.AsyncClient` URL-encoded the curly braces in SWID. ESPN compared raw bytes and rejected the encoded value.

The fix in that file builds the `Cookie:` header by hand and sends a Chrome `User-Agent`. Mirror the pattern for any future provider that needs cookies.

**How to detect:**
- For any new HTTP call in `backend/app/integrations/` or `backend/app/data/sources/`, look up: what User-Agent does httpx send by default? Does it follow redirects (`AsyncClient(follow_redirects=...)`)? How does the cookies arg encode special characters? What's the default timeout (currently `10.0` in our clients)?
- Don't trust "it works in the test." `respx` test mocks don't enforce header parity; production servers do.
- For frontend `fetch`, watch the implicit `credentials` default (`same-origin`). Our `apiFetch` in `web/src/api/client.ts` overrides it to `include`; if you copy that helper, verify the override carried over.

## 5. Persistence / migration gaps

**Canonical case:** `backend/alembic/versions/006_linked_leagues.py` originally used the long-form revision id `"006_linked_leagues"`. The repo convention is short numeric (`"001"` through `"007"` — see other files in the directory). Alembic couldn't resolve the chain and the `autotiers-api` container failed at startup with `KeyError: '005_user_google_subject'`.

**How to detect:**
- For any new Alembic migration: open existing migrations in `backend/alembic/versions/` and verify the `revision = "..."` line uses the same convention. Currently `"NNN"` (zero-padded numeric). Filename can be descriptive (`007_linked_league_optional_league.py`) but the revision string must be just the number.
- Run `cd backend && venv/bin/alembic upgrade head` against the dev DB and confirm it applies cleanly.
- For any NOT NULL → nullable transition: write a `downgrade()` that backfills before re-adding NOT NULL. Migration 007 is the reference example.
- For new tables: confirm the SQLAlchemy model uses `JSONB().with_variant(JSON(), "sqlite")` for any JSON column — bare JSONB breaks the SQLite test engine.

## 6. UI inconsistency

**Canonical case:** `LinkedLeagueSection` in `web/src/components/LinkedLeagueSection.tsx` collapsed to just the connected row when a league was linked, hiding Sleeper / NFL Fantasy / CBS. Users couldn't switch providers or see what was coming soon. The fix moved to "always render all four rows, swap each row's action based on whether it's the linked one."

**How to detect:**
- Components in `web/src/components/` that toggle on a state variable (`activeForm`, `linked`, `step`) should be inspected for what they hide. Are the alternatives still reachable?
- For each rendered state of the changed component, mentally list every interactive affordance. Compare across states. A row that exists in state A but not state B is suspicious.
- Adjacent features should re-evaluate consistently. If `Refresh` is hidden when there's no league (`linked.league_id` check), `Disconnect` should also re-check what makes sense in that state.

## 7. Test sincerity

**Canonical case:** a test had `expect(getAllByText(/coming soon/i)).toHaveLength(2)` but the production change moved one of those rows behind a state branch the test never triggered. The test still passed because it counted text occurrences in the wrong state.

**Second case (weak-bound assertions):** the customizable-tier-count PR (#170) shipped tests asserting `max_tier >= 10` for a `overall_tier_count=15` run and `max_tier <= 5` for a 5-player pool. Both passed even when the new parameter was bypassed — `>= 10` still holds if the count silently falls back to the old hardcoded 10, and `<= 5` still holds if dedup over-collapses to fewer tiers. QA noticed the gap but logged it as a non-blocker; a reviewer caught it post-QA. The fix asserted the **exact** expected set (`tiers == set(range(1, 16))`, `tiers == {1,2,3,4,5}`).

**How to detect:**
- For each test in the diff, mentally delete the production change and ask: would this test still pass? If yes, the test isn't sincere.
- **Distrust open-ended bound assertions** (`>=`, `<=`, `>`, `<`, "at least N", `len(x) <= k`) on a value the change is supposed to control. They pass for a whole *range* that includes the bypassed-behaviour value. When a test exists to prove a parameter is *honored*, assert the exact value or the exact set it should produce, not a bound the old/broken behaviour also satisfies.
- For new `if/else` or `try/except`, both branches need a test that fails when the branch is deleted.
- Treat a weak-bound assertion on the feature-under-test as a **blocker**, not a non-blocker — this one slipped to an external reviewer precisely because it was deferred.
- Coverage tools confirm the line executed; only inspection confirms the test actually verified behaviour.

## 8. Git hygiene

**Canonical case:** `git add backend/ web/src/` accidentally staged the entire `backend/venv312/` directory. 5664 files in one commit. Required a force-push and a clean re-do.

The fix updated `backend/.gitignore` to include `venv*/` and `coverage.xml` (read that file before deciding what's safe to stage).

**How to detect:**
- Before EVERY commit, run `git status` and inspect every file listed.
- Never `git add -A` or `git add .` or `git add <directory>`. Stage explicit paths (`git add backend/app/api/auth.py backend/tests/test_yahoo_oauth.py ...`).
- If staging a directory is unavoidable, run `git status --short --untracked-files=all <path>` first to verify nothing surprising is inside.
- Reject any commit larger than 50 files unless every file was deliberately staged.
- Known never-commit paths in this repo: `backend/venv/`, `backend/venv*/`, `backend/coverage.xml`, `backend/.coverage`, `backend/__pycache__/`, `web/node_modules/`, `web/.vite/`, `.claire/` (editor scratch), `.claude/worktrees/` (worktree state).

## Probe order (for the QA agent)

When reviewing a change, walk these in this order:

1. Test sincerity (does the test really test what it claims?)
2. Git hygiene (is anything staged that shouldn't be?)
3. Validation gaps (what happens with empty/blank/null inputs?)
4. Misleading copy (does every error string accurately name its cause?)
5. Library defaults (does any new HTTP call or library usage assume an unverified default?)
6. Identity / session (what happens when current_user is None mid-flow?)
7. Persistence / migration (will this survive a DB restart, an Alembic chain, an FK cascade?)
8. UI inconsistency (do all states show consistent affordances?)

If a category clearly doesn't apply to the change, say so explicitly with reasoning. Don't skip silently.
