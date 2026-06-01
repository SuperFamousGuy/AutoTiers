---
name: autotiers-bug-classes
description: Catalogue of bug classes that have actually reached AutoTiers users, with concrete recipes for detecting each before shipping. Invoke when reviewing a non-trivial change — the QA agent uses this to probe the categories most likely to fail in practice.
---

# Bug classes we've shipped

Every entry below is a real bug that reached the user. Use these as the QA checklist — for each change, ask whether the new code could fail in any of these ways.

## 1. Misleading error copy

**Canonical case:** signup form said *"Email may already be in use, or password may be too short (min 10 chars)"* on ANY signup failure. A user with a perfectly valid 16-char password was told their password was too short — the real cause was a 409 (email already used).

**How to detect during review:**
- Read every user-facing string that appears in an error path.
- For each one, list the conditions that trigger it. If it claims a specific cause ("password too short") but actually fires for multiple causes, that's a bug.
- Prefer surfacing the backend's actual error detail over hand-crafted messages.
- Backend errors must also be specific. `"Connection failed"` tells the user nothing; `"ESPN returned HTTP 502 — try again"` tells them what to do.

## 2. Empty / blank validation gap

**Canonical case:** the ESPN connect form succeeded with empty league ID, no SWID, no espn_s2. The backend wrote a row with literally no useful data and the UI reported "linked."

**How to detect:**
- Submit the form with every required field blank. Does the backend persist anything? If yes, that's likely a bug.
- Submit with whitespace-only strings (often pass `min_length` checks because they have non-zero length).
- For each new endpoint that accepts an optional field, ask: "What's the minimum information that should still produce a successful linkage?" Reject below that minimum.

## 3. Identity / session loss → phantom account

**Canonical case:** linking Yahoo from inside the app while authenticated. If the session cookie failed the OAuth round-trip, the callback created a brand-new user and orphaned the original (Sleeper-linked) account.

**How to detect:**
- For any OAuth or session-bearing flow, ask: "What happens if `current_user` is None?"
- If the answer is "create a new user," that's likely wrong for the link path. Linking must distinguish from sign-up.
- Test by clearing the auth cookie mid-flow (in DevTools) and verifying the system refuses gracefully rather than silently switching the user.

## 4. Third-party library defaults

**Canonical case:** ESPN rejected all private-league connects. Two unverified assumptions:
1. httpx's default `python-httpx/0.x` User-Agent triggered ESPN's bot-block (302 to login).
2. httpx's `Cookies` object URL-encoded the curly braces in SWID. ESPN compared raw bytes and rejected the encoded value.

**How to detect:**
- For any third-party HTTP call, look up: what User-Agent does the library send by default? Does it follow redirects automatically? How does it encode cookie values? What's the default timeout?
- Don't trust "it works in the test." Test mocks don't enforce header parity; production servers do.

## 5. Persistence / migration gaps

**Canonical case:** migration 006 used the long-form revision id `"006_linked_leagues"` while the repo convention was short numeric `"005"`. Alembic couldn't resolve the chain and the API container failed at startup.

**How to detect:**
- For any new Alembic migration, run `alembic upgrade head` against a clean DB and verify it applies cleanly.
- For any NOT NULL → nullable transition, run the migration and verify existing data survives. Run the downgrade too.
- Don't merge a migration without testing both `upgrade()` and `downgrade()`.

## 6. UI inconsistency

**Canonical case:** linking a fantasy league collapsed the LinkedAccountsDialog to just the connected row, hiding Sleeper / NFL Fantasy / CBS rows. Users couldn't switch providers or see what was coming soon.

**How to detect:**
- For each possible state (unlinked / linked-with-league / linked-no-league / connecting / error), ask: "Does the UI show all the same affordances as the other states?"
- When you hide a button conditionally, check whether the adjacent affordances are also hidden consistently.
- Adjacent features should behave the same way. If Refresh is hidden when there's no league, Disconnect should also re-evaluate whether it makes sense.

## 7. Test sincerity

**Canonical case:** a test had `expect(getAllByText(/coming soon/i)).toHaveLength(2)` but the production change moved one of those rows behind a state branch the test never triggered. The test still passed because it counted text occurrences in the wrong state.

**How to detect:**
- For each test in the diff, mentally delete the production change and ask: would this test still pass? If yes, the test isn't sincere.
- For new `if/else` or `try/except`, both branches need a test that fails when the branch is deleted.
- Coverage tools confirm the line executed; only inspection confirms the test actually verified behaviour.

## 8. Git hygiene

**Canonical case:** `git add backend/ web/` accidentally staged the entire `backend/venv312/` directory. 5664 files in one commit. Required a force-push and a clean re-do.

**How to detect:**
- Before EVERY commit, run `git status` and inspect every file listed.
- Never `git add -A` or `git add .` or `git add <directory>`. Stage explicit paths.
- If staging a directory is unavoidable, run `git status --short --untracked-files=all <path>` first to verify nothing surprising is inside.
- Reject any commit larger than 50 files unless every file was deliberately staged.

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
