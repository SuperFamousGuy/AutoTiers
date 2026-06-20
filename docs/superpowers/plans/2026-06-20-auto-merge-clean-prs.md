# Auto-merge clean PRs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fully-agentic cron sweeper that AUTO-MERGES open PRs satisfying all six merge predicates (CI green, mergeable, Copilot-reviewed, no unresolved threads, quiet 24h, bot-or-collaborator author).

**Architecture:** A single GitHub Actions workflow `claude-auto-merge.yml`, modeled on the **pure-mechanical** `claude-sweeper-health.yml` (NOT the Claude+PAT sweepers). One `scan` job: pure `gh`/GraphQL + `python3` for date math, evaluates the six predicates per open PR, and merges each eligible PR via `gh pr merge --squash --delete-branch`. Ships `DRY_RUN: "true"` (report-only) so the predicate can be sanity-checked against real PRs before the merge is armed. No `claude-code-action`, no `PR_AUTHOR_PAT`, no new secrets.

**Tech Stack:** GitHub Actions, `gh` CLI, one GraphQL query per PR, `GITHUB_TOKEN`. No Claude.

**Note on methodology:** the deliverable is one declarative YAML artifact, not application code, so there is no unit-test/TDD loop. "Verification" = `actionlint`, structural `grep` assertions, and a `workflow_dispatch` DRY-RUN against current real PRs. Build the file in one task (an incomplete intermediate YAML would fail to lint and give a false signal), then verify.

**Reference files (read before starting):**
- `.github/workflows/claude-sweeper-health.yml` — the template: pure-mechanical, `GITHUB_TOKEN`, two-stage idle-cheap scan, defensive `::warning::` handling.
- `.github/workflows/claude-resolve-conflicts.yml` — scan/matrix style, cron-offset rationale, `mergeable` GraphQL.
- `.github/workflows/claude-fix-pr-checks.yml` — statusCheckRollup style.
- `docs/superpowers/specs/2026-06-20-auto-merge-clean-prs-design.md` — the approved spec.

**Verify-before-relying (live facts the Manager confirmed 2026-06-20; re-confirm if the repo changed):**
- `main` is unprotected → `GITHUB_TOKEN` can merge; no PAT.
- Copilot reviewer login is `copilot-pull-request-reviewer[bot]`; its reviews are `COMMENTED`, not `APPROVED`.
- Taken cron minutes: 0, 17, 30, 45. This workflow uses 50.

---

### Task 1: Create the workflow file

**Files:**
- Create: `.github/workflows/claude-auto-merge.yml`

- [ ] **Step 1: Write the complete workflow file**

Create `.github/workflows/claude-auto-merge.yml` with EXACTLY this content:

```yaml
name: claude-auto-merge

# Cron-driven sweeper. AUTO-MERGES open PRs that are unambiguously safe to merge.
# PURE-MECHANICAL (no Claude, no PAT) — modeled on claude-sweeper-health.yml, NOT
# on the Claude+PAT sweepers. All six merge predicates are deterministic gh/GraphQL
# reads, so an LLM would only add cost + a non-deterministic actor to a DESTRUCTIVE
# action (merge). It uses the built-in GITHUB_TOKEN: `main` is unprotected, so a
# merge is a plain Contents+PR write the token can do; nothing here pushes to
# .github/workflows/, so the PAT the other sweepers need is unnecessary.
#
# WHY CRON, NOT an event trigger (same constraints the other sweepers documented):
#  1. BOT-ACTOR GATING: a run triggered by a bot actor is parked in
#     `action_required` awaiting manual approval -> not hands-off.
#  2. LOOP: reacting to PR events re-fires on our own activity.
# A SCHEDULED workflow runs as the repo/owner identity and is NOT approval-gated.
# We poll an idempotent work-signal ("open PR satisfying all six predicates"); a
# merged PR is closed and never re-scanned, so the signal is self-clearing.
#
# SAFETY: ships DRY_RUN=true (report-only). The scan logs which PRs WOULD merge
# without merging any. After the predicate is sanity-checked against real PRs,
# flip DRY_RUN to "false" (one-line commit) to arm the merge. workflow_dispatch
# has a dry_run input that overrides the env for a single manual run.
#
# THE SIX PREDICATES (ALL required), per open non-draft same-repo PR with no hold
# label:
#  1. CI passing      : statusCheckRollup.state == SUCCESS (null rollup = no checks
#                       => NOT eligible; PENDING/FAILURE => NOT eligible).
#  2. No conflicts    : mergeable == MERGEABLE (UNKNOWN => settling, skip tick;
#                       CONFLICTING => resolve-conflicts sweeper's job).
#  3. Copilot reviewed: a review exists from copilot-pull-request-reviewer[bot] in
#                       ANY state. !! NOT state==APPROVED — Copilot reviews come
#                       back COMMENTED, so gating on APPROVED never fires. !!
#  4. No open threads : zero reviewThreads with isResolved==false, AND no human's
#                       latest review is CHANGES_REQUESTED.
#  5. Quiet 24h       : now - max(last commit, comments, review comments, reviews)
#                       >= QUIET_HOURS.
#  6. Trusted author  : author is a Bot (__typename Bot / login ends [bot]) OR a
#                       repo collaborator with admin|write|maintain permission.
#
# NOTE (YAML/heredoc gotcha): the python predicate is written to a tempfile via an
# INDENTED heredoc and de-indented with sed before it runs. A flush-left heredoc
# body would terminate the `run: |` block scalar early and break YAML parsing.
#
# Design: docs/superpowers/specs/2026-06-20-auto-merge-clean-prs-design.md

on:
  schedule:
    # Every 3 hours at minute 50. OFFSET from the four other scheduled workflows
    # so no two tick in the same minute and double-spend the run budget:
    # copilot-review = min 0, sweeper-health = min 17, fix-checks = min 30,
    # resolve-conflicts = min 45. Minute 50 collides with NONE. A `*/3` schedule
    # still fires AT its minute field (the cron-collision gotcha), so the minute
    # is what must be unique; the hour spacing is irrelevant to collision.
    # Auto-merge is the least time-sensitive sweeper and the work-signal is
    # idempotent, so 3-hourly is ample. (GitHub throttles high-frequency cron on
    # this low-activity repo anyway.)
    - cron: "50 */3 * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Report-only (true) or actually merge (false). Overrides the DRY_RUN env for this run."
        type: boolean
        default: true

concurrency:
  # Serialize ticks so two overlapping runs never both decide to merge the same
  # PR. cancel-in-progress:false lets an in-flight sweep finish.
  group: claude-auto-merge-sweeper
  cancel-in-progress: false

permissions:
  contents: write # perform the merge commit
  pull-requests: write # merge via the PR + delete the head branch
  checks: read # read check runs (rollup)
  statuses: read # read commit statuses (rollup)

env:
  # Report-only by default. Flip to "false" to arm the merge after previewing.
  DRY_RUN: "true"
  # Criterion 5 threshold (hours of inactivity required before merge).
  QUIET_HOURS: "24"
  # Criterion 3 keys off this exact reviewer login (verified live 2026-06-20).
  COPILOT_REVIEWER_LOGIN: "copilot-pull-request-reviewer[bot]"
  # Merge method: squash keeps main linear, one commit per PR. Tunable.
  MERGE_METHOD: "squash"
  # Escape-hatch labels: a PR carrying any of these is never auto-merged.
  HOLD_LABELS: "do-not-merge,hold"

jobs:
  # Single job: scan + merge. The merge IS the cheap action (one API call), so
  # unlike the Claude sweepers there is no separate expensive stage.
  auto-merge:
    name: scan and auto-merge clean PRs
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Write predicate evaluator
        run: |
          # De-indent the heredoc (10 leading spaces from the YAML scalar) so the
          # python file lands at column 0. A flush-left heredoc body here would
          # break the YAML block scalar, hence the indent + sed strip.
          sed 's/^          //' > /tmp/predicate.py <<'PY'
          import json, os, sys
          from datetime import datetime, timezone

          d = json.load(sys.stdin)
          pull = (d.get("data") or {}).get("repository", {}).get("pullRequest")
          if not pull:
              print("SKIP:no-pull-data"); sys.exit(0)

          def parse(ts):
              return datetime.fromisoformat(ts.replace("Z", "+00:00"))

          if pull.get("isDraft"):
              print("SKIP:draft"); sys.exit(0)
          hold = {l.strip() for l in os.environ["HOLD_LABELS"].split(",") if l.strip()}
          labels = {n["name"] for n in (pull.get("labels") or {}).get("nodes", [])}
          if labels & hold:
              print("SKIP:hold-label"); sys.exit(0)

          mergeable = pull.get("mergeable")
          if mergeable == "UNKNOWN":
              print("SKIP:mergeable-unknown-settling"); sys.exit(0)
          if mergeable != "MERGEABLE":
              print(f"SKIP:not-mergeable({mergeable})"); sys.exit(0)

          commits = (pull.get("commits") or {}).get("nodes", [])
          if not commits:
              print("SKIP:no-head-commit"); sys.exit(0)
          head = commits[0]["commit"]
          rollup = head.get("statusCheckRollup")
          if rollup is None:
              print("SKIP:no-checks"); sys.exit(0)
          if rollup.get("state") != "SUCCESS":
              print(f"SKIP:checks-{rollup.get('state')}"); sys.exit(0)

          copilot = os.environ["COPILOT_REVIEWER_LOGIN"]
          reviews = (pull.get("reviews") or {}).get("nodes", [])
          if not any((r.get("author") or {}).get("login") == copilot for r in reviews):
              print("SKIP:no-copilot-review"); sys.exit(0)

          threads = (pull.get("reviewThreads") or {}).get("nodes", [])
          if any(not t.get("isResolved") for t in threads):
              print("SKIP:unresolved-threads"); sys.exit(0)

          latest = {}
          for r in reviews:
              login = (r.get("author") or {}).get("login")
              sub = r.get("submittedAt")
              state = r.get("state")
              if not login or login == copilot or not sub:
                  continue
              if state not in ("APPROVED", "CHANGES_REQUESTED"):
                  continue
              if login not in latest or parse(sub) > parse(latest[login][0]):
                  latest[login] = (sub, state)
          if any(state == "CHANGES_REQUESTED" for _, state in latest.values()):
              print("SKIP:changes-requested"); sys.exit(0)

          stamps = [head["committedDate"]]
          for c in (pull.get("comments") or {}).get("nodes", []):
              stamps.append(c["createdAt"])
          for r in reviews:
              if r.get("submittedAt"):
                  stamps.append(r["submittedAt"])
          for t in threads:
              for c in (t.get("comments") or {}).get("nodes", []):
                  stamps.append(c.get("updatedAt") or c["createdAt"])
          newest = max(parse(s) for s in stamps)
          age_h = (datetime.now(timezone.utc) - newest).total_seconds() / 3600.0
          quiet = float(os.environ["QUIET_HOURS"])
          if age_h < quiet:
              print(f"SKIP:active-{age_h:.1f}h-ago"); sys.exit(0)

          author = pull.get("author") or {}
          login = author.get("login", "")
          if author.get("__typename") == "Bot" or login.endswith("[bot]"):
              print("ELIGIBLE"); sys.exit(0)

          print(f"NEEDS_COLLAB:{login}"); sys.exit(0)
          PY
          echo "predicate written:"; head -3 /tmp/predicate.py

      - name: Scan open PRs and merge the clean ones
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          OWNER: ${{ github.repository_owner }}
          DRY_RUN_OVERRIDE: ${{ github.event.inputs.dry_run }}
        run: |
          set -euo pipefail

          dry_run="${DRY_RUN}"
          if [ -n "${DRY_RUN_OVERRIDE:-}" ]; then
            dry_run="${DRY_RUN_OVERRIDE}"
          fi
          echo "DRY_RUN effective = ${dry_run}"

          repo_name="${REPO#*/}"

          candidates="$(gh pr list --repo "$REPO" --state open --limit 100 \
            --json number,isCrossRepository,isDraft \
            --jq '[.[] | select(.isCrossRepository == false and .isDraft == false) | .number]')"
          echo "candidate PRs (open same-repo non-draft): $candidates"

          for pr in $(echo "$candidates" | python3 -c 'import json,sys; print(" ".join(str(n) for n in json.load(sys.stdin)))'); do
            echo "----- evaluating PR #$pr -----"

            data="$(gh api graphql -f query='
              query($owner:String!,$repo:String!,$pr:Int!){
                repository(owner:$owner,name:$repo){
                  pullRequest(number:$pr){
                    mergeable
                    isDraft
                    author{ __typename login }
                    labels(first:50){ nodes{ name } }
                    commits(last:1){ nodes{ commit{
                      committedDate
                      statusCheckRollup{ state }
                    }}}
                    comments(last:100){ nodes{ createdAt } }
                    reviews(last:100){ nodes{ author{ login } state submittedAt } }
                    reviewThreads(first:100){ nodes{
                      isResolved
                      comments(last:50){ nodes{ createdAt updatedAt } }
                    }}
                  }
                }
              }' -F owner="$OWNER" -F repo="$repo_name" -F pr="$pr" 2>/tmp/gql-err || true)"

            if [ -z "$data" ]; then
              echo "::warning::PR #$pr: GraphQL returned empty (possible API failure); treating as NOT eligible. stderr: $(tr '\n' ' ' < /tmp/gql-err)"
              rm -f /tmp/gql-err
              continue
            fi
            rm -f /tmp/gql-err

            verdict="$(echo "$data" | QUIET_HOURS="$QUIET_HOURS" \
              COPILOT_REVIEWER_LOGIN="$COPILOT_REVIEWER_LOGIN" \
              HOLD_LABELS="$HOLD_LABELS" python3 /tmp/predicate.py)"

            case "$verdict" in
              SKIP:*)
                echo "PR #$pr: ${verdict#SKIP:} -> not eligible."
                continue
                ;;
              NEEDS_COLLAB:*)
                login="${verdict#NEEDS_COLLAB:}"
                perm="$(gh api "repos/${REPO}/collaborators/${login}/permission" \
                  --jq '.permission' 2>/dev/null || echo "none")"
                case "$perm" in
                  admin|write|maintain)
                    echo "PR #$pr: author $login is collaborator ($perm) -> eligible."
                    ;;
                  *)
                    echo "PR #$pr: author $login not a trusted collaborator (perm=$perm) -> not eligible."
                    continue
                    ;;
                esac
                ;;
              ELIGIBLE)
                echo "PR #$pr: author is a bot -> eligible."
                ;;
              *)
                echo "::warning::PR #$pr: unexpected verdict '$verdict'; treating as NOT eligible."
                continue
                ;;
            esac

            if [ "$dry_run" = "true" ]; then
              echo "PR #$pr: WOULD MERGE (method=${MERGE_METHOD}, --delete-branch). DRY_RUN on; not merging."
              continue
            fi

            echo "PR #$pr: MERGING (method=${MERGE_METHOD}, --delete-branch)."
            if ! gh pr merge "$pr" --repo "$REPO" "--${MERGE_METHOD}" --delete-branch; then
              echo "::warning::PR #$pr: merge failed (race or transient API error); will be re-evaluated next tick."
            fi
          done

          echo "auto-merge sweep complete."
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/claude-auto-merge.yml
git commit -m "feat: add claude-auto-merge sweeper (report-only by default)"
```

---

### Task 2: Lint the workflow

**Files:**
- Verify: `.github/workflows/claude-auto-merge.yml`

- [ ] **Step 1: Run actionlint**

Run: `actionlint .github/workflows/claude-auto-merge.yml`
(If not installed: `brew install actionlint`, or use the YAML-parse fallback.)
Expected: no output (exit 0). actionlint also runs `shellcheck` on `run:` blocks — fix any SC warnings. (The embedded python heredoc is opaque to shellcheck, which is fine.)

- [ ] **Step 2: YAML-parse fallback (if actionlint unavailable)**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/claude-auto-merge.yml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 3: Python-block syntax check**

The predicate is written to `/tmp/predicate.py` via an INDENTED heredoc (10 leading
spaces, required so the `run: |` block scalar stays valid YAML) and de-indented at
runtime by `sed 's/^          //'`. Compile it locally exactly as the runner would —
extract the heredoc body, strip the 10-space indent, then `ast.parse`:
```bash
python3 - <<'CHK'
import re, ast
y = open('.github/workflows/claude-auto-merge.yml').read()
body = re.search(r"<<'PY'\n(.*?)\n          PY", y, re.S).group(1)
ded = '\n'.join(l[10:] if l.startswith('          ') else l for l in body.split('\n'))
ast.parse(ded); print('PY OK after de-indent;', ded.count(chr(10)) + 1, 'lines')
CHK
```
Expected: `PY OK after de-indent; N lines`.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add .github/workflows/claude-auto-merge.yml
git commit -m "fix: actionlint cleanups on claude-auto-merge"
```

---

### Task 3: Structural assertions

Each grep must print a match (or NO match where stated).

**Files:**
- Verify: `.github/workflows/claude-auto-merge.yml`

- [ ] **Step 1: Cron minute is unique vs the other four sweepers**

Run: `grep -rn 'cron:' .github/workflows/claude-*.yml`
Expected minute fields, all distinct: copilot-review `0`, sweeper-health `17`, fix-checks `30`, resolve-conflicts `45`, auto-merge `50`. No shared minute.

- [ ] **Step 2: Pure-mechanical — NO Claude, NO PAT**

Run: `grep -n 'PR_AUTHOR_PAT\|claude-code-action\|CLAUDE_CODE_OAUTH_TOKEN\|id-token' .github/workflows/claude-auto-merge.yml`
Expected: **NO matches** (this sweeper uses GITHUB_TOKEN only).

- [ ] **Step 3: Copilot detection by PRESENCE, not APPROVED**

Run: `grep -n 'copilot-pull-request-reviewer\[bot\]' .github/workflows/claude-auto-merge.yml`
Expected: a match (the COPILOT_REVIEWER_LOGIN env).
Run: `grep -n 'APPROVED' .github/workflows/claude-auto-merge.yml`
Expected: APPROVED appears ONLY inside the crit-4b latest-human-review logic (allowed states), NEVER as the Copilot gate.

- [ ] **Step 4: Merge call + safety default present**

Run: `grep -n 'gh pr merge\|--delete-branch\|DRY_RUN' .github/workflows/claude-auto-merge.yml`
Expected: `gh pr merge ... --delete-branch` present; `DRY_RUN: "true"` env default present.

- [ ] **Step 5: All six predicates wired**

Run: `grep -n 'statusCheckRollup\|mergeable\|reviewThreads\|isResolved\|CHANGES_REQUESTED\|committedDate\|collaborators' .github/workflows/claude-auto-merge.yml`
Expected: matches covering crit 1 (rollup), 2 (mergeable), 4 (reviewThreads/isResolved/CHANGES_REQUESTED), 5 (committedDate), 6 (collaborators). (Crit 3 covered by Step 3.)

---

### Task 4: Live DRY-RUN via workflow_dispatch

Scheduled workflows only run from the default branch, but `workflow_dispatch` runs from any branch via `--ref`. Exercise the predicate against REAL PRs before arming.

**Files:** none (operational).

- [ ] **Step 1: Push the branch and open the PR**

```bash
git push -u origin <feature-branch>
gh pr create --fill --base main --head <feature-branch>
```

- [ ] **Step 2: Dispatch in DRY-RUN (default) from this branch**

```bash
gh workflow run claude-auto-merge.yml --ref <feature-branch> -f dry_run=true
gh run watch "$(gh run list --workflow=claude-auto-merge.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected: the job logs a per-PR verdict for every open PR — `WOULD MERGE PR #N` for eligible ones and `SKIP:<reason>` for the rest. Nothing is merged.

- [ ] **Step 3: Hand-verify the verdicts**

For 2-3 PRs, confirm the logged verdict by hand:
- An eligible PR really is green + mergeable + has a `copilot-pull-request-reviewer[bot]` review + no open threads + quiet 24h + bot/collaborator author.
- A `SKIP:no-copilot-review` PR really lacks a Copilot review.
- A `SKIP:active-Xh-ago` PR really had activity in the last 24h.
Confirm a fork PR and a draft PR are absent from the candidate list.

- [ ] **Step 4: Live merge round-trip on a throwaway PR (optional, before arming)**

Create a trivially-clean throwaway PR that satisfies all six (or temporarily relax `QUIET_HOURS` to `0` via a dispatch on a test branch), then:
```bash
gh workflow run claude-auto-merge.yml --ref <test-branch> -f dry_run=false
```
Confirm the throwaway PR is squash-merged and its head branch deleted. Clean up.

- [ ] **Step 5: Arm it**

After the user confirms the DRY-RUN verdicts match intent, flip the env in a one-line commit:
```yaml
  DRY_RUN: "false"
```
and commit `chore: arm claude-auto-merge (DRY_RUN=false)`. This is an explicit, reviewable step — the sweeper merges nothing until it lands.

---

## Self-Review

**Spec coverage:**
- Pure-mechanical, GITHUB_TOKEN only, no PAT/Claude → Task 1 (permissions + env + no action ref), Task 3 Step 2. ✓
- Cron min 50, unique vs the four → Task 1 (`on.schedule`), Task 3 Step 1. ✓
- Crit 1 rollup SUCCESS, null=ineligible → Task 1 python, Task 3 Step 5. ✓
- Crit 2 mergeable MERGEABLE, UNKNOWN settle-skip → Task 1 python, Task 3 Step 5. ✓
- Crit 3 Copilot presence (ANY state, NOT APPROVED) → Task 1 python, Task 3 Step 3. ✓
- Crit 4 unresolved threads + outstanding CHANGES_REQUESTED → Task 1 python, Task 3 Step 5. ✓
- Crit 5 quiet-24h union of stamps in python → Task 1 python, Task 3 Step 5. ✓
- Crit 6 bot OR collaborator (admin|write|maintain via REST) → Task 1 python + shell collab lookup, Task 3 Step 5. ✓
- Q3 squash + delete-branch → Task 1 merge call, Task 3 Step 4. ✓
- Q4 draft guard + hold labels + CHANGES_REQUESTED → Task 1 python guards. ✓
- DRY_RUN report-only default + dispatch override + arm step → Task 1 env/input, Task 3 Step 4, Task 4 Steps 2/5. ✓
- Self-clearing termination (no MAX_PASSES) → no pass-label machinery; merged PR closes. ✓
- actionlint + python-syntax + structural greps + dispatch dry-run → Tasks 2-4. ✓

**Placeholder scan:** only `<feature-branch>` / `<test-branch>` in the operational task, environment-specific by nature. No code placeholders.

**Name/type consistency:** env keys `DRY_RUN`, `QUIET_HOURS`, `COPILOT_REVIEWER_LOGIN`, `MERGE_METHOD`, `HOLD_LABELS`; verdict tokens `ELIGIBLE` / `SKIP:*` / `NEEDS_COLLAB:*`; `--${MERGE_METHOD}` matches the `gh pr merge` flag form — used consistently across the python block, shell case, and merge call. ✓
