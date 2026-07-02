# Orphan-issue sweeper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-implement issues that die silently (Claude quota exhaustion, timeouts, action errors) currently orphan forever; this adds a self-healing cron sweeper that re-dispatches them with a bounded retry budget and alarms a human when the budget is spent.

**Architecture:** Three moving parts. (1) `claude-implement-issue.yml` gains a `workflow_dispatch` re-entry point and stamps terminal-state labels on the issue (`implement-failed`, `implement-blocked`). (2) A pure, unit-tested decision core `backend/scripts/orphan_issue_sweep.py` classifies each open issue into dispatch/alarm/clear/skip from a "world" JSON. (3) A new cron sweeper `claude-orphan-issue-sweeper.yml` gathers that world via `gh`/REST, runs the core, and executes the plan (re-dispatch via `PR_AUTHOR_PAT`, everything else via `GITHUB_TOKEN`); plus a 4th health job watching it.

**Tech Stack:** GitHub Actions (YAML), `gh` CLI + REST API, `jq` (present on runners), Python 3.14 + pytest (decision core), no new secrets (reuses `GITHUB_TOKEN` + `PR_AUTHOR_PAT`).

**Spec:** `docs/superpowers/specs/2026-07-02-orphan-issue-sweeper-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/scripts/orphan_issue_sweep.py` | **Create.** Pure decision core: world JSON → action plan JSON. No I/O beyond stdin/stdout. Mirrors `sweeper_health.py`. |
| `backend/tests/test_orphan_issue_sweep.py` | **Create.** Unit tests locking the classification boundaries. |
| `.github/workflows/claude-implement-issue.yml` | **Modify.** Add `workflow_dispatch` trigger, issue-context shim (event-or-input), dispatch-path trust re-check, terminal-state labels. |
| `.github/workflows/claude-orphan-issue-sweeper.yml` | **Create.** Cron sweeper: gather world → run core → execute plan. `DRY_RUN: "true"` default. |
| `.github/workflows/claude-sweeper-health.yml` | **Modify.** Add a 4th job `orphan-sweeper-health` watching the new sweeper. |

**Label vocabulary** (all created on first use with `gh label create ... || true`):
- `implement-failed` — implement job died red (observability; not load-bearing).
- `implement-blocked` — implement stopped deliberately on a test blocker (sweeper skips these).
- `implement-attempt-N` — sweeper's retry counter (N = attempts so far).
- `orphan-issue-stale` — dedup label for the cap-exhausted alarm issue.
- `orphan-sweeper-stale` — dedup label for the health-watcher alarm.

---

## Task 1: Decision core `orphan_issue_sweep.py` (TDD)

**Files:**
- Create: `backend/scripts/orphan_issue_sweep.py`
- Test: `backend/tests/test_orphan_issue_sweep.py`

The core takes a `world` dict and returns a plan dict with four buckets. Classification per open issue:
- `has_linked_pr` (open/merged PR closing it) → not an orphan. If it still carries `implement-attempt-N` labels, emit a `clear` (recovery housekeeping); else `skip` reason `has_linked_pr`.
- author not in `trusted_associations` → `skip` reason `untrusted_author`.
- `has_branch` (a `claude/issue-N` branch exists) → `skip` reason `has_branch`.
- `blocked_label` in labels → `skip` reason `blocked`.
- `in_progress` → `skip` reason `in_progress`.
- otherwise **orphan**: if attempt count `< max_attempts` → `dispatch` (remove stale attempt labels, add `implement-attempt-{count+1}`); else → `alarm`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_orphan_issue_sweep.py`:

```python
"""Tests for the orphan-issue sweeper decision core.

The auto-implement flow (`claude-implement-issue.yml`) can die silently — most
often when the day's Claude subscription quota is exhausted, but also on
timeouts or transient action errors. A silently-dead issue leaves no PR, no
branch, and no blocker comment, and never re-triggers (the workflow fires only
on `issues: opened/reopened`). `orphan_issue_sweep.plan_sweep` is the pure
decision that turns a snapshot of repo state ("world") into an action plan;
these tests lock the classification boundaries the untestable shell relies on.

The key correctness hinge: a DELIBERATE stop (tests failed, agent posted a
blocker comment, job green → labelled `implement-blocked`) must be left alone,
while a SILENT death (no such label, no PR, no branch) must be re-dispatched.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from scripts.orphan_issue_sweep import main, plan_sweep

BASE_WORLD = {
    "max_attempts": 3,
    "attempt_label_prefix": "implement-attempt-",
    "blocked_label": "implement-blocked",
    "trusted_associations": ["OWNER", "MEMBER", "COLLABORATOR"],
    "issues": [],
}


def _world(*issues):
    w = dict(BASE_WORLD)
    w["issues"] = list(issues)
    return w


def _issue(number, **kw):
    issue = {
        "number": number,
        "title": f"Issue {number}",
        "author_association": "OWNER",
        "labels": [],
        "has_linked_pr": False,
        "has_branch": False,
        "in_progress": False,
    }
    issue.update(kw)
    return issue


def test_silent_death_is_dispatched():
    # No PR, no branch, not blocked, no attempts yet -> first retry.
    plan = plan_sweep(_world(_issue(10)))
    assert [d["number"] for d in plan["dispatch"]] == [10]
    d = plan["dispatch"][0]
    assert d["add_label"] == "implement-attempt-1"
    assert d["attempt"] == 1
    assert d["remove_labels"] == []
    assert plan["alarm"] == []


def test_failed_label_still_dispatches():
    # `implement-failed` is observability only, not a skip signal.
    plan = plan_sweep(_world(_issue(11, labels=["implement-failed"])))
    assert [d["number"] for d in plan["dispatch"]] == [11]


def test_blocked_label_is_skipped():
    # Deliberate blocker stop -> leave alone.
    plan = plan_sweep(_world(_issue(12, labels=["implement-blocked"])))
    assert plan["dispatch"] == []
    assert plan["alarm"] == []
    assert {"number": 12, "reason": "blocked"} in plan["skip"]


def test_in_progress_is_skipped():
    plan = plan_sweep(_world(_issue(13, in_progress=True)))
    assert plan["dispatch"] == []
    assert {"number": 13, "reason": "in_progress"} in plan["skip"]


def test_open_pr_is_skipped():
    plan = plan_sweep(_world(_issue(14, has_linked_pr=True)))
    assert plan["dispatch"] == []
    assert {"number": 14, "reason": "has_linked_pr"} in plan["skip"]


def test_merged_pr_with_stale_attempt_label_is_cleared():
    # Recovered: has PR now. Clear the leftover attempt label so a future
    # reopen starts fresh; do not dispatch.
    plan = plan_sweep(
        _world(_issue(15, has_linked_pr=True, labels=["implement-attempt-2"]))
    )
    assert plan["dispatch"] == []
    assert plan["clear"] == [{"number": 15, "remove_labels": ["implement-attempt-2"]}]


def test_untrusted_author_is_skipped():
    plan = plan_sweep(_world(_issue(16, author_association="NONE")))
    assert plan["dispatch"] == []
    assert {"number": 16, "reason": "untrusted_author"} in plan["skip"]


def test_existing_branch_is_skipped():
    plan = plan_sweep(_world(_issue(17, has_branch=True)))
    assert plan["dispatch"] == []
    assert {"number": 17, "reason": "has_branch"} in plan["skip"]


def test_under_cap_bumps_attempt_label():
    plan = plan_sweep(_world(_issue(18, labels=["implement-attempt-2"])))
    d = plan["dispatch"][0]
    assert d["attempt"] == 3
    assert d["add_label"] == "implement-attempt-3"
    assert d["remove_labels"] == ["implement-attempt-2"]


def test_at_cap_alarms_not_dispatches():
    plan = plan_sweep(_world(_issue(19, labels=["implement-attempt-3"])))
    assert plan["dispatch"] == []
    assert plan["alarm"] == [{"number": 19, "attempts": 3}]


def test_multiple_stale_attempt_labels_all_removed():
    # Defensive: if two attempt labels somehow coexist, count is the max and
    # both are removed before adding the next.
    plan = plan_sweep(
        _world(_issue(20, labels=["implement-attempt-1", "implement-attempt-2"]))
    )
    d = plan["dispatch"][0]
    assert d["attempt"] == 3
    assert d["remove_labels"] == ["implement-attempt-1", "implement-attempt-2"]
    assert d["add_label"] == "implement-attempt-3"


def test_non_integer_attempt_suffix_ignored():
    plan = plan_sweep(_world(_issue(21, labels=["implement-attempt-oops"])))
    d = plan["dispatch"][0]
    assert d["attempt"] == 1  # unparseable suffix counts as 0 attempts


def test_main_reads_stdin_and_emits_plan(monkeypatch):
    world = _world(_issue(22))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(world)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--world", "-"])
    assert rc == 0
    plan = json.loads(buf.getvalue())
    assert [d["number"] for d in plan["dispatch"]] == [22]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_orphan_issue_sweep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.orphan_issue_sweep'`.

(Venv path per `autotiers-test-running`: the repo venv is at `backend/venv`, not `.venv`. On CI, drop the `venv/bin/` prefix — deps are pre-installed.)

- [ ] **Step 3: Write the implementation**

Create `backend/scripts/orphan_issue_sweep.py`:

```python
"""Decision core for the orphan-issue sweeper (`claude-orphan-issue-sweeper.yml`).

`claude-implement-issue.yml` implements a trusted author's issue end-to-end and
opens a PR. It fires ONLY on `issues: opened/reopened` — a webhook, not a poll —
so nothing ever re-scans open issues. The flow has two no-PR outcomes:

  * DELIBERATE stop — the agent ran, its tests failed, it posted a blocker
    comment and stopped (job green). The implement workflow labels the issue
    `implement-blocked`. This is a correct terminal state; leave it alone.
  * SILENT death — the action step itself errored before the agent could post
    anything (dominant cause: the day's Claude subscription quota is exhausted;
    also timeouts / transient errors). The job concludes red, the push/PR steps
    skip on their `hashFiles('.pr-body.md')` gate, and the issue is left with no
    PR, no branch, no comment. It never re-triggers -> orphaned forever.

This module is the PURE decision: given a snapshot of repo state (`world`), it
returns the action plan the sweeper's shell then executes. Keeping the logic
here (not in shell) lets us unit-test the classification boundaries that shell
`if`-chains get wrong. The discriminator between the two cases above is the
`implement-blocked` label, NOT any historical Actions-run correlation
(`gh run list` exposes only a run's display title, i.e. the issue title, never
its number).

world (stdin JSON):
    {
      "max_attempts": 3,
      "attempt_label_prefix": "implement-attempt-",
      "blocked_label": "implement-blocked",
      "trusted_associations": ["OWNER", "MEMBER", "COLLABORATOR"],
      "issues": [
        {"number": 1, "title": "...", "author_association": "OWNER",
         "labels": ["implement-attempt-1"], "has_linked_pr": false,
         "has_branch": false, "in_progress": false}
      ]
    }

plan (stdout JSON):
    {
      "dispatch": [{"number", "attempt", "remove_labels", "add_label"}],
      "alarm":    [{"number", "attempts"}],
      "clear":    [{"number", "remove_labels"}],
      "skip":     [{"number", "reason"}]
    }

Exit code is 0 on success; a malformed world (bad JSON, missing key) raises and
exits non-zero so a broken input is loud rather than silently "nothing to do".
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def _attempt_labels(labels: list[str], prefix: str) -> tuple[int, list[str]]:
    """Return (highest attempt N, sorted attempt-label names present).

    A label whose suffix is not a base-10 integer is ignored for the count but
    still returned for removal, so a malformed `implement-attempt-oops` cannot
    wedge an issue: it contributes 0 to the count and gets swept away on the
    next dispatch.
    """
    names: list[str] = []
    best = 0
    for name in labels:
        if not name.startswith(prefix):
            continue
        names.append(name)
        suffix = name[len(prefix):]
        try:
            best = max(best, int(suffix))
        except ValueError:
            continue
    return best, sorted(names)


def plan_sweep(world: dict) -> dict:
    """Classify every open issue in `world` into an action plan (see module docstring)."""
    max_attempts = int(world["max_attempts"])
    prefix = world["attempt_label_prefix"]
    blocked = world["blocked_label"]
    trusted = set(world["trusted_associations"])

    dispatch: list[dict] = []
    alarm: list[dict] = []
    clear: list[dict] = []
    skip: list[dict] = []

    for issue in world["issues"]:
        number = issue["number"]
        labels = issue.get("labels", [])
        count, attempt_labels = _attempt_labels(labels, prefix)

        # A linked (open or merged) PR means the issue is in flight or done:
        # never an orphan. Housekeep any leftover attempt labels so a future
        # reopen starts from a fresh retry budget.
        if issue.get("has_linked_pr"):
            if attempt_labels:
                clear.append({"number": number, "remove_labels": attempt_labels})
            else:
                skip.append({"number": number, "reason": "has_linked_pr"})
            continue

        if issue.get("author_association") not in trusted:
            skip.append({"number": number, "reason": "untrusted_author"})
            continue
        if issue.get("has_branch"):
            skip.append({"number": number, "reason": "has_branch"})
            continue
        if blocked in labels:
            skip.append({"number": number, "reason": "blocked"})
            continue
        if issue.get("in_progress"):
            skip.append({"number": number, "reason": "in_progress"})
            continue

        # Orphan: open, trusted, no PR, no branch, not blocked, not running.
        if count < max_attempts:
            dispatch.append({
                "number": number,
                "attempt": count + 1,
                "remove_labels": attempt_labels,
                "add_label": f"{prefix}{count + 1}",
            })
        else:
            alarm.append({"number": number, "attempts": count})

    return {"dispatch": dispatch, "alarm": alarm, "clear": clear, "skip": skip}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--world",
        default="-",
        help="Path to the world JSON, or '-' (default) to read stdin.",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.world == "-" else open(args.world, encoding="utf-8").read()
    world = json.loads(raw)
    plan = plan_sweep(world)
    json.dump(plan, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_orphan_issue_sweep.py -q`
Expected: PASS — all 13 tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/orphan_issue_sweep.py backend/tests/test_orphan_issue_sweep.py
git commit -m "feat(ci): orphan-issue sweeper decision core

Pure classifier: world snapshot -> dispatch/alarm/clear/skip. Discriminates
silent-death (re-dispatch) from deliberate blocker-stop (leave alone) via the
implement-blocked label, with a per-issue retry cap.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `workflow_dispatch` re-entry + terminal-state labels on `claude-implement-issue.yml`

**Files:**
- Modify: `.github/workflows/claude-implement-issue.yml`

This task makes the implement workflow re-dispatchable by issue number and makes it stamp its own terminal state. **The webhook happy path (implement→push→PR) must behave exactly as today** — only the *source* of the issue fields changes, plus new label steps.

- [ ] **Step 1: Add the `workflow_dispatch` trigger**

Replace the `on:` block (currently):

```yaml
on:
  issues:
    types: [opened, reopened]
```

with:

```yaml
on:
  issues:
    types: [opened, reopened]
  workflow_dispatch:
    inputs:
      issue_number:
        description: "Issue number to (re-)implement end-to-end."
        required: true
        type: string
```

- [ ] **Step 2: Make `concurrency` and the job guard event-or-input aware**

Replace the `concurrency` block:

```yaml
concurrency:
  group: claude-issue-${{ github.event.issue.number }}
  cancel-in-progress: false
```

with (concurrency is evaluated at workflow start, before any step runs, so it CANNOT read step-set env — it must read the raw contexts):

```yaml
concurrency:
  group: claude-issue-${{ github.event.issue.number || github.event.inputs.issue_number }}
  cancel-in-progress: false
```

Replace the job-level `if:` (currently on the `implement` job, line ~40):

```yaml
    if: contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)
```

with (allow the dispatch path through the job gate; the trust re-check happens inside — see Step 3):

```yaml
    if: >-
      github.event_name == 'workflow_dispatch' ||
      contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)
```

- [ ] **Step 3: Add the issue-context shim as the FIRST step of the `implement` job**

Insert this as the first step, BEFORE `- uses: actions/checkout@v4`:

```yaml
      # Resolve the issue's number/title/author from EITHER the webhook payload
      # (opened/reopened) OR the workflow_dispatch input, into $GITHUB_ENV so
      # every later step reads one canonical source. Also: (a) fail closed if a
      # dispatched issue's author is not trusted (workflow_dispatch itself is
      # already write-access-gated by GitHub, but this is defense-in-depth so
      # neither a write-access human nor the sweeper can drive Claude on a
      # stranger's issue body); (b) clear stale terminal-state labels so they
      # always reflect THIS run; (c) on a human open/reopen only, reset the
      # sweeper's retry counter (a dispatch is the sweeper's own retry and must
      # keep the counter it just set).
      - name: Resolve issue context
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          EVENT_NAME: ${{ github.event_name }}
          EVENT_ISSUE_NUMBER: ${{ github.event.issue.number }}
          EVENT_ISSUE_TITLE: ${{ github.event.issue.title }}
          EVENT_ISSUE_ASSOC: ${{ github.event.issue.author_association }}
          INPUT_ISSUE_NUMBER: ${{ github.event.inputs.issue_number }}
        run: |
          set -euo pipefail
          if [ "$EVENT_NAME" = "workflow_dispatch" ]; then
            num="$INPUT_ISSUE_NUMBER"
            title="$(gh issue view "$num" --repo "$REPO" --json title --jq .title)"
            assoc="$(gh issue view "$num" --repo "$REPO" --json authorAssociation --jq .authorAssociation)"
            case "$assoc" in
              OWNER|MEMBER|COLLABORATOR) : ;;
              *)
                echo "::error::Issue #$num author association '$assoc' is not trusted; refusing to implement." >&2
                exit 1 ;;
            esac
          else
            num="$EVENT_ISSUE_NUMBER"
            title="$EVENT_ISSUE_TITLE"
            assoc="$EVENT_ISSUE_ASSOC"
          fi

          # Export for later steps. Use the delimiter form for the title so a
          # quote or special char in it cannot break the env file.
          {
            echo "ISSUE_NUMBER=$num"
            echo "ISSUE_ASSOC=$assoc"
            echo "ISSUE_TITLE<<__EOT__"
            echo "$title"
            echo "__EOT__"
          } >> "$GITHUB_ENV"

          # Clear stale terminal-state labels so they reflect THIS run only.
          # `--remove-label` errors if the label isn't on the issue -> tolerate.
          gh issue edit "$num" --repo "$REPO" \
            --remove-label implement-failed --remove-label implement-blocked \
            2>/dev/null || true

          # Human open/reopen resets the sweeper's retry budget; a dispatch does not.
          if [ "$EVENT_NAME" != "workflow_dispatch" ]; then
            gh issue view "$num" --repo "$REPO" --json labels \
              --jq '.labels[].name | select(startswith("implement-attempt-"))' \
              | while read -r lbl; do
                  [ -n "$lbl" ] && gh issue edit "$num" --repo "$REPO" --remove-label "$lbl" 2>/dev/null || true
                done
          fi
```

- [ ] **Step 4: Replace every `github.event.issue.*` reference in the job body with the resolved env vars**

Change these (there may be many `${{ github.event.issue.number }}` occurrences in the `Implement issue` prompt, plus the push/PR steps):

- Everywhere in the `prompt:` and `claude_args:` of the `Implement issue` step: `${{ github.event.issue.number }}` → `${{ env.ISSUE_NUMBER }}`.
- In the prompt: `Issue title: ${{ github.event.issue.title }}` → `Issue title: ${{ env.ISSUE_TITLE }}`.
- `Push implemented branch` step env: `BRANCH: claude/issue-${{ github.event.issue.number }}` → `BRANCH: claude/issue-${{ env.ISSUE_NUMBER }}`.
- `Open pull request` step env: `BRANCH: claude/issue-${{ github.event.issue.number }}` → `BRANCH: claude/issue-${{ env.ISSUE_NUMBER }}`; and the title fallback `title="Implement issue #${{ github.event.issue.number }}"` → `title="Implement issue #${{ env.ISSUE_NUMBER }}"`.

Use a grep to confirm none remain in the job body afterward:

Run: `grep -n 'github.event.issue' .github/workflows/claude-implement-issue.yml`
Expected: matches ONLY inside the `Resolve issue context` step's `env:` block (the `EVENT_ISSUE_*` bindings) and the `concurrency`/`if:` expressions from Step 2. No occurrence inside the prompt, push, or PR steps.

- [ ] **Step 5: Add the two terminal-state label steps at the END of the job**

Append after the `Open pull request` step (these are the sweeper's discriminator source):

```yaml
      # Silent death: the job failed (e.g. Claude quota exhausted, timeout,
      # action error) before producing a PR. Mark the issue so a human browsing
      # issues sees it; the orphan sweeper re-dispatches it regardless of this
      # label (it keys on "no PR + no branch + not blocked").
      - name: Label silent failure
        if: failure()
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
        run: |
          gh label create implement-failed --repo "$REPO" \
            --color d93f0b --description "Auto-implement job failed (e.g. Claude quota out)" \
            2>/dev/null || true
          gh issue edit "${ISSUE_NUMBER}" --repo "$REPO" --add-label implement-failed || true

      # Deliberate stop: the agent ran and SUCCEEDED at running, but wrote no
      # .pr-body.md — meaning tests failed and it posted a blocker comment
      # instead of opening a PR (the push/PR steps skipped on their hashFiles
      # gate; skipped steps do not fail, so success() holds). Mark it
      # `implement-blocked` so the orphan sweeper leaves it for a human.
      - name: Label deliberate blocker stop
        if: success() && hashFiles('.pr-body.md') == ''
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
        run: |
          gh label create implement-blocked --repo "$REPO" \
            --color fbca04 --description "Auto-implement stopped on a test blocker; needs a human" \
            2>/dev/null || true
          gh issue edit "${ISSUE_NUMBER}" --repo "$REPO" --add-label implement-blocked || true
```

- [ ] **Step 6: Verify the workflow still parses as valid YAML**

Run: `cd backend && venv/bin/python -c "import yaml,sys; yaml.safe_load(open('../.github/workflows/claude-implement-issue.yml')); print('ok')"`
Expected: `ok`

(YAML `on:` can parse as the boolean key `True` — that is normal for GitHub workflow files and harmless; we only assert the document is well-formed.)

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/claude-implement-issue.yml
git commit -m "feat(ci): make implement-issue re-dispatchable + stamp terminal state

Add workflow_dispatch(issue_number) re-entry with an event-or-input shim and a
defense-in-depth trust re-check; stamp implement-failed / implement-blocked so
the orphan sweeper can tell a silent death from a deliberate blocker stop.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: The sweeper workflow `claude-orphan-issue-sweeper.yml`

**Files:**
- Create: `.github/workflows/claude-orphan-issue-sweeper.yml`

Gathers the "world" via `gh`/REST + `jq`, runs the Task 1 core, and executes the plan. Ships **`DRY_RUN: "true"`** — it logs what it WOULD do and mutates nothing until armed.

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/claude-orphan-issue-sweeper.yml`:

```yaml
name: claude-orphan-issue-sweeper

# BACKSTOP for silently-dead auto-implement runs.
#
# `claude-implement-issue.yml` fires only on `issues: opened/reopened` (a
# webhook, not a poll). When its Claude step dies before producing a PR — most
# often because the day's Claude SUBSCRIPTION QUOTA is exhausted, also on
# timeouts / transient action errors — the issue is left with no PR, no branch,
# no comment, and never re-triggers: orphaned forever. (Design:
# docs/superpowers/specs/2026-07-02-orphan-issue-sweeper-design.md.)
#
# This sweeper periodically re-scans open issues and re-dispatches the orphans
# (bounded by a per-issue retry cap), alarming a human when an issue exhausts
# its budget. It invokes NO Claude directly — detection is deterministic GitHub
# reads. Claude re-enters only via the re-dispatched claude-implement-issue run.
#
# TOKEN SPLIT (correctness-critical): all detection reads and label/alarm writes
# use the built-in GITHUB_TOKEN. The `gh workflow run` DISPATCH uses
# PR_AUTHOR_PAT, because GitHub's recursion guard means an event triggered with
# GITHUB_TOKEN does NOT start a new workflow run (this includes
# workflow_dispatch) — a GITHUB_TOKEN dispatch would return success yet start
# nothing, defeating the sweeper. (Same behavior noted in the auto-merge sweeper
# and in the tfstate memory: "GITHUB_TOKEN merges suppress workflow runs".)
#
# Watched for staleness by claude-sweeper-health.yml (orphan-sweeper-health job).

on:
  schedule:
    # Hourly at minute 40. Verified-free minute among the scheduled workflows
    # (copilot-review=0, sweeper-health=17, fix-checks=30, resolve-conflicts=45,
    # auto-merge=50) — a cron fires AT its minute field regardless of the
    # hour/step field, so the minute is what must be unique. Hourly is ample:
    # Claude quota resets on a daily cadence, so an orphan from a quota-out day
    # just needs a retry within the day; GitHub throttles sub-hourly cron on
    # this low-activity repo anyway.
    - cron: "40 * * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Override DRY_RUN for a single manual run (true/false)."
        required: false
        type: string

concurrency:
  # Serialize ticks so two runs never both dispatch or double-label the same issue.
  group: claude-orphan-issue-sweeper
  cancel-in-progress: false

permissions:
  contents: read # actions/checkout; branch existence is read via the API below
  issues: write # bump attempt labels, clear recovered labels, open/close alarm
  pull-requests: read # detect linked PRs by head branch

env:
  # Ship SAFE: report-only until a human confirms the predicate against real
  # orphans, then flip to "false" in a one-line commit to arm re-dispatch.
  DRY_RUN: "true"
  IMPLEMENT_WORKFLOW: claude-implement-issue.yml
  MAX_ATTEMPTS: "3"
  ATTEMPT_LABEL_PREFIX: "implement-attempt-"
  BLOCKED_LABEL: "implement-blocked"
  ORPHAN_STALE_LABEL: "orphan-issue-stale"

jobs:
  sweep:
    name: scan and re-dispatch orphaned issues
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Scan, plan, and act
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_AUTHOR_PAT: ${{ secrets.PR_AUTHOR_PAT }}
          REPO: ${{ github.repository }}
          DRY_RUN_OVERRIDE: ${{ github.event.inputs.dry_run }}
        run: |
          set -euo pipefail

          dry_run="${DRY_RUN_OVERRIDE:-$DRY_RUN}"
          echo "DRY_RUN=$dry_run"

          # --- Gather the world -------------------------------------------------
          # Open issues WITH author_association + labels. The REST issues endpoint
          # returns both (unlike `gh issue list --json`), and includes PRs — which
          # we drop via `.pull_request == null`.
          gh api --paginate "repos/$REPO/issues?state=open&per_page=100" \
            > issues_raw.json

          # Numbers of issues that have a `claude/issue-N` branch on the remote.
          # matching-refs returns [] (200) when none match.
          gh api "repos/$REPO/git/matching-refs/heads/claude/issue-" \
            --jq '[.[].ref | capture("refs/heads/claude/issue-(?<n>[0-9]+)$") | .n | tonumber]' \
            > branch_nums.json || echo '[]' > branch_nums.json

          # Numbers of issues with an OPEN or MERGED PR whose head is their
          # `claude/issue-N` branch (our only PR-creation convention).
          gh pr list --repo "$REPO" --state all --limit 300 \
            --json number,headRefName,state \
            --jq '[.[] | select((.state=="OPEN" or .state=="MERGED") and (.headRefName|test("^claude/issue-[0-9]+$"))) | (.headRefName|ltrimstr("claude/issue-")|tonumber)]' \
            > pr_nums.json

          # Titles of implement runs currently queued/in_progress (best-effort
          # in-progress guard; run display title == the issue title).
          gh run list --repo "$REPO" --workflow "$IMPLEMENT_WORKFLOW" \
            --limit 40 --json displayTitle,status \
            --jq '[.[] | select(.status=="in_progress" or .status=="queued") | .displayTitle]' \
            > running_titles.json

          # --- Assemble the world JSON the decision core consumes ---------------
          jq -n \
            --slurpfile branch_nums branch_nums.json \
            --slurpfile pr_nums pr_nums.json \
            --slurpfile running running_titles.json \
            --argjson issues "$(jq '[.[] | select(.pull_request == null) | {number, title, author_association, labels: [.labels[].name]}]' issues_raw.json)" \
            --arg max "$MAX_ATTEMPTS" \
            --arg prefix "$ATTEMPT_LABEL_PREFIX" \
            --arg blocked "$BLOCKED_LABEL" \
            '{
              max_attempts: ($max | tonumber),
              attempt_label_prefix: $prefix,
              blocked_label: $blocked,
              trusted_associations: ["OWNER", "MEMBER", "COLLABORATOR"],
              issues: [
                $issues[] | . as $i | {
                  number: $i.number,
                  title: $i.title,
                  author_association: $i.author_association,
                  labels: $i.labels,
                  has_branch: ($branch_nums[0] | any(. == $i.number)),
                  has_linked_pr: ($pr_nums[0] | any(. == $i.number)),
                  in_progress: ($running[0] | any(. == $i.title))
                }
              ]
            }' > world.json

          echo "::group::world.json"; cat world.json; echo "::endgroup::"

          # --- Decide -----------------------------------------------------------
          python3 backend/scripts/orphan_issue_sweep.py --world world.json > plan.json
          echo "::group::plan.json"; cat plan.json; echo "::endgroup::"

          # --- Act --------------------------------------------------------------
          # DISPATCH: bump the attempt label (GITHUB_TOKEN) and re-run the
          # implement workflow (PR_AUTHOR_PAT — a GITHUB_TOKEN dispatch no-ops).
          jq -c '.dispatch[]' plan.json | while read -r row; do
            n="$(echo "$row" | jq -r .number)"
            add="$(echo "$row" | jq -r .add_label)"
            attempt="$(echo "$row" | jq -r .attempt)"
            echo "orphan #$n -> re-dispatch (attempt $attempt)"
            if [ "$dry_run" = "true" ]; then continue; fi
            gh label create "$add" --repo "$REPO" \
              --color ededed --description "Auto-implement retry attempt" 2>/dev/null || true
            echo "$row" | jq -r '.remove_labels[]?' | while read -r rl; do
              [ -n "$rl" ] && gh issue edit "$n" --repo "$REPO" --remove-label "$rl" 2>/dev/null || true
            done
            gh issue edit "$n" --repo "$REPO" --add-label "$add"
            GH_TOKEN="$PR_AUTHOR_PAT" gh workflow run "$IMPLEMENT_WORKFLOW" \
              --repo "$REPO" -f issue_number="$n"
          done

          # CLEAR: recovered issues (now have a PR) — drop stale attempt labels.
          jq -c '.clear[]' plan.json | while read -r row; do
            n="$(echo "$row" | jq -r .number)"
            echo "recovered #$n -> clearing stale attempt labels"
            if [ "$dry_run" = "true" ]; then continue; fi
            echo "$row" | jq -r '.remove_labels[]?' | while read -r rl; do
              [ -n "$rl" ] && gh issue edit "$n" --repo "$REPO" --remove-label "$rl" 2>/dev/null || true
            done
          done

          # SKIP: log only (visibility into why each open issue was left alone).
          jq -r '.skip[] | "skip #\(.number): \(.reason)"' plan.json || true

          # --- Alarm on cap-exhausted issues ------------------------------------
          alarm_nums="$(jq -r '[.alarm[].number] | join(", ")' plan.json)"
          existing="$(gh issue list --repo "$REPO" \
            --label "$ORPHAN_STALE_LABEL" --state open --limit 1 \
            --json number --jq '.[0].number // ""')"

          if [ -n "$alarm_nums" ]; then
            body="$(printf '## Auto-implement orphans exhausted their retry budget\n\nThese open issues have been re-dispatched %s times by the orphan sweeper without ever producing a PR, and will no longer be retried automatically:\n\n%s\n\n**What to check**\n- Open the issue and its latest `%s` run. Is it a persistent blocker (bad spec, un-passable tests) rather than a transient quota-out? If so, fix the spec and reopen the issue to reset the retry budget.\n- Was the day'"'"'s Claude subscription quota simply exhausted for a long stretch? Re-running `%s` manually (Actions -> Run workflow -> issue_number) will retry it.\n\nThis issue auto-closes once no open issue remains at the retry cap.\n\n_Filed by `claude-orphan-issue-sweeper.yml`._' \
              "$MAX_ATTEMPTS" \
              "$(jq -r '.alarm[] | "- #\(.number) (\(.attempts) attempts)"' plan.json)" \
              "$IMPLEMENT_WORKFLOW" "$IMPLEMENT_WORKFLOW")"
            echo "Cap-exhausted orphans: $alarm_nums"
            if [ "$dry_run" = "true" ]; then
              echo "(dry-run) would open/update alarm issue."
            elif [ -n "$existing" ]; then
              gh issue comment "$existing" --repo "$REPO" --body "$body"
            else
              gh label create "$ORPHAN_STALE_LABEL" --repo "$REPO" \
                --color b60205 --description "Auto-implement orphan hit its retry cap" 2>/dev/null || true
              gh issue create --repo "$REPO" \
                --title "alarm: auto-implement orphan(s) exhausted retries" \
                --label "$ORPHAN_STALE_LABEL" \
                --body "$body"
            fi
          else
            # No orphans at the cap: recover-close any open alarm.
            if [ -n "$existing" ] && [ "$dry_run" != "true" ]; then
              gh issue comment "$existing" --repo "$REPO" --body \
                "No open issues remain at the retry cap. Auto-closing."
              gh issue close "$existing" --repo "$REPO" --reason completed
            fi
          fi
```

- [ ] **Step 2: Verify the workflow parses as valid YAML**

Run: `cd backend && venv/bin/python -c "import yaml; yaml.safe_load(open('../.github/workflows/claude-orphan-issue-sweeper.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Smoke-test the world→plan wiring locally with a synthetic world**

This proves the core + JSON contract without needing GitHub. Run:

```bash
cd backend && printf '%s' '{
  "max_attempts": 3, "attempt_label_prefix": "implement-attempt-",
  "blocked_label": "implement-blocked",
  "trusted_associations": ["OWNER","MEMBER","COLLABORATOR"],
  "issues": [
    {"number": 1, "title": "orphan", "author_association": "OWNER", "labels": [], "has_linked_pr": false, "has_branch": false, "in_progress": false},
    {"number": 2, "title": "blocked", "author_association": "OWNER", "labels": ["implement-blocked"], "has_linked_pr": false, "has_branch": false, "in_progress": false},
    {"number": 3, "title": "capped", "author_association": "OWNER", "labels": ["implement-attempt-3"], "has_linked_pr": false, "has_branch": false, "in_progress": false}
  ]
}' | venv/bin/python scripts/orphan_issue_sweep.py --world -
```

Expected (one line, order may differ): `dispatch` contains #1 with `add_label` `implement-attempt-1`; `skip` contains #2 reason `blocked`; `alarm` contains `{"number": 3, "attempts": 3}`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/claude-orphan-issue-sweeper.yml
git commit -m "feat(ci): orphan-issue sweeper workflow (dry-run default)

Hourly cron gathers open-issue state, runs the decision core, and re-dispatches
orphans via PR_AUTHOR_PAT (GITHUB_TOKEN dispatch no-ops), alarming at the retry
cap. Ships DRY_RUN=true; arm by flipping to false after verifying against real
orphans.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Health coverage — 4th job on `claude-sweeper-health.yml`

**Files:**
- Modify: `.github/workflows/claude-sweeper-health.yml`

The orphan sweeper is a single job whose run-level conclusion IS the health signal (like `auto-merge`, unlike `fix-checks`). Reuse `sweeper_health.py --mode scan`: `last_run` = newest run of any conclusion (still ticking?), `last_success` = newest `success` run (scan logic still working?).

- [ ] **Step 1: Add the orphan-sweeper env block**

In `.github/workflows/claude-sweeper-health.yml`, inside the top-level `env:` map, append after the auto-merge block (after `AUTO_MERGE_STALE_LABEL: auto-merge-sweeper-stale`):

```yaml

  # --- orphan-issue sweeper (claude-orphan-issue-sweeper.yml) ---
  # Single job; run-level conclusion is the health signal (like auto-merge). Its
  # configured cadence is hourly (`40 * * * *`). Same ~4h grace window as the
  # copilot/fix-checks watchers: 60 * (3 + 1) = 240 min. A genuine >4h outage or
  # the 60-day auto-disable trips it; throttled hourly delivery does not.
  ORPHAN_SWEEPER_WORKFLOW: claude-orphan-issue-sweeper.yml
  ORPHAN_INTERVAL_MINUTES: "60"
  ORPHAN_MAX_MISSED_TICKS: "3"
  ORPHAN_SWEEPER_STALE_LABEL: orphan-sweeper-stale
```

- [ ] **Step 2: Add the `orphan-sweeper-health` job**

Append this job at the end of the `jobs:` map (after the `auto-merge-health` job). It mirrors `auto-merge-health` exactly, swapping env names, labels, and messages:

```yaml

  orphan-sweeper-health:
    name: check orphan-issue sweeper freshness
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Evaluate orphan sweeper health and alarm if needed
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail

          # last_run = newest run of any conclusion (still ticking?);
          # last_success = newest run that concluded `success` (scan logic still
          # working?). A run that dispatched nothing but scanned cleanly still
          # concludes success = healthy idle. A non-zero gh exit fails loudly
          # rather than masquerading as a benign empty result.
          if ! runs_json="$(gh run list \
            --repo "$REPO" \
            --workflow "$ORPHAN_SWEEPER_WORKFLOW" \
            --limit 30 \
            --json databaseId,createdAt,conclusion,status)"; then
            echo "::error::Failed to query run history for $ORPHAN_SWEEPER_WORKFLOW; cannot evaluate orphan sweeper health." >&2
            exit 1
          fi

          last_run="$(echo "$runs_json" | jq -r '.[0].createdAt // ""')"
          echo "Orphan sweeper last run: '${last_run:-<none>}'"

          last_success="$(echo "$runs_json" | jq -r \
            '[.[] | select(.status == "completed" and .conclusion == "success")][0].createdAt // ""')"
          echo "Orphan sweeper last successful run: '${last_success:-<none>}'"

          now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

          verdict="$(python3 backend/scripts/sweeper_health.py \
            --mode scan \
            --last-run "$last_run" \
            --last-success "$last_success" \
            --now "$now" \
            --interval-minutes "$ORPHAN_INTERVAL_MINUTES" \
            --max-missed-ticks "$ORPHAN_MAX_MISSED_TICKS")"
          echo "Verdict: $verdict"

          status="$(echo "$verdict" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
          detail="$(echo "$verdict" | python3 -c 'import json,sys; print(json.load(sys.stdin)["detail"])')"

          existing="$(gh issue list --repo "$REPO" \
            --label "$ORPHAN_SWEEPER_STALE_LABEL" --state open --limit 1 \
            --json number --jq '.[0].number // ""')"

          if [ "$status" = "stale" ] || [ "$status" = "broken" ]; then
            body="$(printf '## Orphan-issue sweeper appears %s\n\n%s\n\nRaw verdict:\n\n```json\n%s\n```\n\n**What to check**\n- If STALE (not ticking): is `%s` disabled? (Actions tab, or after 60 days of repo inactivity — re-enable with `gh workflow enable %s`, or push any commit to reset the 60-day clock.) Are scheduled workflows being throttled/skipped for this repo right now?\n- If BROKEN (run failing): open the latest `%s` run and read the `scan and re-dispatch orphaned issues` job log. A healthy tick concludes `success` whether or not it re-dispatched anything; a failing run means the scan/plan logic itself is erroring.\n\nThis issue auto-closes once the sweeper runs successfully within the expected window again.\n\n_Filed by `claude-sweeper-health.yml`._' "$status" "$detail" "$verdict" "$ORPHAN_SWEEPER_WORKFLOW" "$ORPHAN_SWEEPER_WORKFLOW" "$ORPHAN_SWEEPER_WORKFLOW")"
            if [ -n "$existing" ]; then
              echo "Alarm already open (#$existing); adding a status comment."
              gh issue comment "$existing" --repo "$REPO" --body "$body"
            else
              echo "Opening new orphan-sweeper alarm issue (status=$status)."
              gh label create "$ORPHAN_SWEEPER_STALE_LABEL" --repo "$REPO" \
                --color b60205 --description "orphan-issue sweeper is stale or its run is failing" \
                2>/dev/null || true
              gh issue create --repo "$REPO" \
                --title "alarm: orphan-issue sweeper is $status" \
                --label "$ORPHAN_SWEEPER_STALE_LABEL" \
                --body "$body"
            fi
          elif [ "$status" = "healthy" ]; then
            if [ -n "$existing" ]; then
              echo "Orphan sweeper recovered; closing alarm #$existing."
              gh issue comment "$existing" --repo "$REPO" --body \
                "Orphan-issue sweeper is running successfully on schedule again. $detail Auto-closing."
              gh issue close "$existing" --repo "$REPO" --reason completed
            else
              echo "Orphan sweeper healthy; no alarm open. Nothing to do."
            fi
          else
            # no_runs: sweeper not live on the default branch yet. Do nothing.
            echo "No orphan sweeper run history yet; not alarming. $detail"
          fi
```

- [ ] **Step 3: Verify the health workflow parses as valid YAML**

Run: `cd backend && venv/bin/python -c "import yaml; yaml.safe_load(open('../.github/workflows/claude-sweeper-health.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the existing sweeper-health tests (unchanged, must still pass)**

Run: `cd backend && venv/bin/python -m pytest tests/test_sweeper_health.py -q`
Expected: PASS (this task adds no Python; the test confirms `--mode scan` still behaves as the new job relies on).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/claude-sweeper-health.yml
git commit -m "feat(ci): watch orphan-issue sweeper in the health workflow

4th health job mirrors auto-merge-health (single-job, run-level conclusion is
the signal). Every claude-* sweeper is now observed from the outside.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (before opening the PR)

- [ ] **Run the full decision-core + health test pair**

Run: `cd backend && venv/bin/python -m pytest tests/test_orphan_issue_sweep.py tests/test_sweeper_health.py -q`
Expected: PASS.

- [ ] **Confirm no stray `github.event.issue` leaks in the implement job body**

Run: `grep -n 'github.event.issue' .github/workflows/claude-implement-issue.yml`
Expected: matches only in the `Resolve issue context` step's `env:` bindings and the `concurrency`/job-`if` expressions — never in the prompt, push, or PR steps.

- [ ] **Confirm the cron minute is unique**

Run: `grep -rn 'cron:' .github/workflows/`
Expected: minutes 0, 17, 30, 40, 45, 50 — `40` appears once (the new sweeper), colliding with none.

## After the PR merges — arming (human step, not automated)

The sweeper ships `DRY_RUN: "true"`. After merge:
1. Let one or two scheduled ticks run (or trigger `claude-orphan-issue-sweeper.yml` manually via Actions → Run workflow). Read the `world.json` / `plan.json` groups in the log and confirm the `dispatch`/`skip`/`alarm` split matches intent against the repo's real open issues.
2. When satisfied, flip `DRY_RUN` to `"false"` in a one-line follow-up commit to arm re-dispatch. The `workflow_dispatch` `dry_run` input can override either way for a single manual test run.

Prerequisite already satisfied: `PR_AUTHOR_PAT` exists (used by `claude-implement-issue.yml`) and carries `workflow`/`actions:write` scope, so no new secret is needed.

---

## Self-Review notes (completed by plan author)

- **Spec coverage:** Part 1 (dispatch + shim + trust re-check + terminal labels) → Task 2. Part 2 (predicate, retry cap, alarm, decision core, dry-run) → Tasks 1 + 3. Part 3 (health job) → Task 4. All spec sections mapped.
- **Type/name consistency:** world keys (`max_attempts`, `attempt_label_prefix`, `blocked_label`, `trusted_associations`, `issues[].{number,title,author_association,labels,has_linked_pr,has_branch,in_progress}`) and plan buckets (`dispatch`/`alarm`/`clear`/`skip`) are identical across the core, its tests, and the sweeper's `jq` assembly + `plan.json` consumer. `add_label`/`remove_labels`/`attempt`/`attempts` field names match between `plan_sweep` output and the workflow's `jq` reads.
- **No placeholders:** every code/YAML step is complete and copy-pasteable.
