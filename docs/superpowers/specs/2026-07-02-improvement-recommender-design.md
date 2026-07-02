# Daily improvement recommender — Design

**Date:** 2026-07-02
**Status:** Designed; not yet implemented. Will ship `DRY_RUN: "true"` (files no issues) so the recommendations can be watched for a few days before arming, then a one-line flip arms it.
**Siblings / prior art:**
- `.github/workflows/claude-implement-issue.yml` — the Claude-invoking workflow this mirrors (`claude-code-action`, subscription oauth, `Task` subagents, PAT for the GitHub-side write). This is also the **downstream consumer**: the issues this job files are picked up by that workflow.
- `.github/workflows/claude-orphan-issue-sweeper.yml` — the thin-shell + unit-tested-Python decision-core idiom the issue-selection step mirrors, and the source of the PAT-vs-`GITHUB_TOKEN` dispatch rule.
- `backend/scripts/orphan_issue_sweep.py` — the decision-core idiom `improvement_recommend_select.py` mirrors.
- `.claude/agents/autotiers-{researcher,designer,engineer}.md` — the three specialists this job orchestrates.

## Problem

AutoTiers improves only reactively: a human notices something, files an issue, and (via `claude-implement-issue`) it becomes a PR. Nothing proactively looks at the app and the outside world — new fantasy-football rankings we could benchmark our tiers against, new library/tooling versions, evolving UX best practices, or latent correctness/perf/maintainability debt in our own code — and turns those observations into actionable work.

## Goal

A scheduled daily job in which three existing specialists — `autotiers-researcher`, `autotiers-designer`, `autotiers-engineer` — examine both the current app and newly-available external inputs, then file the highest-value improvement recommendations as GitHub issues. Those issues flow directly into the existing `claude-implement-issue` automation (the user's explicit choice: a full autonomous improvement loop), so a recommendation can become a merged PR with no human in the middle.

## Decisions (locked with the user)

- **Automation coupling: full autonomous loop.** Filed issues are created so `claude-implement-issue` fires on them immediately — each recommendation can become a PR unsupervised. (See *Quota / autonomy posture* for why this ships behind `DRY_RUN`.)
- **Volume: top 5 per run.** After dedup, at most the 5 highest value/effort recommendations are filed per daily run (`MAX_ISSUES`).
- **Scope: all four.** Every run covers (1) external FF rankings vs ours, (2) new tech/deps, (3) UX best practices, (4) app-internals audit.

## Approach

One daily GitHub Actions workflow, structured exactly like the repo's Claude-invoking + PAT-write split:

1. **`claude-code-action`** runs a top-level orchestrator prompt that dispatches the three specialists via `Task`, synthesizes their candidates, dedups against currently-open recommendations, ranks, selects the top 5, and writes `recommendations.json`. The agent creates **no** issues itself.
2. A **deterministic shell step, authenticated as `PR_AUTHOR_PAT`**, reads `recommendations.json` and files the issues.

Rejected alternatives:
- **Three workflows (one per agent), each filing its own issues** — 3× subscription-quota sessions per day, a dedup race across three independent runs, and noisier output. Rejected.
- **`/schedule` cloud routine instead of a workflow** — lives off-repo, is unversioned, and breaks the "every automation is reviewable in git" convention every other sweeper follows. Rejected.

## Architecture

### File: `.github/workflows/claude-improvement-recommender.yml`

**Trigger**
```yaml
on:
  schedule:
    - cron: "10 8 * * *"   # daily 08:10 UTC; minute 10 is free of every
                           # existing sweeper minute (0/17/30/40/45/50).
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Override DRY_RUN for a single manual run (true/false)."
        required: false
        type: string
```

**Concurrency:** `group: claude-improvement-recommender`, `cancel-in-progress: false` — never let two ticks file overlapping issues.

**Permissions:** `contents: read`, `issues: write` (dedup reads + the built-in-token label bootstrap), `id-token: write` (the action mints its OIDC token). The authoritative issue *creation* uses `PR_AUTHOR_PAT`, not the job's `GITHUB_TOKEN` — see below.

**Env (ship-safe defaults):**
```yaml
env:
  DRY_RUN: "true"            # file nothing until a human has watched the output
  MAX_ISSUES: "5"
  REC_LABEL: "recommendation"
  LOOKBACK_DAYS: "30"        # closed-issue window for dedup
```

**Steps**

1. `actions/checkout@v4` with `token: ${{ secrets.PR_AUTHOR_PAT }}`, `fetch-depth: 0`.
2. `setup-python` + `setup-node` + install backend/web deps — so the `engineer`/`designer` subagents can run tests and inspect the live app, not merely read source. Mirrors `claude-implement-issue`'s toolchain pre-provisioning.
3. **Dedup gather** (`GITHUB_TOKEN`): collect open issues plus issues closed within `LOOKBACK_DAYS` that carry `REC_LABEL`, into `existing_recs.json` (`[{number, title, body, state}]`). Handed to the agent so a standing recommendation is not re-proposed every day.
4. **`anthropics/claude-code-action@v1`**:
   - `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}` (subscription quota, same as implement-issue).
   - `claude_args: --model claude-opus-4-8 --max-turns 120 --allowedTools Edit,Write,Read,Glob,Grep,Bash,Task,WebSearch,WebFetch`.
   - Prompt (spec, not verbatim): *You are the AutoTiers improvement recommender. Dispatch three specialists via `Task` and give each its lane:*
     - `autotiers-researcher` — compare our tier/ranking output against newly-available public rankings/ADP (FantasyPros, ESPN, etc.) and flag divergences worth acting on; also surface new tech/deps/techniques relevant to the stack.
     - `autotiers-designer` — audit the existing link→generate→export flow against current UX best practices and new patterns.
     - `autotiers-engineer` — audit app internals for correctness, performance, and maintainability improvements.
   - *Collect every candidate. Read `existing_recs.json` and drop anything that duplicates an open or recently-closed recommendation. Rank by value/effort and select the top `MAX_ISSUES`. Write `recommendations.json` at repo root: `[{title, area, body}]`, where each `body` is an auto-implement-ready spec — problem, proposed change, acceptance criteria, affected files — and each `title` is one concise line. Do NOT create issues; a later step does that.*
5. **File issues** (`PR_AUTHOR_PAT`, gated so dry-run and empty/malformed JSON file nothing):
   - Validate `recommendations.json` parses to a list; else log and exit 0.
   - For up to `MAX_ISSUES` entries: `gh issue create --label "$REC_LABEL"` authenticated as `PR_AUTHOR_PAT`.
   - `DRY_RUN=true` → print the planned title/area for each and create nothing.

### Decision core: `backend/scripts/improvement_recommend_select.py`

To keep dedup + ranking + capping deterministic and unit-testable (the repo's established pattern), extract selection into a small script the agent calls: input = candidate list + `existing_recs.json` + `MAX_ISSUES`; output = the final `recommendations.json`. The agent still *generates* candidates; the script decides which survive. Covered by a unit test (dup suppression, cap enforcement, empty-input safety).

## Why `PR_AUTHOR_PAT` files the issues (correctness-critical)

The whole point is that filed issues auto-implement. Two GitHub facts force the PAT:

1. **Recursion guard.** An issue created with the built-in `GITHUB_TOKEN` does **not** trigger any workflow (`issues: opened` included) — so `claude-implement-issue` would never fire. (Same behavior the orphan sweeper documents for `workflow_dispatch`, and the tfstate memory records for merges.)
2. **Trusted-author gate.** `claude-implement-issue` only runs for `author_association ∈ {OWNER, MEMBER, COLLABORATOR}`. An App/bot-authored issue resolves to `NONE` and is refused.

`PR_AUTHOR_PAT` is a real user credential: it both fires the webhook and passes the trusted-author gate. Exactly the reason the orphan sweeper dispatches via PAT rather than `GITHUB_TOKEN`.

## Quota / autonomy posture

Full loop + top-5/day means a single arming can, at steady state, add **up to 5 `claude-implement-issue` runs per day** — each spawning a PR, a Copilot review, and an auto-merge — *plus* this recommender's own multi-agent session. On subscription quota (`CLAUDE_CODE_OAUTH_TOKEN`, personal Pro/Max) that is heavy, and can starve the auto-implement queue — the precise failure the orphan sweeper exists to catch.

Mitigation, all in-design:
- Ships `DRY_RUN: "true"`: the daily run produces `recommendations.json` and logs the plan but files nothing, so the *quality* of recommendations can be judged for several days before any issue is created.
- Arm gradually: flip `DRY_RUN` to `"false"` first with `MAX_ISSUES: "1"`, watch a few days of the full loop, then ramp toward 5.
- Dedup + the `recommendation` label keep the tracker legible and let the orphan sweeper / health tooling reason about this job's output.

## Testing

- **Unit:** `improvement_recommend_select.py` — dedup suppresses a candidate matching an open rec; cap trims to `MAX_ISSUES`; empty/garbage input yields `[]` without raising.
- **Dry-run integration:** `workflow_dispatch` with `dry_run=true` → assert `recommendations.json` is well-formed and **no** issue was created.
- **Arming smoke (manual):** one `dry_run=false` run with `MAX_ISSUES=1`, confirm exactly one `recommendation`-labelled issue is filed by the PAT identity and that `claude-implement-issue` fires on it.

## Error handling

- Malformed/empty/absent `recommendations.json` → file nothing, log, exit 0 (a bad generation must never fail the schedule).
- Job `timeout-minutes` bounds the multi-agent session.
- Dry-run is the default and files nothing.

## Out of scope for v1 (flagged, deferred)

- A `claude-sweeper-health.yml` job that alarms when this daily run silently fails — add after the loop is armed and trusted.
- Hybrid confidence-based coupling (auto-implement only low-risk recs) — the user chose the full loop; revisit if quota proves too tight.
