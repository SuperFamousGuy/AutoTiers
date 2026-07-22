# Triage-dispatch throttle — design

Date: 2026-07-21
Status: approved (design), pending implementation plan

## Problem

The daily improvement recommender (`claude-improvement-recommender.yml`) files up
to `MAX_ISSUES` (currently 10) `recommendation` issues per run via `PR_AUTHOR_PAT`.
Because `claude-implement-issue.yml` fires on `issues: opened`, every filed issue
immediately launches a full autonomous Opus implement run. Ten issues therefore
launch ten concurrent implement jobs against a shared Claude subscription token,
which saturates the rolling five-hour quota window; jobs quota-die, the orphan
sweeper retries them, and open recommendation issues accumulate faster than they
close. The backlog piles up.

The goal is to decouple *filing* from *implementing*: the recommender should fill
a backlog, and a throttle should meter issues into the auto-implementer
highest-value-first, bounded by how many are already in flight.

## Constraints and decisions

These were settled during brainstorming and bound the design:

- **Pain to fix:** backlog pileup (open recs accumulate faster than they close).
- **Triage powers:** rank/prioritise only — no auto-closing or pruning.
- **Ranking consumer:** the implementer. Issues are worked in priority order,
  a bounded number at a time (this is throttling/gating).
- **Capacity model:** open-PR backpressure. The cap is a maximum number of open
  auto-implement PRs (`claude/issue-*` head branches); the dispatcher refills to
  the cap.
- **Cadence:** event-driven on PR close/merge (a slot frees), plus issue-open as
  a cold-start seed. No scheduled cron.
- **Ranking engine:** deterministic score-sort. The recommender already computes
  a per-candidate `score`; persist it and sort by it. No Claude agent in the
  loop — this keeps the throttle off the shared subscription quota entirely.

A deliberate consequence: despite the original request naming "an agent", the
throttle is a deterministic dispatcher, not a Claude-invoking job. That is a
feature — it adds no quota pressure to an already-fragile shared token.

## Two gotchas that shape the design

1. **Label race.** The recommender applies the `recommendation` label with
   `gh issue edit --add-label` *after* `gh issue create`, because `PR_AUTHOR_PAT`
   has historically lacked Issues:Write and GitHub silently drops the create-time
   `--label`. Therefore the label is NOT present on the issue when the
   `issues: opened` webhook fires. Any discriminator the implementer's
   `opened` handler tests must be present **at create time** — i.e. in the issue
   **body**, not a label.

2. **Orphan-sweeper collision.** `claude-orphan-issue-sweeper.yml` re-dispatches
   any trusted-author open issue with no branch, no linked PR, not blocked, and
   not in-progress. A throttled backlog issue matches that predicate exactly, so
   the sweeper would re-dispatch it and bypass the throttle. The sweeper must be
   taught to skip undispatched backlog issues.

## Components

### 1. `backend/scripts/improvement_recommend_select.py`

Include `score` in each returned dict. Today `select()` emits
`{title, area, body}` and drops the score; the dispatcher needs it persisted.
Keep the existing defensive `_score` semantics (missing/non-numeric → 0.0).

### 2. `.github/workflows/claude-improvement-recommender.yml`

- Embed an identity+score marker as the last line of each filed issue body:
  `<!-- autotiers:rec score=<N> -->`. This marker is present at create time, is
  included in every `issues` webhook payload, and is greppable. It is the
  reliable discriminator (see gotcha 1).
- File each recommendation issue with labels `recommendation` **and**
  `triage-queued`. `triage-queued` marks "in the backlog, not yet dispatched".

### 3. `.github/workflows/claude-implement-issue.yml`

Gate the `issues: opened`/`reopened` path to **skip** any issue whose body
contains the `autotiers:rec` marker. Because the marker lives in the body it is
reliably present in the webhook payload, sidestepping the label race. Net effect:

- Human-opened issues (no marker) still implement immediately — the fast path is
  preserved.
- Recommendation issues do not auto-implement on open; they wait for the
  dispatcher.
- The `workflow_dispatch` path is unchanged. It is how both the dispatcher and
  the orphan sweeper drive implementation.

### 4. NEW `.github/workflows/claude-triage-dispatch.yml`

Deterministic, invokes no Claude.

- **Triggers:** `pull_request: [closed]` (a slot may have freed),
  `issues: [opened, reopened]` (cold-start seed so an empty pipe can start),
  `workflow_dispatch` (manual recovery lever).
- **Concurrency:** a single serialised group so two ticks never double-dispatch.
- **Permissions:** `pull-requests: read`, `issues: write` (to remove the
  `triage-queued` label). Dispatch itself uses `PR_AUTHOR_PAT` via `GH_TOKEN`,
  because a `GITHUB_TOKEN` `workflow run` is suppressed by GitHub's recursion
  guard (same rule the orphan sweeper documents).
- **Logic** (pure decision core in `backend/scripts/triage_dispatch.py`,
  unit-tested, mirroring the orphan sweeper's world/plan split):
  1. `inflight` = count of open PRs whose head matches `claude/issue-*`.
  2. `slots = CAP - inflight`. If `slots <= 0`, do nothing.
  3. Gather open issues labelled `triage-queued`; parse `score` from each body
     marker; sort by score descending (stable tiebreak, e.g. lowest issue number
     first for determinism).
  4. Take the top `slots` issues. For each: remove the `triage-queued` label,
     then `gh workflow run claude-implement-issue.yml -f issue_number=<N>`
     authenticated as `PR_AUTHOR_PAT`.
- **`CAP`** is an env knob, default **2** (concurrency of 10 is what quota-died).

### 5. `.github/workflows/claude-orphan-issue-sweeper.yml`

Add one predicate to the decision core / world assembly: skip any issue still
labelled `triage-queued`. Such issues are intentional backlog, not orphans.

## Lifecycle

```
Filed       labels: recommendation + triage-queued
            → invisible to the implementer (body-marker gate) and to the orphan
              sweeper (triage-queued skip). Pure backlog.

Dispatched  triage-queued removed by the dispatcher
            → now an ordinary auto-implement issue. The existing orphan/retry
              machinery governs it from here, unchanged.
```

Dispatch is expressed as a label removal, which makes selection idempotent across
overlapping events: once `triage-queued` is gone the issue is never re-selected
by the dispatcher. If the subsequent implement run quota-dies before producing a
PR, the issue has no queued label, no branch, and no PR — so the orphan sweeper
correctly picks up the retry. The throttle hands off cleanly to machinery that
already exists.

## Data flow

```
recommender → backlog issues (scored, triage-queued)
     │
     ▼   [pull_request closed | issues opened]
dispatcher → slots free? → dispatch top-score issue(s), drop triage-queued
     │
     ▼
implementer → PR → auto-merge → PR closed → dispatcher (refill) …
```

## Error handling

- **Cold start / empty pipe:** with zero PRs open no `pull_request: closed` event
  ever fires, so the `issues: opened` seed trigger is what starts the pipe when a
  new recommendation is filed; `workflow_dispatch` is the manual restart.
- **Double dispatch:** prevented by the serialised concurrency group plus the
  label-removal idempotency.
- **Malformed / missing score marker:** treated as score 0 (sorts last); never
  crashes the run (mirrors the selector's defensive `_score`).
- **Backpressure stale window:** between label removal and the new PR appearing,
  the inflight PR count is momentarily low, but the removed label prevents
  re-selection, so no over-dispatch results.

## Testing

- `triage_dispatch.py` unit tests: slot math (`CAP - inflight`, `<= 0` → no-op),
  descending score sort with deterministic tiebreak, marker parsing (well-formed,
  absent, non-numeric), empty backlog, and `slots < len(backlog)` truncation.
- Manual end-to-end: file three marked issues with `CAP=2`; verify exactly two
  dispatch and one remains `triage-queued`; close one implement PR and verify the
  third dispatches on the `pull_request: closed` event.

## Explicitly out of scope

- No auto-closing, pruning, or deduping of the backlog beyond what the recommender
  already does.
- No Claude-agent ranking (deterministic score-sort only).
- No scheduled cron for the dispatcher (event-driven only).

The backlog *count* can still grow, because the recommender keeps filing up to
`MAX_ISSUES` per day while dispatch drains at PR-merge rate. That is accepted:
growth no longer burns quota (only dispatched issues do). `MAX_ISSUES` remains a
knob if intake throttling is wanted later.
