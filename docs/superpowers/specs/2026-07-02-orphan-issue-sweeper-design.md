# Orphan-issue sweeper — Design

**Date:** 2026-07-02
**Status:** Approved (design) — pending user sign-off before implementation
**Siblings / prior art:**
- `docs/superpowers/specs/2026-06-16-auto-implement-issues-design.md` — the auto-implement flow this sweeper backstops.
- `.github/workflows/claude-implement-issue.yml` — the workflow being extended with a `workflow_dispatch` re-entry point.
- `.github/workflows/claude-sweeper-health.yml` — the pure-mechanical health-watcher this sweeper is modeled on and adds a 4th job to.
- `.github/workflows/claude-auto-merge.yml` — closest structural sibling (thin shell + unit-tested Python decision core).
- `backend/scripts/sweeper_health.py` — the decision-core idiom the new `orphan_issue_sweep.py` mirrors.

## Problem

`claude-implement-issue.yml` triggers **only** on `issues: [opened, reopened]` — an event-driven webhook, not a poll. Nothing ever re-scans open issues.

The auto-implement flow has two distinct no-PR outcomes:

1. **Deliberate stop** — the agent ran, its tests failed, and per the workflow's own design (lines 108–110) it posted a blocker comment on the issue and stopped. The job concludes **green**. This is a *correct* terminal state, not a failure.
2. **Silent death** — the `claude-code-action` step itself errors before the agent can post anything. The dominant cause is **Claude subscription quota exhaustion** for the day (the flow uses `CLAUDE_CODE_OAUTH_TOKEN`, drawing personal Pro/Max quota — see memory `project_ci-subscription-auth.md`), but timeouts and transient action errors land here too. The job concludes **red**, and the downstream push/PR steps are skipped because they gate on `hashFiles('.pr-body.md')`. Net issue-level signal: **nothing** — no branch, no PR, no comment, no label.

A silently-dead issue is now orphaned permanently: it will never be `opened` again, and only a manual close+reopen re-triggers implementation. The user hit exactly this when a day's Claude credits ran out mid-queue.

## Goal

A scheduled sweeper that detects orphaned issues (silent-death only, never the deliberate-stop case), re-dispatches the implement flow for them via a bounded number of retries, and escalates to a human alarm when an issue exhausts its retries — so a transient outage (quota resets daily) self-heals, while a genuinely-stuck issue surfaces instead of burning quota forever.

## Approach

Two-part change, mirroring the existing sweeper family:

1. **Add a `workflow_dispatch` re-entry point** to `claude-implement-issue.yml` so implementation can be re-run for a given issue number without abusing issue state (no close/reopen). This is the Q1 decision: `workflow_dispatch` over close+reopen (which spams the timeline, notifies subscribers, and reopens deliberately-closed issues) and over `repository_dispatch` (invisible in the Actions UI, no manual-run button).

2. **Add `claude-orphan-issue-sweeper.yml`** — a mechanical (no Claude) cron sweeper whose decision logic lives in a unit-tested `backend/scripts/orphan_issue_sweep.py`. It re-dispatches (1) for each orphan under its retry cap, and opens a dedup'd alarm issue at the cap. All detection reads and label/alarm writes use the built-in `GITHUB_TOKEN`; the **single `gh workflow run` dispatch call uses `PR_AUTHOR_PAT`** — see the token note below.

3. **Add a 4th health job** to `claude-sweeper-health.yml` so the new sweeper is watched like the other three.

The sweeper itself invokes no Claude — orphan detection is entirely deterministic GitHub reads. Claude only re-enters via the re-dispatched `claude-implement-issue.yml`.

## Part 1 — `workflow_dispatch` re-entry on `claude-implement-issue.yml`

### Trigger
Add alongside the existing `issues` trigger:
```yaml
on:
  issues:
    types: [opened, reopened]
  workflow_dispatch:
    inputs:
      issue_number:
        description: "Issue number to (re-)implement"
        required: true
        type: string
```

### Issue-context shim (source from event OR input)
Every later reference to `github.event.issue.number` / `github.event.issue.title` must resolve from **either** the webhook payload or the dispatch input. Add a first job step that normalizes into env/outputs:

- `ISSUE_NUMBER` = `github.event.issue.number` (webhook) **or** `github.event.inputs.issue_number` (dispatch).
- `ISSUE_TITLE` = `github.event.issue.title` (webhook) **or** `gh issue view $ISSUE_NUMBER --json title -q .title` (dispatch).
- `AUTHOR_ASSOC` = `github.event.issue.author_association` (webhook) **or** `gh issue view $ISSUE_NUMBER --json authorAssociation -q .authorAssociation` (dispatch).

All prompt/branch/step references switch from `${{ github.event.issue.* }}` to the normalized env vars (`claude/issue-${ISSUE_NUMBER}`, PR body `Closes #${ISSUE_NUMBER}`, etc.).

### Safety gate must survive the dispatch path (SECURITY-CRITICAL)
The current job-level guard (line 40) is:
```yaml
if: contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)
```
`workflow_dispatch` has **no** `github.event.issue.author_association` (it evaluates to empty → the job would be **skipped**, not run — so the dispatch path is fail-safe by default, but that also means a naive job-level `if` blocks all dispatches). Resolution:

- Keep a job-level `if` that permits BOTH paths: `github.event_name == 'workflow_dispatch' || contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)`.
- Because `workflow_dispatch` can itself only be triggered by a user with **write access** to the repo (GitHub-enforced), the dispatch path is already trust-gated at the API layer. But defense-in-depth: the shim step **re-checks** `AUTHOR_ASSOC` for the dispatch path against the `["OWNER","MEMBER","COLLABORATOR"]` set and **fails the job closed** if the issue's author is untrusted. This prevents a write-access user (or the sweeper) from driving Claude on a *stranger's* issue body. The sweeper (Part 2) independently filters to trusted authors before ever dispatching, so this is a second line of defense.

### Terminal-state labels (feeds the sweeper's discriminator)
The shim step also clears the outcome labels `implement-failed` and `implement-blocked` at the start of every run (so they reflect the latest run, never a stale one), and on the webhook (`opened`/`reopened`) path — but NOT the dispatch path — clears any `implement-attempt-N` labels too (a fresh human open/reopen resets the sweeper's retry budget; a dispatch IS the sweeper's retry and must preserve the counter it just set). Two steps at the end of the job stamp the terminal state:
- `if: failure()` → create+add `implement-failed`.
- `if: success() && hashFiles('.pr-body.md') == ''` → create+add `implement-blocked` (the agent stopped on a blocker; skipped push/PR steps do not count as failures, so `success()` holds).

The success-with-PR path adds no label — the PR's existence is what the sweeper keys on there.

### No behavior change on the webhook happy path
The `opened`/`reopened` path produces the same implement→push→PR behavior as today; only the *source* of the issue fields is indirected through the shim, plus the new terminal-state labels.

## Part 2 — `claude-orphan-issue-sweeper.yml`

> Named `claude-orphan-issue-sweeper` for family consistency with the other `claude-*` sweepers even though it invokes no Claude directly — the prefix is the discovery convention, and the health watcher keys off `claude-*`.

### Triggers
- `schedule: cron: "40 * * * *"` — hourly at minute **40**. Verified-free minute: taken minutes are copilot-review=0, sweeper-health=17, fix-checks=30, resolve-conflicts=45, auto-merge=50. **40 collides with none.** (Cron-collision gotcha: a job fires AT its minute field regardless of the hour/step field, so the *minute* is what must be unique.) Hourly is ample — Claude quota resets on a daily cadence, so an orphan from a quota-out day just needs to be retried within a day; GitHub throttles sub-hourly cron on this low-activity repo anyway (memory `project_github-actions-ci.md`).
- `workflow_dispatch: {}` — manual kick for testing.

### Concurrency
`group: claude-orphan-issue-sweeper`, `cancel-in-progress: false` — serialize ticks so two runs never both dispatch the same issue.

### Permissions
`contents: read` (checkout + list branches via API), `issues: write` (bump attempt label, open/close alarm), `pull-requests: read` (detect linked PRs). NO `id-token`, NO Claude. `actions: write` is NOT granted to `GITHUB_TOKEN` here because the dispatch does not use it (see token note); everything the `GITHUB_TOKEN` does is a read plus issue/label writes.

### Token note — why the dispatch MUST use `PR_AUTHOR_PAT`, not `GITHUB_TOKEN` (correctness-critical)
GitHub's recursion guard means **events triggered using the built-in `GITHUB_TOKEN` do not create new workflow runs** — and this includes `workflow_dispatch`. A `gh workflow run claude-implement-issue.yml` authenticated with `GITHUB_TOKEN` would return success but **silently fail to start the implement run**, defeating the sweeper's entire purpose. (This is the same behavior documented in the auto-merge spec — "a merge with `GITHUB_TOKEN` does not cascade-trigger downstream workflows" — and in memory `project_tfstate-s3-bootstrap-pending.md`: "GITHUB_TOKEN merges suppress workflow runs". There it was harmless; here it is fatal.) Therefore the **dispatch step alone** authenticates with `PR_AUTHOR_PAT` (the existing Copilot-licensed PAT, which carries `actions:write` / `workflow` scope). All other `gh` calls (issue list, run list, branch/PR reads, label ops, alarm open/close) stay on `GITHUB_TOKEN`. This keeps the PAT's blast radius to the one call that genuinely needs it.

Bonus: re-dispatching via the PAT means the resulting implement run — and thus the PR it opens — is created under the Copilot-licensed identity, exactly as the webhook path already relies on for Copilot review to fire.

### Env
- `IMPLEMENT_WORKFLOW: claude-implement-issue.yml` — the dispatch target.
- `MAX_ATTEMPTS: "3"` — retry cap (Q2).
- `ATTEMPT_LABEL_PREFIX: "implement-attempt-"` — attempt counter encoded as label `implement-attempt-N`.
- `ORPHAN_STALE_LABEL: orphan-issue-stale` — dedup label for the cap-exhausted alarm issue.
- `TRUSTED_ASSOCIATIONS: OWNER,MEMBER,COLLABORATOR` — author-trust gate, matching the implement workflow.

### Auth
`GITHUB_TOKEN` for all detection reads and issue/label/alarm writes; `PR_AUTHOR_PAT` for the single `gh workflow run` dispatch step only (see token note).

### Orphan predicate (the correctness core — Q from §"Trigger discriminator")
An open issue is an **orphan to re-dispatch** iff ALL hold:

1. **State open**, and **author is trusted** (`authorAssociation ∈ TRUSTED_ASSOCIATIONS`). Never touch a stranger's issue.
2. **No linked PR**, open OR merged, that closes it. Check both the `claude/issue-N` branch's PRs and any PR whose body contains `Closes #N`. A merged PR means the issue is done (or about to auto-close); an open PR means it's in flight.
3. **No `claude/issue-N` branch** exists on the remote. If the agent committed but the push failed, the branch may be absent; its presence means work exists and a PR step is the right recovery, not a re-dispatch.
4. **Not labeled `implement-blocked`.** This is the discriminator that separates **silent death** from **deliberate stop** — implemented via labels the implement workflow stamps on the issue itself, NOT by correlating historical Actions runs (fragile: `gh run list` exposes only `displayTitle` = the issue title, not its number). The implement workflow is extended to record its own terminal state:
   - `if: failure()` (the job died red — quota-out, timeout, action error) → add label `implement-failed` (observability for humans; not load-bearing for the decision).
   - job succeeded but wrote no `.pr-body.md` (the agent ran, tests failed, it posted a blocker comment and stopped — the deliberate-stop path) → add label `implement-blocked`.
   - The issue-context shim clears BOTH labels at the START of every implement run, so the labels always reflect the *latest* run's outcome, never a stale one.

   Given that, an orphan is simply: no PR + no branch + **not** `implement-blocked`. That covers both the silent-death case (`implement-failed` or, if the webhook never fired at all, no implement labels) and correctly leaves the deliberate-stop case alone (`implement-blocked` present). No run→issue correlation needed for the decision.
5. **Not currently in progress** — best-effort guard: no implement run with status `queued`/`in_progress` whose `displayTitle` matches the issue title (avoid double-dispatching while a run is actively working). This is a soft guard only — with an hourly sweep cadence and the implement job's 30-min timeout, a re-dispatched run always completes before the next tick, so the race is negligible; the guard just trims obvious overlap.

The green-blocker-stop case is skipped automatically by criterion 4: it carries `implement-blocked`.

### Retry accounting (Q2 — label counter + alarm)
For each orphan:
- Read its current attempt count from the `implement-attempt-N` label (absent ⇒ 0).
- If `count < MAX_ATTEMPTS`:
  - Remove the old `implement-attempt-{count}` label, add `implement-attempt-{count+1}` (via `GITHUB_TOKEN`).
  - `GH_TOKEN=$PR_AUTHOR_PAT gh workflow run $IMPLEMENT_WORKFLOW -f issue_number=$N` to re-dispatch (PAT-authenticated — a `GITHUB_TOKEN` dispatch would silently no-op, see token note).
- If `count >= MAX_ATTEMPTS`:
  - Do NOT re-dispatch (stop burning quota on a stuck issue).
  - Open (or comment on, dedup by `ORPHAN_STALE_LABEL`) an alarm issue listing the exhausted issue(s), so a human investigates. Mirrors the other sweepers' alarm idiom.

### Recovery / self-clearing
When an issue finally gets an open or merged PR (criterion 2 fails), it's no longer an orphan and is skipped. As housekeeping, when the sweep sees an issue that now has a linked PR, it clears any lingering `implement-attempt-N` label so a future *reopen* starts fresh. The cap-exhausted alarm issue auto-closes when no issues remain at/over the cap (same recover-and-close pattern as `claude-sweeper-health.yml`).

### Decision core: `backend/scripts/orphan_issue_sweep.py`
Mirrors `sweeper_health.py`: the workflow shell gathers `gh`/REST JSON (open issues with `author_association`+labels, `claude/issue-*` branch refs, PRs by head branch, in-progress implement run titles), assembles a single "world" JSON, and pipes it to the script; the script is pure/deterministic and emits the action plan (JSON with four buckets: `dispatch` / `alarm` / `clear` / `skip`, each carrying the issue number and the exact label mutations). Unit-tested in `backend/tests/test_orphan_issue_sweep.py` covering: silent-death→dispatch, deliberate-stop(`implement-blocked`)→skip, in-progress→skip, has-open-PR→skip, has-merged-PR→(clear stale attempt labels), untrusted-author→skip, has-branch→skip, at-cap→alarm, under-cap→dispatch+attempt-label-bump, no-implement-labels-ever→dispatch, multiple stale attempt labels→remove-all+add-next. The workflow shell then executes the plan (label ops via `GITHUB_TOKEN`, `gh workflow run` via `PR_AUTHOR_PAT`, alarm open/close).

## Part 3 — health coverage (4th job on `claude-sweeper-health.yml`)

Add an `orphan-sweeper-health` job mirroring the existing three:
- Env: `ORPHAN_SWEEPER_WORKFLOW: claude-orphan-issue-sweeper.yml`, `ORPHAN_INTERVAL_MINUTES: "60"`, `ORPHAN_MAX_MISSED_TICKS: "3"` (⇒ 240-min grace window, same as the copilot/fix-checks watchers), dedup label `orphan-sweeper-stale`.
- Because the orphan sweeper is a single job whose run-level conclusion IS the health signal (like `auto-merge`, unlike `fix-checks`), reuse the `--mode scan` path: `last_run` = newest run of any conclusion (still ticking?), `last_success` = newest `success` run (scan logic still working?). A run that dispatches nothing but scans cleanly concludes `success` = healthy idle.
- Alarm/recover/close logic copied from the `auto-merge-health` job verbatim in shape, swapping the env-var names and labels.

## Autonomy / safety posture

**Dry-run first, then arm** — matching the auto-merge sweeper. Ship `claude-orphan-issue-sweeper.yml` with `env: DRY_RUN: "true"`. In dry-run the scan logs exactly which issues it WOULD re-dispatch (with the satisfied-predicate breakdown and current attempt count) and which it WOULD alarm on, but performs no `gh workflow run`, no label mutation, and no alarm issue. After the user confirms the predicate matches intent against real orphaned issues, flip `DRY_RUN` to `"false"` in a one-line follow-up commit. Re-dispatching implementation spends Claude quota, so a human-verifiable preview before it's live is warranted. `workflow_dispatch` input `dry_run` overrides the env for a single manual test run.

## Non-goals / YAGNI

- **Not** covering the deliberate-stop (green, blocker-comment) case — those are correct terminal states; re-running them loops on genuinely-broken specs. A human addresses the blocker comment and reopens.
- **Not** retrying non-trusted-author issues (safety).
- **No** per-issue exponential backoff beyond the flat cap — quota resets daily and the cadence is hourly, so a flat 3-attempt cap is sufficient; backoff is unneeded complexity (YAGNI).
- **No** new secrets — reuses the existing `GITHUB_TOKEN` and `PR_AUTHOR_PAT`.

## Open questions

None — all four design sections approved by the user (2026-07-02).
