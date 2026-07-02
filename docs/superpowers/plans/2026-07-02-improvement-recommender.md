# Daily Improvement Recommender Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily GitHub Actions workflow in which three specialist agents (researcher/designer/engineer) examine the app plus newly-available external inputs and file the top-5 improvement recommendations as issues that feed the existing `claude-implement-issue` autonomous loop.

**Architecture:** `claude-code-action` runs an orchestrator prompt that dispatches the three specialists via `Task` and writes raw candidates to `candidates.json`. A deterministic, unit-tested Python core (`improvement_recommend_select.py`) dedups against already-tracked recommendation issues, orders by the agent-assigned score, and caps to `MAX_ISSUES`. A final shell step files the survivors as `recommendation` issues authenticated as `PR_AUTHOR_PAT` (the only credential that both fires `issues: opened` and passes the downstream trusted-author gate). Ships `DRY_RUN: "true"`.

**Tech Stack:** GitHub Actions, `anthropics/claude-code-action@v1`, `gh` CLI, `jq`, Python 3.14 (stdlib only), pytest.

**Spec:** `docs/superpowers/specs/2026-07-02-improvement-recommender-design.md`

---

## File Structure

- **Create** `backend/scripts/improvement_recommend_select.py` — pure selection core: dedup + rank + cap. Mirrors `backend/scripts/orphan_issue_sweep.py`.
- **Create** `backend/tests/test_improvement_recommend_select.py` — unit tests for the core. Mirrors `backend/tests/test_orphan_issue_sweep.py`.
- **Create** `.github/workflows/claude-improvement-recommender.yml` — the daily workflow (thin shell + the Python core + `claude-code-action`).

---

## Task 1: Selection decision core (dedup + rank + cap)

**Files:**
- Create: `backend/scripts/improvement_recommend_select.py`
- Test: `backend/tests/test_improvement_recommend_select.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_improvement_recommend_select.py`:

```python
"""Tests for the improvement-recommender selection core.

Three specialist agents emit candidate recommendations; this core turns that
raw pile into the small, de-duplicated, best-first list the workflow actually
files as issues. These tests lock the boundaries the untestable shell relies
on: ordering by score, capping to MAX_ISSUES, suppressing anything that
duplicates an already-tracked issue OR an already-kept candidate, and tolerating
malformed / empty / garbage input without raising (a bad LLM generation must
never fail the daily schedule).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from scripts.improvement_recommend_select import _is_duplicate, main, select


def _cand(title, score=5.0, area="internals", body="do the thing"):
    return {"title": title, "area": area, "body": body, "score": score}


def test_orders_by_score_desc():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        _cand("low", 1.0), _cand("high", 9.0), _cand("mid", 5.0)]})
    assert [c["title"] for c in out] == ["high", "mid", "low"]


def test_caps_at_max_issues():
    cands = [_cand(f"rec {i}", score=i) for i in range(10)]
    out = select({"max_issues": 3, "existing": [], "candidates": cands})
    assert [c["title"] for c in out] == ["rec 9", "rec 8", "rec 7"]


def test_suppresses_duplicate_of_existing_issue():
    out = select({"max_issues": 5,
                  "existing": [{"title": "Add ADP reconciliation to tier math"}],
                  "candidates": [_cand("Add ADP reconciliation to tier math", 9.0),
                                 _cand("Upgrade tailwind to v4", 5.0)]})
    assert [c["title"] for c in out] == ["Upgrade tailwind to v4"]


def test_suppresses_duplicate_among_candidates():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        _cand("Improve export button contrast", 9.0),
        _cand("improve the export button contrast!", 8.0)]})
    assert len(out) == 1
    assert out[0]["title"] == "Improve export button contrast"


def test_drops_malformed_candidate():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        {"title": "", "body": "x", "score": 9},
        {"title": "no body", "body": "", "score": 8},
        _cand("valid", 1.0)]})
    assert [c["title"] for c in out] == ["valid"]


def test_empty_and_nonlist_input_is_safe():
    assert select({"max_issues": 5, "existing": [], "candidates": []}) == []
    assert select({"max_issues": 5}) == []
    assert select({"max_issues": 5, "candidates": "garbage"}) == []


def test_is_duplicate_unrelated_titles_false():
    assert not _is_duplicate("Upgrade jenkspy clustering", ["Redesign the export modal"])


def test_result_shape_is_title_area_body_only():
    out = select({"max_issues": 5, "existing": [], "candidates": [_cand("x", 1.0)]})
    assert set(out[0].keys()) == {"title", "area", "body"}


def test_main_reads_files_and_writes_json(tmp_path):
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps([_cand("A", 9.0), _cand("B", 1.0)]))
    exist = tmp_path / "existing.json"
    exist.write_text(json.dumps([{"title": "A"}]))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--candidates", str(cand), "--existing", str(exist), "--max", "5"])
    assert rc == 0
    assert [c["title"] for c in json.loads(buf.getvalue())] == ["B"]


def test_main_tolerates_garbage_file(tmp_path):
    cand = tmp_path / "candidates.json"
    cand.write_text("not json{{{")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--candidates", str(cand), "--max", "5"])
    assert rc == 0
    assert json.loads(buf.getvalue()) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_improvement_recommend_select.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.improvement_recommend_select'`.

- [ ] **Step 3: Write the implementation**

Create `backend/scripts/improvement_recommend_select.py`:

```python
"""Selection core for the daily improvement recommender
(`.github/workflows/claude-improvement-recommender.yml`).

Three specialist agents (researcher/designer/engineer) each emit candidate
improvement recommendations into `candidates.json`. This module is the PURE,
testable selection step: given all candidates plus the recommendations already
tracked as open/recently-closed GitHub issues, it drops duplicates, orders by
the agent-assigned value/effort `score`, and caps the result to `max_issues`.
The workflow's shell then files exactly these as issues.

Keeping selection here (not in the LLM prompt or shell) makes the
dedup/cap/ordering boundaries deterministic and unit-tested; the LLM still
*generates* and *scores* candidates, but cannot flood the tracker or refile a
standing recommendation.

world (input dict):
    {
      "max_issues": 5,
      "existing": [{"number": 12, "title": "...", "state": "open"}],
      "candidates": [
        {"title": "...", "area": "rankings", "body": "...", "score": 8.5}
      ]
    }

result (return value): the surviving candidates, ordered best-first, capped:
    [{"title": "...", "area": "...", "body": "..."}]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(title: str) -> set[str]:
    """Lowercased alphanumeric word tokens of a title, for fuzzy comparison."""
    return set(_WORD_RE.findall(title.lower()))


def _is_duplicate(cand_title: str, existing_titles: list[str], threshold: float = 0.7) -> bool:
    """True if cand_title's word tokens overlap any existing title's at
    >= threshold (Jaccard). Robust to reordering/punctuation but keeps two
    unrelated titles distinct. A title with no word tokens never matches.
    """
    ctoks = _tokens(cand_title)
    if not ctoks:
        return False
    for et in existing_titles:
        etoks = _tokens(et)
        if not etoks:
            continue
        if len(ctoks & etoks) / len(ctoks | etoks) >= threshold:
            return True
    return False


def select(world: dict) -> list[dict]:
    max_issues = int(world.get("max_issues", 5))
    existing = world.get("existing") or []
    candidates = world.get("candidates")
    if not isinstance(candidates, list):
        candidates = []

    seen_titles: list[str] = [e.get("title", "") for e in existing if isinstance(e, dict)]
    kept: list[dict] = []

    # Highest score first; stable tiebreak on title so output is deterministic.
    ordered = sorted(
        (c for c in candidates if isinstance(c, dict)),
        key=lambda c: (-float(c.get("score", 0) or 0), str(c.get("title", ""))),
    )
    for c in ordered:
        title = str(c.get("title", "")).strip()
        body = str(c.get("body", "")).strip()
        if not title or not body:
            continue  # malformed candidate — needs both a title and a spec body
        if _is_duplicate(title, seen_titles):
            continue  # duplicates an existing issue OR an already-kept candidate
        kept.append({"title": title, "area": str(c.get("area", "")), "body": body})
        seen_titles.append(title)
        if len(kept) >= max_issues:
            break
    return kept


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, help="Path to candidates JSON (a list).")
    parser.add_argument("--existing", default="", help="Path to existing-recs JSON (a list); optional.")
    parser.add_argument("--max", type=int, default=5, help="Max issues to keep.")
    args = parser.parse_args(argv)

    def _load(path: str) -> list:
        if not path:
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    world = {
        "max_issues": args.max,
        "candidates": _load(args.candidates),
        "existing": _load(args.existing),
    }
    json.dump(select(world), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_improvement_recommend_select.py -v`
Expected: PASS — all 10 tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/improvement_recommend_select.py backend/tests/test_improvement_recommend_select.py
git commit -m "feat: selection core for improvement recommender

Pure dedup+rank+cap over agent-generated candidates; mirrors
orphan_issue_sweep. Unit-tested boundaries: score ordering, MAX_ISSUES
cap, duplicate suppression (vs existing issues and among candidates),
malformed/garbage-input safety.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Daily recommender workflow

**Files:**
- Create: `.github/workflows/claude-improvement-recommender.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/claude-improvement-recommender.yml`:

```yaml
name: claude-improvement-recommender

# Daily proactive-improvement loop. Three specialist agents
# (autotiers-researcher/designer/engineer) examine the app AND newly-available
# external inputs — fantasy-football rankings we can benchmark our tiers
# against, new tech/deps, UX best practices — and the highest-value
# recommendations are filed as `recommendation` issues. Those issues feed
# claude-implement-issue.yml (the user's chosen FULL autonomous loop), so a
# recommendation can become a merged PR unsupervised.
#
# Ships DRY_RUN: "true" — the run produces recommendations.json and logs the
# plan but files NOTHING, so the quality of recommendations can be judged for a
# few days before arming. Arm by flipping DRY_RUN to "false"; ramp MAX_ISSUES
# from 1 upward.
#
# TOKEN SPLIT (correctness-critical): issue CREATION uses PR_AUTHOR_PAT, NOT the
# built-in GITHUB_TOKEN. A GITHUB_TOKEN-created issue does not trigger any
# workflow (GitHub's recursion guard), and an App/bot-authored issue resolves to
# author_association NONE, which claude-implement-issue.yml refuses. Only a real
# user credential (the PAT) both fires `issues: opened` AND passes that
# trusted-author gate. (Same rule as the orphan sweeper's re-dispatch.)
#
# Design: docs/superpowers/specs/2026-07-02-improvement-recommender-design.md

on:
  schedule:
    # Daily 08:10 UTC. Minute 10 is free of every existing scheduled workflow
    # (copilot-review=0, sweeper-health=17, fix-checks=30, orphan-sweeper=40,
    # resolve-conflicts=45, auto-merge=50) — a cron fires AT its minute field, so
    # the minute is what must be unique.
    - cron: "10 8 * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Override DRY_RUN for a single manual run (true/false)."
        required: false
        type: string

concurrency:
  # Never let two ticks file overlapping issues.
  group: claude-improvement-recommender
  cancel-in-progress: false

permissions:
  contents: read # actions/checkout
  issues: write # dedup reads + label bootstrap (creation itself uses the PAT)
  pull-requests: read
  id-token: write # claude-code-action mints its GitHub token via OIDC

env:
  # Ship SAFE: produce recommendations, file nothing, until a human has watched
  # a few days of output. Flip to "false" (start with MAX_ISSUES=1) to arm.
  DRY_RUN: "true"
  MAX_ISSUES: "5"
  REC_LABEL: "recommendation"
  LOOKBACK_DAYS: "30"

jobs:
  recommend:
    name: generate and file improvement recommendations
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
        with:
          # PAT so any git ops use a real-user credential; issue creation below
          # re-asserts it explicitly via gh.
          token: ${{ secrets.PR_AUTHOR_PAT }}
          fetch-depth: 0

      # Pre-provision the toolchain so the engineer/designer subagents can run
      # tests and inspect the live app, mirroring claude-implement-issue.yml.
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: backend/pyproject.toml
      - name: Install backend deps
        working-directory: backend
        run: pip install -e ".[dev]"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install web deps
        working-directory: web
        run: npm ci

      # Gather recommendations already tracked (open, or closed within
      # LOOKBACK_DAYS) so the agent does not re-propose a standing idea. Pure
      # read on the built-in token.
      - name: Gather existing recommendations
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          since="$(date -u -d "-${LOOKBACK_DAYS} days" +%Y-%m-%dT%H:%M:%SZ)"
          gh issue list --repo "$REPO" --label "$REC_LABEL" --state open \
            --limit 200 --json number,title,state > open_recs.json
          gh issue list --repo "$REPO" --label "$REC_LABEL" --state closed \
            --search "closed:>=$since" --limit 200 \
            --json number,title,state > closed_recs.json
          jq -s 'add' open_recs.json closed_recs.json > existing_recs.json
          echo "::group::existing_recs.json"; cat existing_recs.json; echo "::endgroup::"

      - name: Generate candidate recommendations
        uses: anthropics/claude-code-action@v1
        with:
          # Subscription auth (Pro/Max), same as claude-implement-issue.yml.
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          prompt: |
            You are the AutoTiers improvement recommender. Produce candidate
            improvement recommendations for THIS repository and write them to
            `candidates.json` at the repo root. You do NOT create GitHub issues —
            a later deterministic step selects and files them.

            Dispatch these three specialists via the Task tool, each in its lane;
            run them and collect their findings:
              - autotiers-researcher: compare our tier/ranking output against
                newly-available public fantasy-football rankings / ADP
                (FantasyPros, ESPN, etc.) and flag divergences worth acting on;
                ALSO surface new libraries, tooling, or techniques relevant to
                our stack. Use WebSearch / WebFetch.
              - autotiers-designer: audit the existing link -> generate -> export
                flow against current UX best practices and new patterns.
              - autotiers-engineer: audit app internals (backend/app, web/src)
                for correctness, performance, and maintainability improvements.

            `existing_recs.json` at the repo root lists recommendations already
            tracked as issues — do NOT re-propose anything substantially covered
            there.

            Write `candidates.json`: a JSON array where each element is
              {
                "title": "<one concise line>",
                "area": "rankings" | "tech" | "ux" | "internals",
                "body": "<issue body: an auto-implement-ready spec with sections
                         Problem, Proposed change, Acceptance criteria,
                         Affected files>",
                "score": <number; your value/effort estimate, higher = ship first>
              }
            Emit as many strong candidates as you find (the next step dedups,
            ranks by score, and keeps only the best few). Each body must be
            precise enough for another agent to implement with no further human
            input. The repo's `.claude/skills/` and `.claude/agents/` are present
            in the checkout — use them.
          claude_args: |
            --model claude-opus-4-8
            --max-turns 120
            --allowedTools Edit,Write,Read,Glob,Grep,Bash,Task,WebSearch,WebFetch

      # Deterministic selection: dedup vs existing issues + already-kept
      # candidates, order by score, cap to MAX_ISSUES. A missing or garbage
      # candidates.json yields [] and never fails the schedule.
      - name: Select recommendations to file
        run: |
          set -euo pipefail
          [ -f candidates.json ] || echo "[]" > candidates.json
          python3 backend/scripts/improvement_recommend_select.py \
            --candidates candidates.json \
            --existing existing_recs.json \
            --max "$MAX_ISSUES" > recommendations.json
          echo "::group::recommendations.json"; cat recommendations.json; echo "::endgroup::"

      # File each selected recommendation as an issue, AUTHENTICATED as
      # PR_AUTHOR_PAT so claude-implement-issue fires and its trusted-author gate
      # passes. DRY_RUN files nothing.
      - name: File recommendation issues
        env:
          GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}
          REPO: ${{ github.repository }}
          DRY_RUN_OVERRIDE: ${{ github.event.inputs.dry_run }}
        run: |
          set -euo pipefail
          dry_run="${DRY_RUN_OVERRIDE:-$DRY_RUN}"
          echo "DRY_RUN=$dry_run"
          count="$(jq 'length' recommendations.json)"
          echo "selected $count recommendation(s)"
          [ "$count" -gt 0 ] || { echo "nothing to file."; exit 0; }

          if [ "$dry_run" != "true" ]; then
            gh label create "$REC_LABEL" --repo "$REPO" \
              --color 0e8a16 --description "Proactive improvement recommendation (auto-filed)" \
              2>/dev/null || true
          fi

          jq -c '.[]' recommendations.json | while read -r row; do
            title="$(echo "$row" | jq -r .title)"
            body="$(echo "$row" | jq -r .body)"
            area="$(echo "$row" | jq -r .area)"
            echo "recommendation [$area]: $title"
            if [ "$dry_run" = "true" ]; then
              echo "(dry-run) would file issue."
              continue
            fi
            printf '%s\n\n_Filed by `claude-improvement-recommender.yml` (area: %s)._' \
              "$body" "$area" \
              | gh issue create --repo "$REPO" --label "$REC_LABEL" \
                  --title "$title" --body-file -
          done
```

- [ ] **Step 2: Verify the workflow YAML parses**

Run: `cd backend && venv/bin/python -c "import yaml,sys; yaml.safe_load(open('../.github/workflows/claude-improvement-recommender.yml')); print('yaml ok')"`
Expected: `yaml ok`

If `actionlint` is installed, also run: `actionlint .github/workflows/claude-improvement-recommender.yml`
Expected: no output (clean). If not installed, skip — the YAML parse above is the required gate.

- [ ] **Step 3: Re-run the full decision-core test to confirm nothing regressed**

Run: `cd backend && venv/bin/pytest tests/test_improvement_recommend_select.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/claude-improvement-recommender.yml
git commit -m "feat(ci): daily improvement-recommender workflow (dry-run default)

Three specialists examine the app + external inputs daily; top-5
recommendations are filed as \`recommendation\` issues via PR_AUTHOR_PAT so
they feed the claude-implement-issue autonomous loop. Ships DRY_RUN.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Manual verification (post-merge, not automatable here)

1. **Secrets exist:** confirm `PR_AUTHOR_PAT` (Contents+Issues+workflow scope) and `CLAUDE_CODE_OAUTH_TOKEN` are set on the repo — both are reused from `claude-implement-issue.yml`, so no new secret is needed.
2. **Dry-run smoke:** Actions → `claude-improvement-recommender` → Run workflow with `dry_run=true`. Confirm `recommendations.json` in the log is well-formed and **no** issue was created.
3. **Arming smoke (deliberate):** Run once with `dry_run=false` after temporarily setting `MAX_ISSUES=1`; confirm exactly one `recommendation`-labelled issue is filed by the PAT identity and that `claude-implement-issue` fires on it. Then flip `DRY_RUN` in the file to `"false"` when ready to arm for real.

---

## Out of scope (deferred, per spec)

- A `claude-sweeper-health.yml` job that alarms when this daily run silently fails — add after the loop is armed and trusted.
- Hybrid confidence-based coupling — the user chose the full loop.
```
