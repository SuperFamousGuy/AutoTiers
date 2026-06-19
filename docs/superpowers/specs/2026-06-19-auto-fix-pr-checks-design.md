# Auto-Fix PR Failing Checks — Design

## Goal
When an open same-repo PR has failing CI checks, fix them automatically — no human
in the loop — until the checks go green or a per-PR pass cap is hit.

## Approach
A cron-driven **sweeper** (not an event trigger) polls every 10 minutes for open
same-repo PRs whose head SHA has ≥1 failed check run and budget remaining. For each,
it checks out the PR head, runs the `fix-pr-checks` skill via `claude-code-action`
(commit-only), pushes the fix with the Copilot-licensed PAT, and lets the existing
`tests`/`coverage` workflows re-run on the push. Self-limiting: green checks or the
pass cap ends the loop.

## Why cron, not an event trigger (the key decision)
The user asked for "auto on check failure," whose literal shape is a
`check_suite`/`workflow_run: { types: [completed], ... }` trigger. The repo already
learned why that doesn't work (see `claude-address-copilot-review.yml:6-15`):

1. **Bot-actor gating** — any run triggered by a bot actor (`github-actions[bot]`,
   `claude[bot]`) is parked in `action_required` awaiting manual approval. The fix
   push's checks are bot-attributed, so an event-driven re-run can't be fully
   agentic.
2. **Infinite loop** — `workflow_run: failure` re-fires on the fix push's *own*
   re-run of the checks. If the fix doesn't fully green them, it triggers itself
   forever with no natural bound.

A scheduled workflow runs as the repo/owner identity (not approval-gated) and polls
an idempotent work-signal, so a skipped or duplicate tick is harmless. This mirrors
the copilot-review sweeper exactly. Same hands-off UX, none of the landmines.

## Auth (mirrors the two existing Claude workflows)
- **`CLAUDE_CODE_OAUTH_TOKEN`** — subscription auth for `claude-code-action` (kills
  per-token API cost; draws personal Pro/Max quota).
- **`PR_AUTHOR_PAT`** — Copilot-licensed PAT with `workflows` + `contents:write`.
  The agent **commits only**; a dedicated push step re-seats git's transport with
  the PAT (`-c http...extraheader=` clears the action's App-OIDC header). App OIDC
  tokens are refused write access to `.github/workflows/`, and a check fix may edit a
  workflow file — so the PAT push is mandatory, exactly as in
  `claude-implement-issue.yml` / `claude-address-copilot-review.yml`.

Both secrets already exist in the repo; no new secret provisioning.

## Termination
Per-PR incrementing label `claude-fix-checks-pass-K`, stamped right before the agent
runs. Scan counts existing labels; at `>= MAX_PASSES` (default 3) the PR is skipped
forever until a human removes the labels to re-arm. A one-time `claude-fix-checks-capped`
label guards the cap-notice comment so it isn't re-posted every tick. Identical
mechanism to the copilot sweeper.

## Work-signal scope (which failures are actionable)
- **In scope:** failed check runs from `tests` (backend pytest, frontend vitest) and
  `coverage` (diff-coverage gate) — the kinds `fix-pr-checks` is built to resolve.
- **Excluded by denylist** (`SKIP_CHECK_PATTERNS`): any check whose name matches
  `deploy` or `CodeQL`/`security` — Claude must not touch prod deploy or security
  scans. `deploy.yml` is release/dispatch-only so it isn't a PR check today, but the
  denylist makes that guarantee explicit and future-proof.
- **Settle guard:** skip a PR if ANY check is still `in_progress`/`queued` — act only
  on a settled suite, never mid-run.
- **Draft guard:** skip draft PRs (WIP; fixing their checks is wasteful churn).
- **Same-repo only:** `isCrossRepository == false` (a fork PR can't be pushed with our
  PAT). Same guard as the copilot sweeper.

## Cost
Idle path is a cheap scan job (gh/GraphQL only) that exits before provisioning the
toolchain or invoking Claude when no PR is eligible. Cron offset to `2,12,22,32,42,52`
so it doesn't collide tick-for-tick with the copilot sweeper's `*/10` and double-spend
quota in the same minute.

## Out of scope
- Reacting in real time (cron has up to ~10 min latency — acceptable; the signal is
  idempotent).
- Fixing failures on cross-repo/fork PRs.
- Fixing `deploy`/security check failures (denied by design).
- A staleness/health alarm for THIS sweeper (the existing `claude-sweeper-health.yml`
  pattern could be extended later — file as a follow-up issue).

## Open questions
None blocking. Defaults (MAX_PASSES=3, 10-min cron, deploy/security denylist, skip
drafts) are chosen to match the copilot sweeper and are tunable via `env`.
