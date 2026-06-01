---
name: autotiers-test-running
description: Concrete commands for running pytest, vitest, tsc, and coverage in the AutoTiers repo. Invoke before claiming a change is tested — agents that skip this invariably miss the project-specific gotchas (venv path, OOM on full pytest, warnings to ignore).
---

# Running tests in AutoTiers

## Backend (pytest)

The venv lives at `backend/venv/`. Other venvs (`venv312/`, `venv313/`) are gitignored experimental copies — do not rely on them.

### Run a focused subset (default for most changes)

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest \
  tests/<file_you_touched>.py \
  tests/<adjacent_file>.py \
  -q
```

### Run a broader sweep (when the change touches shared code)

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest \
  tests/test_linked_league_endpoints.py \
  tests/test_integrations/ \
  tests/test_google_oauth.py \
  tests/test_yahoo_oauth.py \
  tests/test_auth_unlink.py \
  tests/test_fernet.py \
  -q
```

### The full suite

`venv/bin/pytest -q` works locally but can OOM in CI on the data-pipeline tests (`tests/test_sources/`). If a full run is needed:

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/ -q --ignore=tests/test_sources
```

### Coverage check (matches the CI gate)

```bash
cd /Users/karlkell/Code/AutoTiers/backend && \
  venv/bin/pytest tests/ --cov=app --cov-report=xml --ignore=tests/test_sources -q
```

The diff-coverage CI gate requires **≥80%** on lines touched relative to `origin/main`. Always check this for new branches in `_handle_oauth_link`, `_provider_http_error`, and similar central helpers.

### Warnings to ignore

These are pre-existing and not regressions:

- `InsecureKeyLengthWarning: HMAC key is 24 bytes long` — test JWT secret is short by design.
- `DeprecationWarning: datetime.utcnow()` — pre-existing in `app/data/sources/`.

Do NOT silence these; just don't treat them as failures.

## Frontend (vitest, tsc)

### Focused

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/<path>.test.tsx 2>&1 | tail -8
```

### Full sweep

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run 2>&1 | tail -5
```

Should report `Tests N passed (N)` with no failures. The current baseline is around 156 tests.

### Type check

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated"
```

`app-authenticated.test.tsx` has two pre-existing unused-import warnings; filter them out. **Any other tsc error is a blocker.**

## What "tests pass" actually requires

Before claiming DONE on a change:

1. The targeted tests for files you touched pass.
2. A broader sweep of related areas passes (no regressions).
3. `tsc --noEmit` is clean for files you touched.
4. For new code branches: a test exists that would FAIL if that branch's behaviour was deleted. Coverage tool catches presence; only manual inspection catches sincerity.

If you can't satisfy all four, report `DONE_WITH_CONCERNS` listing exactly what you couldn't verify, not `DONE`.
