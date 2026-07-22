# Triage-dispatch throttle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Meter recommender-filed issues into the auto-implementer highest-score-first, capped by open-PR backpressure, so the backlog stops piling up and stops quota-dying.

**Architecture:** The recommender fills a backlog (issues labelled `triage-queued`, each carrying a `<!-- autotiers:rec score=N -->` body marker). A new deterministic dispatcher workflow reacts to PR-close and issue-open events, counts in-flight `claude/issue-*` PRs, and `workflow_dispatch`es the top-score queued issues to fill open slots. The implementer skips marker-bearing issues on `opened`; the orphan sweeper skips still-queued issues. No Claude runs in the throttle.

**Tech Stack:** GitHub Actions (YAML), `gh` CLI, Python 3.14 pure-function decision cores (pytest), `jq`.

**Repo conventions used below:**
- Backend tests run with the repo venv: `backend/venv/bin/pytest`.
- Decision cores live in `backend/scripts/`, are pure `world → plan` functions, and are unit-tested in `backend/tests/`. This plan mirrors `orphan_issue_sweep.py` / `test_orphan_issue_sweep.py`.
- Workflow dispatch that must trigger another workflow uses `PR_AUTHOR_PAT` (a `GITHUB_TOKEN` `workflow run` is suppressed by GitHub's recursion guard).

---

## File structure

- Create: `backend/scripts/triage_dispatch.py` — pure decision core (slot math + score-sort + marker parse).
- Create: `backend/tests/test_triage_dispatch.py` — unit tests for the core.
- Create: `.github/workflows/claude-triage-dispatch.yml` — the dispatcher workflow.
- Modify: `backend/scripts/improvement_recommend_select.py` — carry `score` through to output.
- Modify: `backend/tests/test_improvement_recommend_select.py` — assert score is carried.
- Modify: `.github/workflows/claude-improvement-recommender.yml` — embed marker + `triage-queued` label.
- Modify: `.github/workflows/claude-implement-issue.yml` — skip marker-bearing issues on `opened`/`reopened`.
- Modify: `.github/workflows/claude-orphan-issue-sweeper.yml` + `backend/scripts/orphan_issue_sweep.py` + its test — skip `triage-queued` issues.

---

### Task 1: Carry `score` through the recommender selector

The selector currently drops `score` from its output (`{title, area, body}`). The dispatcher needs the score persisted into the filed issue, so `select()` must include it.

**Files:**
- Modify: `backend/scripts/improvement_recommend_select.py:105`
- Test: `backend/tests/test_improvement_recommend_select.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_improvement_recommend_select.py`:

```python
def test_select_carries_score_through_to_output():
    world = {
        "max_issues": 5,
        "existing": [],
        "candidates": [
            {"title": "Alpha", "area": "qa", "body": "spec", "score": 8.5},
            {"title": "Beta", "area": "ux", "body": "spec", "score": 3},
        ],
    }
    kept = select(world)
    assert [k["title"] for k in kept] == ["Alpha", "Beta"]  # score-desc order
    assert kept[0]["score"] == 8.5
    assert kept[1]["score"] == 3.0  # coerced to float


def test_select_defaults_missing_or_bad_score_to_zero():
    world = {
        "max_issues": 5,
        "existing": [],
        "candidates": [
            {"title": "NoScore", "area": "qa", "body": "spec"},
            {"title": "BadScore", "area": "qa", "body": "spec", "score": "high"},
        ],
    }
    kept = {k["title"]: k for k in select(world)}
    assert kept["NoScore"]["score"] == 0.0
    assert kept["BadScore"]["score"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/pytest backend/tests/test_improvement_recommend_select.py::test_select_carries_score_through_to_output -v`
Expected: FAIL with `KeyError: 'score'`.

- [ ] **Step 3: Implement — include the float score in the kept dict**

In `backend/scripts/improvement_recommend_select.py`, change the `kept.append(...)` line inside `select()` (currently line 105):

```python
        kept.append({"title": title, "area": _text(c.get("area")), "body": body, "score": _score(c)})
```

`_score` already returns a float and defaults missing/non-numeric to `0.0`, so both tests are satisfied without new helpers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/venv/bin/pytest backend/tests/test_improvement_recommend_select.py -v`
Expected: PASS (all, including the two new tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/improvement_recommend_select.py backend/tests/test_improvement_recommend_select.py
git commit -m "feat(recommender): carry candidate score through selector output"
```

---

### Task 2: Dispatcher decision core `triage_dispatch.py`

Pure `world → plan`: parse each queued issue's score marker, sort desc, and pick enough top issues to fill `cap - inflight` open slots.

**Files:**
- Create: `backend/scripts/triage_dispatch.py`
- Test: `backend/tests/test_triage_dispatch.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_triage_dispatch.py`:

```python
from backend.scripts.triage_dispatch import parse_score, plan_dispatch


def test_parse_score_wellformed():
    assert parse_score("blah\n\n<!-- autotiers:rec score=8.5 -->") == 8.5


def test_parse_score_integer_and_negative():
    assert parse_score("<!-- autotiers:rec score=3 -->") == 3.0
    assert parse_score("<!-- autotiers:rec score=-2 -->") == -2.0


def test_parse_score_missing_or_bad_defaults_zero():
    assert parse_score("no marker here") == 0.0
    assert parse_score("<!-- autotiers:rec score=high -->") == 0.0


def _issue(number, score=None, label="triage-queued"):
    marker = "" if score is None else f"\n<!-- autotiers:rec score={score} -->"
    return {"number": number, "body": f"spec{marker}", "labels": [label]}


def test_dispatch_fills_free_slots_highest_score_first():
    world = {
        "cap": 2,
        "inflight": 0,
        "queued_label": "triage-queued",
        "issues": [_issue(10, 3), _issue(11, 9), _issue(12, 5)],
    }
    plan = plan_dispatch(world)
    assert plan["slots"] == 2
    assert [d["number"] for d in plan["dispatch"]] == [11, 12]  # 9, then 5


def test_dispatch_respects_inflight_backpressure():
    world = {
        "cap": 2,
        "inflight": 2,
        "queued_label": "triage-queued",
        "issues": [_issue(10, 9)],
    }
    plan = plan_dispatch(world)
    assert plan["slots"] == 0
    assert plan["dispatch"] == []


def test_dispatch_slots_never_negative():
    world = {"cap": 2, "inflight": 5, "queued_label": "triage-queued", "issues": [_issue(10, 9)]}
    assert plan_dispatch(world)["slots"] == 0


def test_dispatch_tiebreak_lowest_number_first():
    world = {
        "cap": 3,
        "inflight": 0,
        "queued_label": "triage-queued",
        "issues": [_issue(12, 5), _issue(10, 5), _issue(11, 5)],
    }
    plan = plan_dispatch(world)
    assert [d["number"] for d in plan["dispatch"]] == [10, 11, 12]


def test_dispatch_ignores_issues_missing_queued_label():
    world = {
        "cap": 2,
        "inflight": 0,
        "queued_label": "triage-queued",
        "issues": [_issue(10, 9, label="recommendation")],  # not queued
    }
    assert plan_dispatch(world)["dispatch"] == []


def test_dispatch_missing_marker_sorts_last():
    world = {
        "cap": 1,
        "inflight": 0,
        "queued_label": "triage-queued",
        "issues": [_issue(10, None), _issue(11, 1)],
    }
    # issue 11 (score 1) beats issue 10 (no marker -> 0)
    assert [d["number"] for d in plan_dispatch(world)["dispatch"]] == [11]


def test_dispatch_empty_backlog():
    world = {"cap": 2, "inflight": 0, "queued_label": "triage-queued", "issues": []}
    assert plan_dispatch(world) == {"dispatch": [], "slots": 2}
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/venv/bin/pytest backend/tests/test_triage_dispatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.scripts.triage_dispatch'`.

- [ ] **Step 3: Implement the core**

Create `backend/scripts/triage_dispatch.py`:

```python
"""Decision core for the triage dispatcher (`.github/workflows/claude-triage-dispatch.yml`).

The improvement recommender files backlog issues labelled `triage-queued`, each
carrying a `<!-- autotiers:rec score=N -->` marker in its body. This module is
the PURE decision: given a snapshot of repo state (`world`) — the concurrency
cap, the count of in-flight `claude/issue-*` PRs, and the queued issues — it
returns which issues to dispatch to `claude-implement-issue.yml` to fill the
open slots, highest score first.

Keeping the slot math + score-sort here (not in shell) lets us unit-test the
boundaries an `if`-chain gets wrong (cap<=inflight, tie-breaks, malformed
markers). The workflow shell then, for each dispatched issue, removes the
`triage-queued` label and dispatches the implement workflow via PR_AUTHOR_PAT.

world (stdin/file JSON):
    {
      "cap": 2,
      "inflight": 1,
      "queued_label": "triage-queued",
      "issues": [
        {"number": 12, "body": "spec\\n<!-- autotiers:rec score=8.5 -->",
         "labels": ["recommendation", "triage-queued"]}
      ]
    }

plan (stdout JSON):
    {"dispatch": [{"number": 12, "score": 8.5}], "slots": 2}

`slots` is the number of free slots computed (cap - inflight, floored at 0);
`dispatch` is at most `slots` issues, best score first. A malformed world (bad
JSON, missing key) raises and exits non-zero so a broken input is loud.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

_SCORE_RE = re.compile(r"<!--\s*autotiers:rec\s+score=([-+]?\d*\.?\d+)\s*-->")


def parse_score(body: str) -> float:
    """Score from the body marker; 0.0 when absent or non-numeric."""
    if not body:
        return 0.0
    m = _SCORE_RE.search(body)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except ValueError:
        return 0.0


def plan_dispatch(world: dict) -> dict:
    cap = int(world["cap"])
    inflight = int(world["inflight"])
    queued_label = world["queued_label"]
    slots = max(cap - inflight, 0)

    # Only genuinely-queued issues are candidates (defensive: the shell already
    # queries by label, but a stale/edited label list must not slip through).
    queued = [
        i for i in world.get("issues", [])
        if queued_label in i.get("labels", [])
    ]
    # Highest score first; deterministic tiebreak on ascending issue number.
    ordered = sorted(
        queued,
        key=lambda i: (-parse_score(i.get("body", "")), int(i["number"])),
    )
    dispatch = [
        {"number": int(i["number"]), "score": parse_score(i.get("body", ""))}
        for i in ordered[:slots]
    ]
    return {"dispatch": dispatch, "slots": slots}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--world",
        default="-",
        help="Path to the world JSON, or '-' (default) to read stdin.",
    )
    args = parser.parse_args(argv)
    raw = sys.stdin.read() if args.world == "-" else open(args.world, encoding="utf-8").read()
    plan = plan_dispatch(json.loads(raw))
    json.dump(plan, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `backend/venv/bin/pytest backend/tests/test_triage_dispatch.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/triage_dispatch.py backend/tests/test_triage_dispatch.py
git commit -m "feat(triage): add deterministic triage-dispatch decision core"
```

---

### Task 3: Recommender embeds score marker + `triage-queued` label

The recommender must persist the score marker in each issue body and label each
issue `triage-queued` so the dispatcher can find and rank it. Note `recommendations.json` now carries `.score` (Task 1).

**Files:**
- Modify: `.github/workflows/claude-improvement-recommender.yml` (the "File recommendation issues" step, lines ~389-452)

- [ ] **Step 1: Add `triage-queued` label bootstrap**

In the "File recommendation issues" step, find the `dry_run != "true"` label-create block (currently ~lines 402-406) and add a second `gh label create` beneath the existing one:

```bash
          if [ "$dry_run" != "true" ]; then
            gh label create "$REC_LABEL" --repo "$REPO" \
              --color 0e8a16 --description "Proactive improvement recommendation (auto-filed)" \
              2>/dev/null || true
            gh label create "triage-queued" --repo "$REPO" \
              --color 1d76db --description "Recommendation awaiting the triage dispatcher" \
              2>/dev/null || true
          fi
```

- [ ] **Step 2: Read the score and append the marker to the body**

Inside the `jq -c '.[]' recommendations.json | while read -r row; do` loop, add a `score` read next to the existing `title`/`body`/`area` reads (~lines 409-411):

```bash
            title="$(echo "$row" | jq -r .title)"
            body="$(echo "$row" | jq -r .body)"
            area="$(echo "$row" | jq -r .area)"
            score="$(echo "$row" | jq -r '.score // 0')"
```

Then change the `gh issue create` `printf` (currently ~lines 431-434) to append the marker line after the "Filed by" footer:

```bash
            issue_url="$(printf '%s\n\n_Filed by `claude-improvement-recommender.yml` (area: %s)._\n\n<!-- autotiers:rec score=%s -->' \
              "$body" "$area" "$score" \
              | gh issue create --repo "$REPO" --label "$REC_LABEL" \
                  --title "$title" --body-file -)"
```

- [ ] **Step 3: Apply the `triage-queued` label alongside `recommendation`**

The step already re-applies `$REC_LABEL` via `gh issue edit` (the load-bearing label guarantee, ~line 447). Extend that same edit to add `triage-queued` in one call so the issue enters the backlog atomically. Replace the existing edit-and-verify block:

```bash
            # Re-apply both labels explicitly and verify. NO `|| true`: if this
            # fails, the step must fail so a silent label drop can't leave an
            # unlabeled (undispatchable / un-dedupable) recommendation issue.
            if ! gh issue edit "$issue_num" --repo "$REPO" \
                 --add-label "$REC_LABEL" --add-label "triage-queued"; then
              echo "::error::failed to apply the '$REC_LABEL'/'triage-queued' labels to issue #$issue_num (does PR_AUTHOR_PAT have Issues:Write?); refusing to continue with unlabeled recommendation issues"
              exit 1
            fi
            echo "labeled #$issue_num with '$REC_LABEL' + 'triage-queued'"
```

- [ ] **Step 4: Verify the workflow YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/claude-improvement-recommender.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/claude-improvement-recommender.yml
git commit -m "feat(recommender): tag filed issues with score marker + triage-queued label"
```

---

### Task 4: Implementer skips marker-bearing issues on open

Recommendation issues must not auto-implement on `opened`/`reopened`; they wait for the dispatcher. The reliable discriminator at webhook time is the body marker (the `recommendation` label is applied post-create — see the design's label-race note). Human-opened issues (no marker) keep implementing immediately; the `workflow_dispatch` path is untouched.

**Files:**
- Modify: `.github/workflows/claude-implement-issue.yml:46-48`

- [ ] **Step 1: Add the marker exclusion to the job `if:`**

Replace the job-level `if:` block (currently lines 46-48):

```yaml
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association) &&
       !contains(github.event.issue.body, 'autotiers:rec'))
```

`workflow_dispatch` short-circuits the `||` first (no `issue.body` exists on that event, and it's never evaluated), so the dispatcher's and orphan sweeper's dispatches still implement recommendation issues normally. On an `issues` event, a body containing the `autotiers:rec` marker is skipped; a human issue without it runs as before.

- [ ] **Step 2: Update the header comment to document the gate**

Just below the existing top-of-file comment block (before `on:`, ~line 17), add:

```yaml
# NOTE: recommendation issues (body carries `<!-- autotiers:rec ... -->`) are
# deliberately SKIPPED on issues:opened — they are throttled by
# claude-triage-dispatch.yml, which dispatches them here via workflow_dispatch
# when a slot is free. The body marker (not the `recommendation` label) is the
# discriminator because the label is applied post-create and is absent from the
# opened webhook payload.
```

- [ ] **Step 3: Verify the workflow YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/claude-implement-issue.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/claude-implement-issue.yml
git commit -m "feat(implement): skip triage-queued recommendation issues on open"
```

---

### Task 5: The dispatcher workflow

Event-driven, deterministic, no Claude. Counts in-flight `claude/issue-*` PRs, computes free slots, and dispatches the top-score queued issues.

**Files:**
- Create: `.github/workflows/claude-triage-dispatch.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/claude-triage-dispatch.yml`:

```yaml
name: claude-triage-dispatch

# Deterministic throttle between the improvement recommender and the
# auto-implementer. The recommender files backlog issues labelled `triage-queued`
# with a `<!-- autotiers:rec score=N -->` body marker. This workflow reacts to a
# freed slot (a PR closing) or new intake (an issue opening), counts in-flight
# `claude/issue-*` PRs, and dispatches the top-score queued issues to
# claude-implement-issue.yml to fill up to CAP concurrent slots. It invokes NO
# Claude — selection is a pure Python decision core.
#
# TOKEN SPLIT (correctness-critical): the `gh workflow run` DISPATCH uses
# PR_AUTHOR_PAT, because a GITHUB_TOKEN-triggered workflow_dispatch is suppressed
# by GitHub's recursion guard (same rule as the orphan sweeper). Label writes use
# the built-in GITHUB_TOKEN.
#
# Design: docs/superpowers/specs/2026-07-21-triage-dispatch-throttle-design.md

on:
  pull_request:
    types: [closed] # a slot may have freed
  issues:
    types: [opened, reopened] # cold-start seed: start an empty pipe
  workflow_dispatch: {} # manual recovery lever

concurrency:
  # Serialize ticks so two events never both dispatch (and double-drain) slots.
  group: claude-triage-dispatch
  cancel-in-progress: false

permissions:
  contents: read # actions/checkout for the decision core
  issues: write # remove the triage-queued label on dispatch
  pull-requests: read # count in-flight claude/issue-* PRs

env:
  CAP: "2" # max concurrent open auto-implement PRs
  QUEUED_LABEL: "triage-queued"
  IMPLEMENT_WORKFLOW: claude-implement-issue.yml

jobs:
  dispatch:
    name: dispatch queued recommendations to fill open slots
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Scan, plan, and dispatch
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_AUTHOR_PAT: ${{ secrets.PR_AUTHOR_PAT }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail

          # --- Gather the world -----------------------------------------------
          # In-flight = open PRs whose head is a `claude/issue-N` branch.
          inflight="$(gh pr list --repo "$REPO" --state open --limit 300 \
            --json headRefName \
            --jq '[.[] | select(.headRefName | test("^claude/issue-[0-9]+$"))] | length')"

          # Queued backlog issues with body + label names.
          gh issue list --repo "$REPO" --label "$QUEUED_LABEL" --state open \
            --limit 200 --json number,body,labels \
            --jq '[.[] | {number, body, labels: [.labels[].name]}]' > queued.json

          jq -n \
            --arg cap "$CAP" \
            --arg inflight "$inflight" \
            --arg queued "$QUEUED_LABEL" \
            --slurpfile issues queued.json \
            '{cap: ($cap|tonumber), inflight: ($inflight|tonumber),
              queued_label: $queued, issues: $issues[0]}' > world.json

          echo "::group::world.json"; cat world.json; echo "::endgroup::"

          # --- Decide ---------------------------------------------------------
          python3 backend/scripts/triage_dispatch.py --world world.json > plan.json
          echo "::group::plan.json"; cat plan.json; echo "::endgroup::"

          slots="$(jq -r .slots plan.json)"
          count="$(jq -r '.dispatch | length' plan.json)"
          {
            echo "### Triage dispatch"
            echo ""
            echo "| metric | value |"
            echo "|---|---|"
            echo "| CAP | $CAP |"
            echo "| in-flight PRs | $inflight |"
            echo "| free slots | $slots |"
            echo "| dispatched | $count |"
          } >> "$GITHUB_STEP_SUMMARY"

          # --- Act ------------------------------------------------------------
          # For each selected issue: drop triage-queued (GITHUB_TOKEN) so it is
          # never re-selected, then dispatch implement (PR_AUTHOR_PAT — a
          # GITHUB_TOKEN dispatch no-ops). Order matters: remove the label first
          # so a mid-loop failure can't leave a dispatched issue still queued.
          jq -c '.dispatch[]' plan.json | while read -r row; do
            n="$(echo "$row" | jq -r .number)"
            s="$(echo "$row" | jq -r .score)"
            echo "dispatch #$n (score $s)"
            gh issue edit "$n" --repo "$REPO" --remove-label "$QUEUED_LABEL"
            GH_TOKEN="$PR_AUTHOR_PAT" gh workflow run "$IMPLEMENT_WORKFLOW" \
              --repo "$REPO" -f issue_number="$n"
          done
```

- [ ] **Step 2: Verify the workflow YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/claude-triage-dispatch.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Verify the decision core wires to the shell contract**

Run this local smoke test of the exact `jq` → python path the workflow uses:

```bash
printf '[{"number":11,"body":"spec\\n<!-- autotiers:rec score=9 -->","labels":["triage-queued"]},{"number":12,"body":"spec\\n<!-- autotiers:rec score=5 -->","labels":["triage-queued"]}]' > /tmp/queued.json
jq -n --arg cap 2 --arg inflight 0 --arg queued triage-queued --slurpfile issues /tmp/queued.json \
  '{cap:($cap|tonumber),inflight:($inflight|tonumber),queued_label:$queued,issues:$issues[0]}' \
  | python3 backend/scripts/triage_dispatch.py --world -
```
Expected: `{"dispatch": [{"number": 11, "score": 9.0}, {"number": 12, "score": 5.0}], "slots": 2}`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/claude-triage-dispatch.yml
git commit -m "feat(triage): add event-driven triage-dispatch workflow"
```

---

### Task 6: Orphan sweeper skips queued backlog

An undispatched backlog issue (no branch, no PR, not blocked, not in-progress) matches the orphan predicate exactly, so the sweeper would re-dispatch it and bypass the throttle. Teach the core to skip any issue still carrying `triage-queued`.

**Files:**
- Modify: `backend/scripts/orphan_issue_sweep.py` (`plan_sweep`)
- Modify: `backend/tests/test_orphan_issue_sweep.py`
- Modify: `.github/workflows/claude-orphan-issue-sweeper.yml` (world assembly)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_orphan_issue_sweep.py`:

```python
def test_triage_queued_issue_is_skipped_not_dispatched():
    world = {
        "max_attempts": 3,
        "attempt_label_prefix": "implement-attempt-",
        "blocked_label": "implement-blocked",
        "queued_label": "triage-queued",
        "trusted_associations": ["OWNER", "MEMBER", "COLLABORATOR"],
        "issues": [
            {
                "number": 42,
                "title": "Queued rec",
                "author_association": "OWNER",
                "labels": ["recommendation", "triage-queued"],
                "has_linked_pr": False,
                "has_branch": False,
                "in_progress": False,
            }
        ],
    }
    plan = plan_sweep(world)
    assert plan["dispatch"] == []
    assert {"number": 42, "reason": "triage_queued"} in plan["skip"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/venv/bin/pytest backend/tests/test_orphan_issue_sweep.py::test_triage_queued_issue_is_skipped_not_dispatched -v`
Expected: FAIL — the issue is classified as an orphan and appears in `dispatch`, not `skip`.

- [ ] **Step 3: Implement the skip predicate**

In `backend/scripts/orphan_issue_sweep.py`, read the queued label at the top of `plan_sweep` (next to the other label reads):

```python
    blocked = world["blocked_label"]
    queued_label = world.get("queued_label", "triage-queued")
    trusted = set(world["trusted_associations"])
```

Then add the skip check in the per-issue loop, placed after the trust gate and before the `has_linked_pr` check (an intentional backlog issue must be left completely untouched — no `clear` housekeeping):

```python
        if issue.get("author_association") not in trusted:
            skip.append({"number": number, "reason": "untrusted_author"})
            continue

        # Undispatched triage backlog: intentionally waiting for the triage
        # dispatcher, NOT an orphan. Leave it entirely alone.
        if queued_label in labels:
            skip.append({"number": number, "reason": "triage_queued"})
            continue
```

- [ ] **Step 4: Run to verify it passes**

Run: `backend/venv/bin/pytest backend/tests/test_orphan_issue_sweep.py -v`
Expected: PASS (all).

- [ ] **Step 5: Pass `queued_label` from the sweeper workflow**

In `.github/workflows/claude-orphan-issue-sweeper.yml`, add the env var to the `env:` block (~line 62, next to `ORPHAN_STALE_LABEL`):

```yaml
  ORPHAN_STALE_LABEL: "orphan-issue-stale"
  QUEUED_LABEL: "triage-queued"
```

Then in the `jq -n` world-assembly (the block starting ~line 123), add the arg and field:

```bash
            --arg blocked "$BLOCKED_LABEL" \
            --arg queued "$QUEUED_LABEL" \
```

and inside the assembled object, next to `blocked_label: $blocked,`:

```bash
              blocked_label: $blocked,
              queued_label: $queued,
```

- [ ] **Step 6: Verify YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/claude-orphan-issue-sweeper.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/orphan_issue_sweep.py backend/tests/test_orphan_issue_sweep.py .github/workflows/claude-orphan-issue-sweeper.yml
git commit -m "feat(orphan-sweeper): skip triage-queued backlog issues"
```

---

### Task 7: Full backend test sweep

Confirm nothing regressed across the two touched cores.

- [ ] **Step 1: Run the affected suites**

Run:
```bash
backend/venv/bin/pytest backend/tests/test_triage_dispatch.py \
  backend/tests/test_orphan_issue_sweep.py \
  backend/tests/test_improvement_recommend_select.py -v
```
Expected: PASS (all). Do NOT run the full `pytest` (memory: `tests/test_sources` OOMs); these three files cover every core changed here.

- [ ] **Step 2: Final YAML sanity across all touched workflows**

Run:
```bash
for f in claude-triage-dispatch claude-improvement-recommender claude-implement-issue claude-orphan-issue-sweeper; do
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/$f.yml')); print('$f ok')"
done
```
Expected: four `... ok` lines.

---

## Deferred to arming (out of plan scope, human gate)

These are deliberate follow-ups, not code tasks — the loop should ship inert and be armed by a human, mirroring how the recommender/orphan-sweeper were armed:

- The dispatcher ships functional but the throttle only bites once the recommender is filing `triage-queued` issues (Task 3) AND the implementer's skip gate is live (Task 4). Land all tasks together.
- Confirm `PR_AUTHOR_PAT` can dispatch `claude-implement-issue.yml` (it already does for the orphan sweeper — same secret, same mechanism).
- First real firing: watch one recommender run → confirm N issues filed carry the marker + `triage-queued`, then confirm the dispatcher drains only `CAP` of them and the rest wait. `workflow_dispatch` the dispatcher once to prime if the pipe is empty.
- Tune `CAP` (default 2) after observing quota headroom.

---

## Self-review notes

- **Spec coverage:** selector score persistence (T1), dispatcher core + marker parse/slot math/sort (T2), recommender marker+label (T3), implementer skip gate with label-race-safe body discriminator (T4), event-driven dispatcher with PR-close + issue-open + manual triggers and PAT dispatch (T5), orphan-sweeper coordination (T6). Cold-start seed = `issues: opened` trigger in T5. Lifecycle hand-off = label removal in T5 + skip in T6. All spec sections mapped.
- **Type consistency:** `plan_dispatch` returns `{"dispatch": [{number, score}], "slots": int}` — consumed as `.dispatch[]`/`.slots` in T5 shell. `parse_score` used in both tests and core. `queued_label` key threaded through T6 core + workflow. Marker string `autotiers:rec` identical in recommender emit (T3), implementer gate (T4), and core regex (T2).
- **No placeholders:** every code/step is concrete.
