# Auto-resolve PR merge conflicts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fully-agentic cron sweeper that resolves merge conflicts on open same-repo PRs end-to-end.

**Architecture:** A single GitHub Actions workflow `claude-resolve-conflicts.yml`, a near-clone of the existing `claude-fix-pr-checks.yml`. A cheap Stage-1 `scan` job finds open same-repo non-draft PRs whose `mergeable == CONFLICTING` and emits a matrix; an expensive Stage-2 `resolve` job merges the base branch into the PR head, resolves conflicts via the `resolve-merge-conflicts` skill, commits, and pushes as the PAT. Always-push + flag-uncertain; no local test gate (the fix-checks sweeper heals any post-merge breakage).

**Tech Stack:** GitHub Actions, `gh` CLI, `anthropics/claude-code-action@v1`, the existing `.claude/skills/resolve-merge-conflicts` skill. Subscription auth (`CLAUDE_CODE_OAUTH_TOKEN`) + `PR_AUTHOR_PAT`.

**Note on methodology:** the deliverable is one declarative YAML artifact, not application code, so there is no unit-test/TDD loop. "Verification" = `actionlint`, structural `grep` assertions on the file, and a `workflow_dispatch` dry-run against a deliberately-conflicted PR. The file is built in one task (an incomplete intermediate YAML would fail to lint and give a false signal), then verified.

**Reference files (read before starting):**
- `.github/workflows/claude-fix-pr-checks.yml` — the template; copy its structure, comments style, deferred-stamp trick, and PAT-push step.
- `.github/workflows/claude-address-copilot-review.yml` — the other sweeper; cron-offset rationale lives here.
- `.claude/skills/resolve-merge-conflicts/SKILL.md` — the skill the agent invokes.
- `docs/superpowers/specs/2026-06-19-auto-resolve-pr-conflicts-design.md` — the approved spec.

---

### Task 1: Create the workflow file

**Files:**
- Create: `.github/workflows/claude-resolve-conflicts.yml`

- [ ] **Step 1: Write the complete workflow file**

Create `.github/workflows/claude-resolve-conflicts.yml` with EXACTLY this content:

```yaml
name: claude-resolve-conflicts

# Cron-driven sweeper. Auto-resolves MERGE CONFLICTS on every open same-repo PR,
# fully agentic (zero manual approvals).
#
# WHY CRON, NOT an event trigger:
# Same constraint the other two sweepers documented
# (claude-fix-pr-checks.yml / claude-address-copilot-review.yml):
#  1. BOT-ACTOR GATING: a workflow run triggered by a bot actor
#     (github-actions[bot] / claude[bot]) is parked in `action_required` awaiting
#     manual approval, so an event-driven reaction can never be hands-off.
#  2. LOOP: reacting to PR-update events re-fires on the resolution push's own
#     branch update, with no natural bound.
# A SCHEDULED (cron) workflow runs as the repo/owner identity and is NOT
# approval-gated -> fully agentic. We poll an idempotent work-signal instead of
# reacting: "open same-repo non-draft PR whose mergeable == CONFLICTING". Once
# resolved the PR is MERGEABLE and the next tick ignores it; if the base moves
# and reconflicts, that is legitimate new work picked up on a later tick.
#
# AUTONOMY: always-push + flag-uncertain. The agent resolves every hunk (best-
# guess semantic merges), pushes, and posts an uncertainty log as a PR comment
# for after-the-fact human review. NO local test gate: after the push the PR's
# own tests.yml re-runs, and the claude-fix-pr-checks sweeper heals any breakage.
#
# AUTH (mirrors the other sweepers):
#  - CLAUDE_CODE_OAUTH_TOKEN: subscription auth for claude-code-action.
#  - PR_AUTHOR_PAT: Copilot-licensed PAT with `workflows` + `contents:write`. The
#    agent COMMITS ONLY; a dedicated push step re-seats git's transport with the
#    PAT because the action's minted OIDC App token is refused write access to
#    `.github/workflows/` and a conflict can occur in a workflow file.
#
# TERMINATION (MAX_PASSES=3): per-PR incrementing `claude-resolve-conflicts-pass-K`
# label, stamped right before Claude runs. The scan counts existing labels; at
# >=MAX_PASSES the PR is skipped (until a human removes the labels to re-arm). A
# one-time `claude-resolve-conflicts-capped` label guards the cap-notice comment.
#
# Design: docs/superpowers/specs/2026-06-19-auto-resolve-pr-conflicts-design.md

on:
  schedule:
    # Every 2 hours at minute 45. OFFSET from the other scheduled workflows so no
    # two tick in the same minute and double-spend the shared subscription quota:
    # copilot sweeper = minute 0 (hourly), fix-checks sweeper = minute 30
    # (hourly), sweeper-health = minute 17 (hourly). Minute 45 collides with none
    # of them. (Do NOT use "0 */2 * * *" — minute 0 collides with the hourly
    # copilot sweeper on every even hour.) Conflicts are less time-sensitive than
    # failing checks, so a 2-hourly cadence is fine; the work-signal is
    # idempotent, so a missed tick is just picked up by the next one. (GitHub
    # throttles high-frequency cron on low-activity repos anyway.)
    - cron: "45 */2 * * *"
  workflow_dispatch: {} # manual kick for testing

concurrency:
  # Serialize ticks so two overlapping cron runs never both read the same prior
  # pass counts and double-spend the budget. cancel-in-progress:false lets an
  # in-flight sweep finish (it may be mid-push) rather than be killed.
  group: claude-resolve-conflicts-sweeper
  cancel-in-progress: false

permissions:
  contents: write
  pull-requests: write
  issues: write # PR labels are issue labels in GitHub's model
  id-token: write # claude-code-action mints its GitHub token via OIDC

env:
  # Max automatic Claude resolution attempts per PR. Bounds token spend and
  # guarantees termination even if an attempt fails to clear the conflict.
  MAX_PASSES: 3

jobs:
  # STAGE 1 (cheap): scan for eligible PRs. Pure gh, no toolchain, no Claude.
  # Emits a JSON array of eligible PR numbers as `matrix` and a boolean `any`.
  # When `any` is false the resolve job is skipped entirely.
  scan:
    name: scan for PRs with merge conflicts
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      matrix: ${{ steps.scan.outputs.matrix }}
      any: ${{ steps.scan.outputs.any }}
    steps:
      - name: Find eligible PRs
        id: scan
        env:
          GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail

          # Candidate PRs: open, same-repo, non-draft. Fork PRs can't be pushed
          # with our PAT; draft PRs are WIP.
          candidates="$(gh pr list --repo "$REPO" --state open --limit 100 \
            --json number,isCrossRepository,isDraft \
            --jq '[.[] | select(.isCrossRepository == false and .isDraft == false) | .number]')"
          echo "candidate PRs (open same-repo non-draft): $candidates"

          eligible='[]'
          for pr in $(echo "$candidates" | python3 -c 'import json,sys; print(" ".join(str(n) for n in json.load(sys.stdin)))'); do
            # `mergeable` is computed asynchronously by GitHub: MERGEABLE |
            # CONFLICTING | UNKNOWN. A per-PR `gh pr view` returns the current
            # value (and nudges computation). UNKNOWN => still settling, skip
            # this tick (settle guard); a real gh/API failure also yields empty,
            # which we default to UNKNOWN and log a ::warning:: so a silently
            # broken scan is visible rather than looking like "nothing to do".
            mergeable="$(gh pr view "$pr" --repo "$REPO" --json mergeable --jq '.mergeable' 2>/tmp/gh-merge-err || true)"
            if [ -z "$mergeable" ]; then
              echo "::warning::PR #$pr: 'gh pr view' returned no mergeable value (possible gh/API failure); treating as UNKNOWN. stderr: $(tr '\n' ' ' < /tmp/gh-merge-err)"
              mergeable="UNKNOWN"
            fi
            rm -f /tmp/gh-merge-err

            if [ "$mergeable" = "UNKNOWN" ]; then
              echo "PR #$pr: mergeable state still settling; skip this tick."
              continue
            fi
            if [ "$mergeable" != "CONFLICTING" ]; then
              echo "PR #$pr: no merge conflict (mergeable=$mergeable)."
              continue
            fi

            # Count prior Claude passes; at/over cap the PR is not eligible.
            passes="$(gh pr view "$pr" --repo "$REPO" --json labels \
              --jq '[.labels[].name | select(startswith("claude-resolve-conflicts-pass-"))] | length')"
            echo "PR #$pr: CONFLICTING, prior passes=$passes"

            if [ "$passes" -lt "$MAX_PASSES" ]; then
              eligible="$(echo "$eligible" | python3 -c "import json,sys; a=json.load(sys.stdin); a.append($pr); print(json.dumps(a))")"
            else
              # Cap reached AND still conflicting: post a one-time notice, guarded
              # by the claude-resolve-conflicts-capped label.
              already="$(gh pr view "$pr" --repo "$REPO" --json labels \
                --jq '[.labels[].name | select(. == "claude-resolve-conflicts-capped")] | length')"
              if [ "$already" -eq 0 ]; then
                gh label create "claude-resolve-conflicts-capped" --repo "$REPO" \
                  --color b60205 --description "Auto-resolve-conflicts cap (MAX_PASSES) reached; needs human" \
                  2>/dev/null || true
                gh pr edit "$pr" --repo "$REPO" --add-label "claude-resolve-conflicts-capped"
                gh pr comment "$pr" --repo "$REPO" --body \
                  "Automated conflict-resolution passes hit the cap (MAX_PASSES=${MAX_PASSES}) and the PR is still conflicting. A human should resolve it, then remove the \`claude-resolve-conflicts-pass-*\` labels to re-arm the sweeper."
                echo "PR #$pr: capped; posted one-time notice."
              else
                echo "PR #$pr: capped; notice already posted, skipping."
              fi
            fi
          done

          echo "eligible PRs: $eligible"
          echo "matrix=$eligible" >> "$GITHUB_OUTPUT"
          if [ "$(echo "$eligible" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')" -gt 0 ]; then
            echo "any=true" >> "$GITHUB_OUTPUT"
          else
            echo "any=false" >> "$GITHUB_OUTPUT"
          fi

  # STAGE 2 (expensive): one job per eligible PR. Skipped wholesale when scan
  # found nothing, so the toolchain + Claude only run when there is real work.
  resolve:
    name: resolve conflicts (PR #${{ matrix.pr }})
    needs: scan
    if: needs.scan.outputs.any == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      # Sequential so passes are reserved one PR at a time and the shared
      # subscription quota is not hit by N concurrent Claude runs.
      max-parallel: 1
      fail-fast: false
      matrix:
        pr: ${{ fromJson(needs.scan.outputs.matrix) }}
    steps:
      # FIRST: decide whether there is budget, but DO NOT stamp yet. The pass-
      # label stamp is deferred to just before the Claude step so an infra
      # failure in checkout/setup does not consume a pass without an attempt.
      - name: Count prior passes (decide budget)
        id: budget
        env:
          GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}
          PR: ${{ matrix.pr }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          prior="$(gh pr view "$PR" --repo "$REPO" --json labels \
            --jq '[.labels[].name | select(startswith("claude-resolve-conflicts-pass-"))] | length')"
          echo "prior passes: $prior  cap: $MAX_PASSES"
          if [ "$prior" -ge "$MAX_PASSES" ]; then
            echo "Cap reached ($prior >= $MAX_PASSES); no budget left. Stopping."
            echo "has_budget=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          next=$((prior + 1))
          echo "Budget available: pass $next of $MAX_PASSES (label stamped later)."
          echo "next_label=claude-resolve-conflicts-pass-${next}" >> "$GITHUB_OUTPUT"
          echo "has_budget=true" >> "$GITHUB_OUTPUT"

      - name: Resolve PR head + base refs
        id: refs
        if: steps.budget.outputs.has_budget == 'true'
        env:
          GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}
          PR: ${{ matrix.pr }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          head="$(gh pr view "$PR" --repo "$REPO" --json headRefName --jq '.headRefName')"
          base="$(gh pr view "$PR" --repo "$REPO" --json baseRefName --jq '.baseRefName')"
          echo "head ref: $head   base ref: $base"
          echo "head=$head" >> "$GITHUB_OUTPUT"
          echo "base=$base" >> "$GITHUB_OUTPUT"

      - name: Checkout PR head
        if: steps.budget.outputs.has_budget == 'true'
        uses: actions/checkout@v4
        with:
          # Push resolution commits under the Copilot-seated account so they stay
          # attributable. NOTE: this persisted credential is overwritten by
          # claude-code-action's minted OIDC App token, so the authoritative push
          # is the dedicated PAT step below.
          token: ${{ secrets.PR_AUTHOR_PAT }}
          ref: ${{ steps.refs.outputs.head }}
          fetch-depth: 0 # full history required to merge the base branch

      # Lightweight toolchain — ONLY so the resolve-merge-conflicts skill can
      # regenerate a conflicted lockfile (rm package-lock.json && npm install).
      # We deliberately do NOT install full deps and do NOT run tests (the fix-
      # checks sweeper owns post-merge breakage). Versions match tests.yml.
      - uses: actions/setup-node@v4
        if: steps.budget.outputs.has_budget == 'true'
        with:
          node-version: "20"
      - uses: actions/setup-python@v5
        if: steps.budget.outputs.has_budget == 'true'
        with:
          python-version: "3.14"

      # Stamp the pass label NOW — after checkout/setup and right before Claude
      # runs/pushes. Preserves the termination invariant (label exists before the
      # push) while ensuring an earlier infra failure does not burn a pass.
      # Adding an already-present label is a no-op, so a retried run can't
      # double-count.
      - name: Stamp pass label (reserve budget)
        if: steps.budget.outputs.has_budget == 'true'
        env:
          GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}
          PR: ${{ matrix.pr }}
          REPO: ${{ github.repository }}
          LABEL: ${{ steps.budget.outputs.next_label }}
        run: |
          set -euo pipefail
          gh label create "$LABEL" --repo "$REPO" \
            --color ededed --description "Automated Claude pass resolving PR merge conflicts" \
            2>/dev/null || true
          gh pr edit "$PR" --repo "$REPO" --add-label "$LABEL"
          echo "Reserved budget: stamped $LABEL."

      - name: Resolve conflicts (commit only, do not push)
        if: steps.budget.outputs.has_budget == 'true'
        uses: anthropics/claude-code-action@v1
        env:
          # Attribute any `gh` calls the agent makes to the Copilot-seated PAT
          # account. gh prefers GH_TOKEN over GITHUB_TOKEN, so this wins.
          GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          prompt: |
            PR #${{ matrix.pr }} in this repository has MERGE CONFLICTS with its
            base branch. Resolve them end-to-end on the PR head branch
            (${{ steps.refs.outputs.head }}), with no further human input.

            CRITICAL — read this before you start. Do NOT `git push`. A conflict
            can occur in a file under `.github/workflows/`, and a `git push` from
            inside this action goes out as the action's GitHub App OIDC token
            (the action re-seats git's credential after checkout), which GitHub
            REFUSES to let write workflow files. A later workflow step pushes the
            branch authenticated as the Copilot-licensed PAT. So: commit ONLY;
            never push.

            Process:
            1. Surface the conflicts: run
                 `git fetch origin ${{ steps.refs.outputs.base }}`
               then
                 `git merge origin/${{ steps.refs.outputs.base }}`
               The merge will stop with conflicts.
            2. Invoke the `resolve-merge-conflicts` skill and resolve EVERY
               conflicted hunk. Make best-guess semantic merges; do NOT change
               code beyond what each hunk requires. The merge commit must be the
               ONLY commit you create.
            3. THIS IS CI: ignore any local `/Users/...` paths or `venv/bin/`
               prefixes in the skill, and do NOT run the test suite — that is the
               fix-checks sweeper's job. The skill's LOCKFILE step DOES apply: if
               a lockfile conflicts, regenerate it (e.g. `cd web && rm
               package-lock.json && npm install`); node and python are installed.
            4. Verify NO conflict markers remain (the skill's grep step).
            5. If you CANNOT resolve the conflicts (a hunk needs a human product
               decision, or the merge surfaces NO conflicts because the state was
               stale): do NOT commit, do NOT push, do NOT write the flag. Post a
               PR comment explaining what you found, then STOP.
            6. If resolved: commit the merge (default merge message is fine, or
               `chore: resolve merge conflicts with ${{ steps.refs.outputs.base }}`).
               Leave it as the current branch HEAD. Do NOT push — a later step
               pushes it as the PAT. Then write a sentinel file at the repo root
               named `.resolved.flag` (any content) so the push step knows a
               resolution was committed. Do NOT commit `.resolved.flag`. Do NOT
               open a new pull request.
            7. Post a PR comment containing the skill's uncertainty log (the
               "Uncertain resolutions" section) so a human can review the risky
               hunks after the fact. If every hunk was high-confidence, post a
               short comment saying conflicts were resolved with no uncertain
               hunks.

            The repo's `.claude/skills/` and `.claude/agents/` are present in the
            checkout — use them.
          claude_args: |
            --model claude-opus-4-8
            --max-turns 80
            --allowedTools Edit,Write,Read,Glob,Grep,Bash,Task

      # Push the agent's merge commit, AUTHENTICATED as PR_AUTHOR_PAT, in a step
      # the action cannot override. `-c http...extraheader=` clears the App-token
      # Authorization header the action persisted; the inline token in the remote
      # URL authenticates the push as the PAT (workflows + contents scope). Gated
      # on `.resolved.flag` so a no-resolution run pushes nothing.
      - name: Push resolved branch
        if: steps.budget.outputs.has_budget == 'true' && hashFiles('.resolved.flag') != ''
        env:
          PAT: ${{ secrets.PR_AUTHOR_PAT }}
          REF: ${{ steps.refs.outputs.head }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          # `-c` is a git-level option and MUST precede the `push` subcommand.
          git -c http.https://github.com/.extraheader= push \
            "https://x-access-token:${PAT}@github.com/${REPO}.git" \
            "HEAD:refs/heads/${REF}"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/claude-resolve-conflicts.yml
git commit -m "feat: add claude-resolve-conflicts sweeper"
```

---

### Task 2: Lint the workflow

**Files:**
- Verify: `.github/workflows/claude-resolve-conflicts.yml`

- [ ] **Step 1: Run actionlint**

Run: `actionlint .github/workflows/claude-resolve-conflicts.yml`
(If `actionlint` is not installed: `brew install actionlint`, or skip to the YAML-parse fallback below.)
Expected: no output (exit 0). actionlint also runs `shellcheck` on the `run:` blocks — fix any SC warnings it surfaces.

- [ ] **Step 2: YAML-parse fallback (if actionlint unavailable)**

Run:
```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/claude-resolve-conflicts.yml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 3: Commit any lint fixes (if the file changed)**

```bash
git add .github/workflows/claude-resolve-conflicts.yml
git commit -m "fix: actionlint cleanups on claude-resolve-conflicts"
```

---

### Task 3: Structural assertions

Confirm the file actually wires the pieces the spec requires. These greps each must print a match.

**Files:**
- Verify: `.github/workflows/claude-resolve-conflicts.yml`

- [ ] **Step 1: Work-signal is CONFLICTING (not a check pattern)**

Run: `grep -n 'mergeable' .github/workflows/claude-resolve-conflicts.yml`
Expected: matches on the `gh pr view ... --json mergeable` scan line and the CONFLICTING comparison.

- [ ] **Step 2: Base ref is read dynamically, never hardcoded**

Run: `grep -n 'baseRefName\|steps.refs.outputs.base' .github/workflows/claude-resolve-conflicts.yml`
Expected: matches on the refs step and the merge command in the prompt.
Run: `grep -n 'origin/main' .github/workflows/claude-resolve-conflicts.yml`
Expected: NO matches (base must come from `baseRefName`).

- [ ] **Step 3: Push is gated on the resolution sentinel**

Run: `grep -n "hashFiles('.resolved.flag')" .github/workflows/claude-resolve-conflicts.yml`
Expected: one match on the `Push resolved branch` step's `if:`.

- [ ] **Step 4: Termination labels are namespaced and capped**

Run: `grep -n 'claude-resolve-conflicts-pass-\|MAX_PASSES\|claude-resolve-conflicts-capped' .github/workflows/claude-resolve-conflicts.yml`
Expected: matches in scan (count + cap notice), budget step, and stamp step.

- [ ] **Step 5: Cron is offset from the other two sweepers**

Run: `grep -rn 'cron:' .github/workflows/claude-*.yml`
Expected minute fields, all distinct: `claude-address-copilot-review.yml` = `"0 * * * *"` (min 0), `claude-sweeper-health.yml` = `"17 * * * *"` (min 17), `claude-fix-pr-checks.yml` = `"30 * * * *"` (min 30), `claude-resolve-conflicts.yml` = `"45 */2 * * *"` (min 45). No two sweepers share a minute, so they never tick together and double-spend quota. (No commit; verification only.)

---

### Task 4: Live dry-run via workflow_dispatch

Scheduled workflows only ever run from the **default branch**, but `workflow_dispatch` can run a workflow from any branch via `--ref`. This task exercises the real round-trip before merge.

**Files:** none (operational).

- [ ] **Step 1: Push the branch and open the PR**

```bash
git push -u origin feat/auto-resolve-pr-conflicts
gh pr create --fill --base main --head feat/auto-resolve-pr-conflicts
```

- [ ] **Step 2: Create a deliberately-conflicting test PR**

Pick (or create) a throwaway branch that edits the same line as `main` differently so GitHub marks it `CONFLICTING`. Confirm the state:
```bash
gh pr view <TEST_PR> --json mergeable --jq '.mergeable'
```
Expected: `CONFLICTING` (re-run until it leaves `UNKNOWN`).

- [ ] **Step 3: Dispatch the sweeper from this branch**

```bash
gh workflow run claude-resolve-conflicts.yml --ref feat/auto-resolve-pr-conflicts
gh run watch "$(gh run list --workflow=claude-resolve-conflicts.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected: `scan` finds the test PR; `resolve` merges base, resolves, pushes; the test PR gains a `claude-resolve-conflicts-pass-1` label, an uncertainty comment, and is now `MERGEABLE`.

- [ ] **Step 4: Confirm skip paths**

- A `MERGEABLE` PR and a fork PR are both absent from the `scan` job's `eligible PRs:` log line.
- Re-dispatch twice more against the same still-conflicting test PR (if it reconflicts) to confirm the `MAX_PASSES=3` cap posts the one-time `claude-resolve-conflicts-capped` notice and then skips.

- [ ] **Step 5: Clean up the test PR/branch** once the round-trip is confirmed.

---

## Self-Review

**Spec coverage:**
- Cron-not-event + offset cadence → Task 1 (`on.schedule`), Task 3 Step 5. ✓
- Work-signal `CONFLICTING` + UNKNOWN settle guard + fork/draft skip → Task 1 scan, Task 3 Step 1. ✓
- Always-push + flag-uncertain, no test gate → Task 1 prompt steps 6-7. ✓
- Deferred pass-stamp + MAX_PASSES termination + one-time cap notice → Task 1 budget/stamp/scan, Task 3 Step 4. ✓
- Base from `baseRefName`, never hardcoded → Task 1 refs step, Task 3 Step 2. ✓
- Lightweight lockfile toolchain, no full deps/tests → Task 1 setup-node/setup-python + prompt step 3. ✓
- PAT push gated on `.resolved.flag` → Task 1 push step, Task 3 Step 3. ✓
- No new secrets / reuse existing → Task 1 uses `CLAUDE_CODE_OAUTH_TOKEN` + `PR_AUTHOR_PAT` only. ✓
- Verification (actionlint, dispatch dry-run, skip + cap paths) → Tasks 2-4. ✓

**Placeholder scan:** the only `<TEST_PR>` / `<TEST_BRANCH>` placeholders are in the operational dry-run task where the value is environment-specific by nature. No code placeholders.

**Type/name consistency:** label prefix `claude-resolve-conflicts-pass-`, sentinel `.resolved.flag`, step ids `budget`/`refs`, outputs `head`/`base`/`has_budget`/`next_label` are used consistently across scan, budget, refs, stamp, Claude prompt, and push steps. ✓
