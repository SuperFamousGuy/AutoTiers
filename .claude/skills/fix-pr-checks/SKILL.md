---
name: fix-pr-checks
description: Resolve failing CI checks on a GitHub PR end-to-end — fetch failing check logs, diagnose root cause, apply fixes (GitHub Actions failures, lint errors, type errors, test failures), verify locally, commit, push, and report a summary. Works in any repo with `gh` auth configured. Invoke when the user says "fix the failing checks", "CI is red", "fix the failing tests on PR #N", "checks are failing", "green the CI", "the build is broken on my PR", "fix the lint errors", "make the checks pass", or any similar phrase asking to fix broken CI or check failures on a pull request.
---

# Fix PR Failing Checks

## Before starting

```bash
# Confirm gh auth and get repo context
gh auth status
gh repo view --json owner,name,defaultBranchRef -q '.owner.login + "/" + .name'
```

If the user gave a PR number, use it. Otherwise detect from current branch:

```bash
gh pr view --json number,headRefName,url 2>/dev/null
```

If no PR exists for the current branch, tell the user and stop.

---

## Step 1: Inventory failing checks

```bash
# List all checks for the PR
gh pr checks <PR_NUMBER> --json name,status,conclusion,detailsUrl,workflowName 2>/dev/null \
  || gh pr checks <PR_NUMBER>
```

Filter to `conclusion: failure` (or `conclusion: timed_out`). Group by type:

| Category | Signals |
|----------|---------|
| **GitHub Actions / CI** | Has a `workflowName`, logs accessible via `gh run view` |
| **Lint / format** | Check name contains: lint, eslint, ruff, flake8, prettier, format, style |
| **Type check** | Check name contains: tsc, mypy, pyright, typecheck, type-check |
| **Tests** | Check name contains: test, jest, pytest, vitest, mocha, spec |

One check run can cover multiple categories — read the logs to be sure.

---

## Step 2: Fetch failure logs

### GitHub Actions runs

```bash
# Get the head SHA for the PR
HEAD_SHA=$(gh pr view <PR_NUMBER> --json headRefOid -q .headRefOid)

# List recent workflow runs for that SHA
gh run list --branch $(gh pr view <PR_NUMBER> --json headRefName -q .headRefName) \
  --json databaseId,name,conclusion,status --limit 20 \
  | python3 -c "import json,sys; [print(r['databaseId'], r['name'], r['conclusion']) for r in json.load(sys.stdin) if r['conclusion']=='failure']"

# Get failed step logs for a specific run
gh run view <RUN_ID> --log-failed
```

If `gh run view --log-failed` output is very long, pipe through `head -200` per failing job to get the critical error lines. Look for:
- The first `Error:` or `FAIL` line in the output
- Stack traces
- Compiler/interpreter error messages
- Missing file or module errors

### External check services (non-Actions)

If `detailsUrl` points to an external CI service (CircleCI, Travis, etc.), note it and tell the user you can't fetch those logs directly — ask them to paste the relevant error output.

---

## Step 3: Diagnose root cause

Before touching any code, form a hypothesis:

- **Import / module not found** → missing dependency, wrong path, or package not installed
- **Type error** → wrong type annotation, missing type guard, API mismatch
- **Assertion failure in tests** → logic bug, changed interface, wrong expected value
- **Lint error** → style violation, unused import, unsafe pattern
- **Format error** → run the formatter, do not manually edit whitespace
- **Build / compile error** → syntax error, missing export, wrong tsconfig/pyproject setting
- **Timeout** → flaky test or infinite loop; look for the hung test name in the log

If the root cause is ambiguous (e.g., multiple unrelated failures), fix the most foundational one first (build errors before lint, lint before tests).

---

## Step 4: Fix by category

### Lint / format — run the auto-fixer first

```bash
# JavaScript / TypeScript
npx eslint --fix .
npx prettier --write .

# Python
ruff check --fix .
ruff format .

# Then re-run to confirm no remaining errors
npx eslint .
ruff check .
```

If the auto-fixer can't resolve everything, read the remaining violations and fix them manually.

### Type errors

Read the type error message carefully — it tells you the exact file, line, and mismatch. Fix the source code, not the type annotations (unless the annotation is genuinely wrong). Common patterns:

- `Property X does not exist on type Y` → check the actual shape of the object
- `Type A is not assignable to type B` → add a type guard or fix the upstream value
- `Object is possibly undefined` → add a null check

Verify after each batch of changes:

```bash
npx tsc --noEmit          # TypeScript
python -m mypy .          # Python (mypy)
python -m pyright .       # Python (pyright)
```

### Test failures

Read the test output to identify:
1. Which test file and test name failed
2. The actual vs. expected values
3. Whether the test is testing the right thing or if the implementation is wrong

Fix the **implementation**, not the test — unless the test has a clearly wrong expected value (e.g., a hardcoded constant that changed intentionally).

Run tests locally after fixing:

```bash
npm test                  # or jest, vitest, etc.
python -m pytest          # Python
```

If a test is flaky (fails intermittently without code changes), note it explicitly in the commit message and in the final report.

### CI / build failures

Look at the full job log to identify the failing step. Common cases:

- **Dependency install failed** → check lockfile, add missing dep
- **Script not found** → check package.json scripts or Makefile
- **Environment variable missing** → may need a repo secret; note this and tell the user
- **Docker build failed** → read Dockerfile error; usually a missing COPY or RUN failure
- **Migration / schema error** → database migration out of sync

---

## Step 5: Local verification

Before pushing, run the same checks locally to confirm the fix works:

```bash
# Run whatever the CI runs — check the workflow YAML for the exact commands
cat .github/workflows/*.yml | grep -A2 "run:" | grep -v "^--$"
```

Replicate the failing step's `run:` command locally. If it passes locally, proceed.

If you can't replicate CI locally (e.g., needs Docker, secrets, or a specific OS), note that in the commit message.

---

## Step 6: Commit and push

Stage only files related to the fix:

```bash
git diff --name-only          # review what changed
git add <specific files>      # never git add -A blindly
git commit -m "fix: <concise description of what broke and what you did>

- Fixed: <check name> — <root cause>
- Verified: <how you confirmed the fix>

Co-Authored-By: Claude <noreply@anthropic.com>"
git push
```

Use conventional commit prefixes: `fix:`, `chore:` (for lint/format), `test:` (for test fixes).

---

## Step 7: Monitor and report

After pushing, wait ~60 seconds then check check status:

```bash
gh pr checks <PR_NUMBER> --watch   # streams updates until all checks finish
# or poll manually:
gh pr checks <PR_NUMBER>
```

Report a summary table when done:

| Check | Before | After | Action taken |
|-------|--------|-------|--------------|
| ESLint | FAIL | PASS | Auto-fixed 3 unused imports |
| tsc | FAIL | PASS | Added null check in `fetchUser()` |
| pytest | FAIL | PASS | Fixed off-by-one in `calculate_rank()` |

If any check is still failing after the push, repeat from Step 2 for that check. If the failure is outside the codebase (missing secret, infra issue, external service), tell the user clearly and stop.

---

## Pause points (the only times to ask)

Pause and ask the user before acting in these cases:

1. **Ambiguous root cause** — multiple plausible explanations and you're not confident which to fix
2. **Test seems intentionally wrong** — the fix would change test expectations in a way that might be a product decision
3. **Missing CI secret or env var** — can't fix without repo-level configuration access
4. **Requires a schema / database migration** — irreversible changes outside the branch

Everything else: fix, verify, push without asking.
