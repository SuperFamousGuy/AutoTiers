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


def test_in_progress_with_attempt_label_skips_without_touching_counter():
    # An issue actively being (re-)implemented is skipped as in_progress, and its
    # attempt counter is left untouched (no dispatch, no clear) so the currently
    # running attempt is not miscounted or double-dispatched.
    plan = plan_sweep(
        _world(_issue(23, in_progress=True, labels=["implement-attempt-1"]))
    )
    assert plan["dispatch"] == []
    assert plan["clear"] == []
    assert {"number": 23, "reason": "in_progress"} in plan["skip"]


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
