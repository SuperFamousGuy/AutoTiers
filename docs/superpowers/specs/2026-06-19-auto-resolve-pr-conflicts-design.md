# Auto-resolve PR merge conflicts (sweeper)

**Date:** 2026-06-19
**Status:** Approved (design)
**Sibling:** `docs/superpowers/specs/2026-06-19-auto-fix-pr-checks-design.md` — this workflow is a near-clone of that one; read it for the shared rationale (cron-not-event, deferred pass-stamp, PAT push).

## Goal

A fully-agentic GitHub Actions sweeper that detects open PRs with merge conflicts and resolves them end-to-end — merge the base branch into the PR head, resolve every conflict via the `resolve-merge-conflicts` skill, commit, and push — with zero manual approvals. Uncertain resolutions are pushed anyway and reported as a PR comment for after-the-fact human review.

## Why a cron sweeper, not an event trigger

Identical to the constraints documented in `claude-fix-pr-checks.yml`:
1. **Bot-actor gating** — a workflow run triggered by a bot actor (`github-actions[bot]` / `claude[bot]`) is parked in `action_required` awaiting manual approval, so an event-driven reaction can never be hands-off.
2. **Loop risk** — reacting to PR-update events re-fires on the resolution push's own update.

A scheduled (cron) workflow runs as the repo/owner identity, is not approval-gated, and is therefore fully agentic. We poll an idempotent work-signal — "open same-repo non-draft PR whose `mergeable == CONFLICTING`" — instead of reacting. Once resolved the PR is no longer `CONFLICTING`, so the next tick sees nothing. If the base moves and reconflicts, that is legitimate new work, picked up on a later tick.

## Autonomy decision

**Always push, flag uncertain** (chosen over "push only if confident" and "draft only"). Maximally hands-off, mirroring the fix-checks sweeper. A semantically-uncertain merge still lands on the branch; the agent posts an uncertainty log as a PR comment so a human can review after the fact.

**No local test gate** (decision A). After pushing the merge resolution, the PR's existing `tests.yml` re-runs on the push. If the merge broke something, the existing `claude-fix-pr-checks` sweeper observes the now-red checks and heals them on its own cadence. The two sweepers compose: this one unsticks the merge, that one fixes any fallout. We do not duplicate test-running logic here, and a flaky test never blocks an otherwise-fine resolution.

## Workflow: `claude-resolve-conflicts.yml`

### Triggers
- `schedule: cron: "45 */2 * * *"` — every 2 hours at minute 45. Offset from the other scheduled workflows so no two tick in the same minute and double-spend the shared subscription quota: copilot sweeper = minute 0 (hourly), fix-checks sweeper = minute 30 (hourly), sweeper-health = minute 17 (hourly). Minute 45 collides with none. (Do NOT use `"0 */2 * * *"` — minute 0 collides with the hourly copilot sweeper on every even hour.) Conflicts are less time-sensitive than failing checks, so a 2-hourly cadence is fine; the work-signal is idempotent so a missed tick is harmless. (Note: GitHub throttles high-frequency cron on low-activity repos — a faster cadence would not be honored anyway.)
- `workflow_dispatch: {}` — manual kick for testing.

### Concurrency
`group: claude-resolve-conflicts-sweeper`, `cancel-in-progress: false` — serialize ticks so two overlapping runs never both read the same prior pass counts and double-spend budget; let an in-flight run (possibly mid-push) finish.

### Permissions
`contents: write`, `pull-requests: write`, `issues: write` (PR labels are issue labels), `id-token: write` (claude-code-action mints its token via OIDC).

### Env
- `MAX_PASSES: 3` — cap on automatic resolution attempts per PR.

### Auth
- `CLAUDE_CODE_OAUTH_TOKEN` — subscription auth for claude-code-action.
- `PR_AUTHOR_PAT` — Copilot-licensed PAT with `workflows` + `contents:write`. The agent COMMITS ONLY; a dedicated push step re-seats git's transport with the PAT because claude-code-action's minted OIDC App token is refused write access to `.github/workflows/` (a conflict can occur in a workflow file).

### Stage 1 — `scan` (cheap, no toolchain, no Claude)

Pure `gh`/GraphQL. Emits `matrix` (JSON array of eligible PR numbers) and `any` (boolean). When `any == false`, Stage 2 is skipped wholesale so the idle path costs only the gh calls.

Eligibility per open same-repo non-draft PR:
1. Read `mergeable` (GraphQL `pullRequest.mergeable`: `MERGEABLE` | `CONFLICTING` | `UNKNOWN`).
   - `UNKNOWN` → GitHub is still computing the merge; skip this tick (settle guard).
   - `MERGEABLE` → nothing to do.
   - `CONFLICTING` → candidate.
2. Count prior `claude-resolve-conflicts-pass-K` labels.
   - `< MAX_PASSES` → eligible.
   - `>= MAX_PASSES` → post a one-time capped notice (guarded by a `claude-resolve-conflicts-capped` label) telling a human to investigate and remove the `pass-*` labels to re-arm; then skip.

Forks (`isCrossRepository`) and drafts (`isDraft`) are filtered out up front — the PAT can't push to a fork and a draft is WIP.

Mirror the fix-checks scan's defensive handling: if a `gh`/GraphQL call returns empty/errors, default to treating the PR as not-actionable and emit a `::warning::` so a silently broken scan is visible in the run log.

### Stage 2 — `resolve` (expensive, one job per eligible PR)

`needs: scan`, `if: needs.scan.outputs.any == 'true'`. `strategy.max-parallel: 1`, `fail-fast: false`, matrix over eligible PR numbers. `timeout-minutes: 30`.

Steps:
1. **Count prior passes (decide budget)** — gate the expensive steps; do NOT stamp yet (deferred-stamp trick: an infra failure in checkout/setup must not burn a pass). Output `has_budget` and `next_label`.
2. **Resolve PR head + base refs** — `gh pr view --json headRefName,baseRefName`. The base is read from `baseRefName`, never hardcoded.
3. **Checkout PR head** — `actions/checkout@v4`, `token: PR_AUTHOR_PAT`, `ref: <headRefName>`, `fetch-depth: 0` (full history needed for the merge).
3a. **Provision lockfile toolchain (lightweight)** — `setup-node@v4` (node 20) and `setup-python@v5` (3.14), versions matching `tests.yml`. This is ONLY so the `resolve-merge-conflicts` skill can regenerate a conflicted lockfile (`rm package-lock.json && npm install` from `web/`, or the python equivalent). We deliberately do NOT run `npm ci` / `pip install -e ".[dev]"` and do NOT run tests (decision A) — those are the fix-checks sweeper's job. `npm install` for lockfile regen pulls its own tree.
4. **Stamp pass label** — `claude-resolve-conflicts-pass-K` right before Claude runs (termination invariant: label exists before the push that could reconflict-check, so the next tick observes the incremented count and stops at the cap). Adding an already-present label is a no-op, so a retried run can't double-count.
5. **Resolve conflicts (commit only, do not push)** — `anthropics/claude-code-action@v1`, subscription auth, `GH_TOKEN: PR_AUTHOR_PAT`. Prompt instructs the agent to:
   - `git fetch origin` then `git merge origin/<baseRefName>` to surface the conflicts on the PR head.
   - Invoke the `resolve-merge-conflicts` skill and resolve every conflicted hunk. Make best-guess semantic merges; do NOT change code beyond what each hunk requires.
   - This is CI: ignore any local `/Users/...` paths or `venv/bin/` prefixes in the skill, and do NOT run the test suite (decision A — that's the fix-checks sweeper's job). Lockfile regeneration in the skill DOES apply if a lockfile conflicts — node/python are provisioned in step 3a; run the install from the lockfile's subdir (e.g. `web/`).
   - Verify no conflict markers remain (the skill's grep step).
   - Commit the merge (the merge commit is the ONLY commit). Do NOT push. Write a `.resolved.flag` sentinel at repo root (do not commit it).
   - Post the uncertainty log from the skill's report as a PR comment.
   - If the conflict CANNOT be resolved (e.g. requires a human product decision, or the merge surfaces no conflicts because the state was stale): do NOT commit, do NOT write the flag; post a comment explaining and STOP.
   - `claude_args`: `--model claude-opus-4-8`, `--max-turns 80`, `--allowedTools Edit,Write,Read,Glob,Grep,Bash,Task`.
6. **Push resolved branch** — gated on `hashFiles('.resolved.flag') != ''`. Re-seat git transport with the PAT (`-c http.https://github.com/.extraheader=` clears the App-token header; inline `x-access-token:PAT` in the remote URL authenticates as the PAT) and `git push HEAD:refs/heads/<headRefName>`. Same mechanism and rationale as fix-checks.

## Termination

The work-signal is self-clearing: the workflow only acts on `CONFLICTING` PRs. A successful resolution makes the PR `MERGEABLE`, so the next tick ignores it. `MAX_PASSES=3` bounds the pathological case where a resolution attempt does not clear the conflict (incomplete resolution, push failure, immediate re-conflict). At the cap the PR gets a one-time `-capped` notice and is skipped until a human removes the `pass-*` labels.

## Secrets / prerequisites

No new secrets — reuses `CLAUDE_CODE_OAUTH_TOKEN` and `PR_AUTHOR_PAT`, already provisioned for the existing sweepers. The `resolve-merge-conflicts` skill already exists in `.claude/skills/`.

## Out of scope

- Resolving conflicts on fork PRs (PAT can't push to forks).
- Running tests / fixing post-merge breakage (owned by the `claude-fix-pr-checks` sweeper).
- Any change to the `resolve-merge-conflicts` skill itself.

## Testing / verification

- YAML lint / actionlint on the new workflow file.
- `workflow_dispatch` manual run against a deliberately-conflicted test PR to confirm the full scan → merge → resolve → push round-trip and the uncertainty comment.
- Confirm a `MERGEABLE` PR and a fork PR are both skipped by the scan.
- Confirm the `MAX_PASSES` cap posts the one-time notice and then skips.
