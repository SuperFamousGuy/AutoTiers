"""Tests for the triage-dispatch decision core.

The improvement recommender files backlog issues labelled `triage-queued`,
each carrying a `<!-- autotiers:rec score=N -->` marker in its body. This
module's `plan_dispatch` is the pure decision that meters those issues into
`claude-implement-issue.yml`, best-score-first, capped by open-PR
backpressure (`cap - inflight`). These tests lock the boundaries an `if`-chain
in shell gets wrong: negative slot math, malformed score markers, tie-breaks,
and issues that lost their queued label.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from scripts.triage_dispatch import main, parse_score, plan_dispatch


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
    assert [d["number"] for d in plan["dispatch"]] == [11, 12]


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
        "issues": [_issue(10, 9, label="recommendation")],
    }
    assert plan_dispatch(world)["dispatch"] == []


def test_dispatch_missing_marker_sorts_last():
    world = {
        "cap": 1,
        "inflight": 0,
        "queued_label": "triage-queued",
        "issues": [_issue(10, None), _issue(11, 1)],
    }
    assert [d["number"] for d in plan_dispatch(world)["dispatch"]] == [11]


def test_dispatch_empty_backlog():
    world = {"cap": 2, "inflight": 0, "queued_label": "triage-queued", "issues": []}
    assert plan_dispatch(world) == {"dispatch": [], "slots": 2}


def test_main_reads_stdin_and_emits_plan(monkeypatch):
    world = {
        "cap": 2,
        "inflight": 0,
        "queued_label": "triage-queued",
        "issues": [_issue(11, 9)],
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(world)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--world", "-"])
    assert rc == 0
    plan = json.loads(buf.getvalue())
    assert plan == {"dispatch": [{"number": 11, "score": 9.0}], "slots": 2}
