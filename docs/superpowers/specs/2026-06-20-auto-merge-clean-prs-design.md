# Auto-merge clean PRs (sweeper) — Design

**Date:** 2026-06-20
**Status:** Approved (design) — pending user sign-off before implementation
**Siblings:**
- `docs/superpowers/specs/2026-06-19-auto-resolve-pr-conflicts-design.md` — conflict-resolution sweeper.
- `docs/superpowers/specs/2026-06-19-auto-fix-pr-checks-design.md` — check-fixing sweeper.
- `.github/workflows/claude-sweeper-health.yml` — the **pure-mechanical** sweeper this one is modeled on (gh/GraphQL only, `GITHUB_TOKEN`, NO Claude, NO PAT).

This sweeper is the *terminal* member of the sweeper family: the others UNSTICK PRs (resolve conflicts, fix checks, address Copilot review); this one MERGES the PRs they've made clean. It composes with them — it only ever acts on PRs the others have already brought to a green, conflict-free, reviewed, quiet state.

## Goal

A fully-agentic cron sweeper that automatically merges open PRs which are unambiguously safe to merge: CI green, no conflicts, Copilot has reviewed, no unresolved threads, quiet for 24h, and authored by a bot or a repo collaborator. Zero manual approvals.

## Approach

A scheduled (cron) workflow polls an idempotent work-signal — "open PR satisfying all six merge predicates" — and merges each match via `gh pr merge --squash --delete-branch`. It is a **pure-GitHub-Actions** workflow: `gh` CLI + a single GraphQL query per PR, no `claude-code-action`, no PAT. All six criteria are mechanically checkable, so invoking Claude would add cost and a failure mode for zero benefit. Self-clearing: a merged PR is closed and never re-scanned.

## Why pure-mechanical (NO Claude), and why `GITHUB_TOKEN` (NO PAT)

The user explicitly asked us to evaluate pure-GHA vs. a Claude-invoking workflow and recommend the simplest that satisfies the criteria. The recommendation is **pure-GHA**:

1. **All six criteria are deterministic GraphQL/REST reads.** There is no judgment call for an LLM to make — "is the rollup SUCCESS", "is mergeable MERGEABLE", "does a review by `copilot-pull-request-reviewer[bot]` exist", "are all reviewThreads resolved", "is the newest activity ≥24h old", "is the author a bot or collaborator" are all boolean. A Claude invocation would be slower, cost subscription quota, and introduce a non-deterministic actor into a destructive action (merge). Mechanical is cheaper AND more reliable here.
2. **No new secrets.** Uses the built-in `GITHUB_TOKEN` only — same as `claude-sweeper-health.yml`.

**Token decision (verified live, 2026-06-20):** `main` is **NOT branch-protected** (`gh api repos/:owner/:repo/branches/main/protection` → 404 "Branch not protected"). A merge is therefore a plain **Contents-write + PR-write**, both grantable to the built-in `GITHUB_TOKEN` via `permissions:`. The `PR_AUTHOR_PAT` that the resolve/fix sweepers need exists ONLY because those sweepers push commits that may touch `.github/workflows/`, which the App-OIDC token is refused. **A merge writes no workflow file, so this sweeper does NOT need the PAT.**

**One documented caveat:** a merge performed with `GITHUB_TOKEN` does not cascade-trigger downstream workflows. That is harmless here — `main`'s own CI (`tests.yml`, `coverage.yml`, `deploy.yml`) runs on `push`/its own triggers regardless of who pushed the merge commit, and there is no loop because a merged PR is closed and never re-scanned.

## Autonomy / safety posture

**Report-only first, then arm.** The workflow ships with an `env: DRY_RUN: "true"` default. In dry-run the scan logs exactly which PRs WOULD be merged (with the satisfied-predicate breakdown) and merges nothing. After the user confirms the predicate matches their intent against real PRs, flip `DRY_RUN` to `"false"` in a one-line follow-up commit to arm the merge. This is the safety analogue of the resolve sweeper's "flag uncertain" posture: a destructive action (merge) gets a human-verifiable preview before it's live.

## Workflow: `claude-auto-merge.yml`

> Named `claude-auto-merge` for family consistency with the other `claude-*` sweepers even though it invokes no Claude — the prefix is the discovery convention for "agentic repo-maintenance sweeper," and the health watcher keys off that prefix.

### Triggers
- `schedule: cron: "50 */3 * * *"` — every 3 hours at minute **50**. Offset from all four existing scheduled workflows so no two tick in the same minute and double-spend the shared run budget. Verified taken minute fields: copilot-review = min 0, sweeper-health = min 17, fix-checks = min 30, resolve-conflicts = min 45. **Minute 50 collides with none.** A `*/3` schedule still fires AT its minute field (the cron-collision gotcha), so the minute field is what must be unique — the hour spacing is irrelevant to collision. Auto-merge is the least time-sensitive sweeper (a PR sitting clean for an extra few hours is harmless), and the work-signal is idempotent, so a 3-hourly cadence is ample. (GitHub throttles high-frequency cron on this low-activity repo anyway, so a faster cadence would not be honored.)
- `workflow_dispatch: { inputs: { dry_run } }` — manual kick for testing; the input overrides the `DRY_RUN` env so a maintainer can preview or force-arm a single run.

### Concurrency
`group: claude-auto-merge-sweeper`, `cancel-in-progress: false` — serialize ticks so two overlapping runs never both decide to merge the same PR; let an in-flight run finish.

### Permissions
`contents: write` (perform the merge), `pull-requests: write` (merge via the PR + delete branch), `checks: read` + `statuses: read` (read the check rollup). NO `id-token` (no OIDC/claude-code-action). NO PAT.

### Env
- `DRY_RUN: "true"` — report-only by default (see safety posture). `workflow_dispatch` input overrides.
- `QUIET_HOURS: "24"` — criterion 5 threshold.
- `COPILOT_REVIEWER_LOGIN: "copilot-pull-request-reviewer[bot]"` — criterion 3 keys off this exact login.
- `MERGE_METHOD: "squash"` — see Q3.
- `HOLD_LABELS: "do-not-merge,hold"` — escape-hatch labels (Q4).

### Auth
`GITHUB_TOKEN` only. No `CLAUDE_CODE_OAUTH_TOKEN`, no `PR_AUTHOR_PAT`.

### Stage 1 — `scan` (the whole workflow; cheap, no toolchain, no Claude)

Unlike the Claude sweepers there is no expensive Stage 2 — the merge IS the cheap action, so it lives in the scan job. Pure `gh`/GraphQL + `python3` (preinstalled on the runner) for date math (criterion 5).

Per open PR, fetch ONE GraphQL document and evaluate all six predicates. Eligibility requires ALL six:

1. **CI passing (crit 1)** — `pullRequest.commits(last:1).nodes.commit.statusCheckRollup.state == SUCCESS`. A `null` rollup means the head commit has **no checks at all** → treat as **NOT eligible** (we never auto-merge something CI never validated). `PENDING`/`FAILURE`/`ERROR`/`EXPECTED` → ineligible (settle/fail guard). Because `main` is unprotected we use the rollup as the gate directly; if branch protection is added later, the required-check semantics should be revisited (see Out of scope).
2. **No conflicts (crit 2)** — `pullRequest.mergeable == MERGEABLE`. `UNKNOWN` → GitHub is still computing; skip this tick (settle guard). `CONFLICTING` → ineligible (the resolve-conflicts sweeper owns that).
3. **Copilot reviewed (crit 3)** — at least one `pullRequest.reviews` node whose `author.login == COPILOT_REVIEWER_LOGIN`. **Detect by PRESENCE of a review from that login, in ANY state.** Copilot's reviews come back `COMMENTED` (verified on PR #374), essentially NEVER `APPROVED`. **Gating on `state == APPROVED` would mean the sweeper never fires — this is the single biggest footgun in the feature.**
4. **No unresolved threads (crit 4)** — `pullRequest.reviewThreads(first:100).nodes` filtered to `isResolved == false` must be **empty**. ADDITIONALLY: no outstanding `CHANGES_REQUESTED` review — compute the latest review per human author; if any human's most-recent review is `CHANGES_REQUESTED` (and not subsequently dismissed), the PR is ineligible. (A human asking for changes is an unresolved objection even if no inline thread is open.)
5. **Quiet 24h (crit 5)** — compute `max(timestamps)` over: head commit `committedDate` (`commits(last:1)`), every issue comment `createdAt` (`comments`), every review comment `createdAt`/`updatedAt` (within `reviewThreads.comments`), and every review `submittedAt` (`reviews`). Require `now - max >= QUIET_HOURS`. Date math in `python3` (jq date math is unavailable locally and brittle on the runner). If a PR has zero comments/reviews, the floor is the head-commit date. (The Copilot review from crit 3 counts as activity — so a freshly-reviewed PR is correctly held until 24h after the review.)
6. **Author is bot OR collaborator (crit 6)** — `pullRequest.author.__typename == "Bot"` (covers `claude[bot]`, `copilot-pull-request-reviewer[bot]`, etc.), with a `login` ending in `"[bot]"` as a fallback. ELSE call `gh api repos/:owner/:repo/collaborators/<login>/permission --jq .permission` and accept `admin|write|maintain`; `read` or 404 (not a collaborator) → ineligible. Using the collaborator-permission API (not PR `authorAssociation`) is deliberate: `authorAssociation == CONTRIBUTOR` is returned for anyone who ever had a PR merged, which is too loose for a "trusted to auto-merge" gate.

**Guards (ineligible up front, before the six predicates):**
- `isDraft == true` → skip (WIP). (Q4)
- Any label in `HOLD_LABELS` present → skip (escape hatch). (Q4)
- `isCrossRepository == true` (fork) → skip. Fork branches can't be deleted by us and a fork PR is a weaker trust signal; defer to Out of scope.

**Defensive handling (mirror the other sweepers):** if a `gh`/GraphQL call returns empty/errors for a PR, default to treating it as **NOT eligible** and emit a `::warning::` so a silently broken scan is visible rather than masquerading as "nothing to merge."

**Action per eligible PR:**
- If `DRY_RUN` truthy: log `WOULD MERGE PR #N (method=$MERGE_METHOD)` with the satisfied-predicate summary. Merge nothing.
- Else: `gh pr merge "$N" --repo "$REPO" --squash --delete-branch`. On failure (race: someone pushed between scan and merge, or transient API error), emit a `::warning::` and continue — no retry/cap label is needed because the work-signal is self-clearing and a transient failure is simply re-evaluated next tick (a since-merged or since-modified PR will no longer match). To avoid comment spam we post NOTHING on a routine failure (just the run-log warning); only persistent operator-visible failures surface via the health watcher (follow-up).

## Resolved open questions

- **Q1 (Copilot detection):** presence of a review by `copilot-pull-request-reviewer[bot]`, ANY state. (Not `APPROVED`.)
- **Q2 (contributor):** collaborator permission in `{admin, write, maintain}` via the collaborator-permission API; bots via `__typename == "Bot"` / `[bot]` suffix.
- **Q3 (merge method + branch delete):** **squash + delete-branch.** Squash keeps `main` history linear and one-commit-per-PR (consistent with how the repo's PRs read today); `--delete-branch` prevents head-branch litter (repo `delete_branch_on_merge` is `false`, so we delete explicitly). Fork head branches can't be deleted by us — moot, since fork PRs are skipped. `MERGE_METHOD` is an env so it's tunable to `merge`/`rebase` without editing logic.
- **Q4 (draft gate + hold label + CHANGES_REQUESTED):** skip drafts; skip any PR labeled `do-not-merge` or `hold` (auto-skipped if the label simply doesn't exist on a PR — no need to pre-create them); treat an outstanding human `CHANGES_REQUESTED` as ineligible (folded into crit 4).

## Termination / idempotency

Self-clearing: a merged PR is closed and never re-scanned, so no `MAX_PASSES` / pass-label machinery is needed (there is no retry loop — a single merge either closes the PR or is harmlessly re-evaluated next tick). Dry-run merges nothing, so it is trivially terminating.

## Math / statistical claims

N/A — no scoring, weights, clustering, or inference. The only arithmetic is a timestamp subtraction for the 24h quiet window.

## FF heuristic basis

N/A — this is repo-maintenance automation; no fantasy-football domain logic.

## Out of scope (each bullet → a GitHub issue in Stage 3.6)

- **Auto-merging fork PRs.** We can't delete their head branch and a fork is a weaker trust signal.
- **Branch-protection-aware required-check gating.** `main` is currently unprotected; we gate on the rollup. If protection with required checks is added later, the gate should switch to "all REQUIRED checks pass" rather than "whole rollup SUCCESS."
- **A configurable author allowlist** (beyond bot-or-collaborator), e.g. merge only PRs from a named set of authors.
- **A health-watcher entry for THIS sweeper in `claude-sweeper-health.yml`.** Every other sweeper is health-watched; this one should be too (strongly recommended follow-up).
- **A persistent escape-hatch / capped notice on repeated merge failures.** Currently a failed merge is only a run-log warning; if a PR repeatedly fails to merge we rely on the health watcher to surface it rather than labeling the PR.

## Open questions

None blocking. The four design questions are resolved above with stated defaults; all are `env`-tunable. The only genuine decision left for the user is operational, not design: **confirm the DRY_RUN preview against real PRs, then flip `DRY_RUN` to `"false"` to arm it.**

## Testing / verification

- `actionlint` (+ its `shellcheck` pass) on the new workflow file.
- Structural greps: cron minute `50` is unique vs the other four; NO `PR_AUTHOR_PAT` reference anywhere; NO `claude-code-action` reference; the exact `copilot-pull-request-reviewer[bot]` login string present; `gh pr merge` present; `DRY_RUN` env present and defaulting to `"true"`.
- `workflow_dispatch` dry-run from the feature branch: confirm the scan logs the correct `WOULD MERGE` / skip decisions against current real PRs, and merges nothing. Manually verify a few of its verdicts by hand (pick one eligible-looking PR and one held-by-each-criterion PR).
- A second `workflow_dispatch` with `dry_run=false` against a single deliberately-clean throwaway PR to confirm the real merge + branch delete round-trip, then clean up.
