"""Structural guard for the claude-sweeper-health watcher workflow.

Issue #377: the auto-merge sweeper (`claude-auto-merge.yml`, PR #376) was the one
member of the `claude-*` sweeper family NOT yet health-watched. This adds an
`auto-merge-health` job so its scheduled runs are monitored for silent failure
the same way the copilot-review and fix-checks sweepers already are.

These tests pin the structural invariants of that wiring so a future edit cannot
silently drop the auto-merge sweeper from the watcher, or misconfigure its grace
window, label, or mode. They assert against the raw workflow text (no YAML
parser) so the suite needs no extra dependency — same approach as
`test_address_copilot_review_workflow.py` and `test_implement_issue_workflow.py`.

The boundary MATH of the verdict (when 720 min trips stale/broken/healthy) is
unit-tested separately in `test_sweeper_health.py`; this file only checks that
the workflow feeds the right inputs to that math for the auto-merge sweeper.
"""

import re
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "claude-sweeper-health.yml"
)

TEXT = WORKFLOW.read_text()


def _auto_merge_job_block() -> str:
    """The text of the auto-merge-health job: from its key up to the next
    top-level job key (or EOF). Bounding the slice to the next job key — rather
    than to end of file — stops assertions from being satisfied by an identical
    string in another job AND keeps them correct if a job is ever added after
    auto-merge-health (it is currently last)."""
    key = "  auto-merge-health:"
    start = TEXT.index(key)
    rest = TEXT[start + len(key) :]
    # Next top-level job key: a line indented exactly two spaces (job keys live
    # under `jobs:`), an identifier, then a colon.
    nxt = re.search(r"^  [A-Za-z0-9_-]+:", rest, re.MULTILINE)
    end = start + len(key) + nxt.start() if nxt else len(TEXT)
    return TEXT[start:end]


def test_auto_merge_health_job_exists():
    """The watcher must declare a dedicated job for the auto-merge sweeper."""
    assert "  auto-merge-health:" in TEXT
    assert "name: check auto-merge sweeper freshness" in TEXT


def test_auto_merge_workflow_is_monitored():
    """The auto-merge sweeper's workflow file is in the monitored set."""
    assert "AUTO_MERGE_WORKFLOW: claude-auto-merge.yml" in TEXT
    # And the job actually queries THAT workflow's run history.
    assert "--workflow \"$AUTO_MERGE_WORKFLOW\"" in _auto_merge_job_block()


def test_auto_merge_uses_scan_mode():
    """A run that keeps ticking but FAILS every time must surface as 'broken',
    not slip through as healthy — so the job runs sweeper_health.py in --mode
    scan (staleness + run-success), exactly like the fix-checks job."""
    block = _auto_merge_job_block()
    assert "--mode scan" in block
    assert "--last-success \"$last_success\"" in block


def test_auto_merge_grace_window_is_720_min():
    """180-min cadence with 3 allowed missed ticks => 180*(3+1) = 720 min (12h).
    The cadence value must match the sweeper's `50 */3 * * *` schedule so the
    window is anchored to the real cron, not an arbitrary number."""
    assert "AUTO_MERGE_INTERVAL_MINUTES: \"180\"" in TEXT
    assert "AUTO_MERGE_MAX_MISSED_TICKS: \"3\"" in TEXT


def test_auto_merge_last_success_is_run_level_conclusion():
    """The auto-merge sweeper is a SINGLE job, so the run-level conclusion IS the
    health signal — last_success is the newest run that concluded `success`, with
    NO per-job `gh run view` lookup (that lookup exists in the fix-checks job only
    because its run can fail on a per-PR job while its scan succeeded)."""
    block = _auto_merge_job_block()
    assert "select(.status == \"completed\" and .conclusion == \"success\")" in block
    # The per-job inspection used by fix-checks must NOT appear in this job.
    assert "gh run view" not in block


def test_auto_merge_alarms_on_both_stale_and_broken():
    """Acceptance criterion: a failed OR missing run is surfaced. Both verdicts
    open/comment the alarm issue."""
    block = _auto_merge_job_block()
    assert "[ \"$status\" = \"stale\" ] || [ \"$status\" = \"broken\" ]" in block


def test_auto_merge_label_is_distinct():
    """A distinct dedup label so an auto-merge alarm never collides with the
    copilot-review or fix-checks alarm issues (or vice versa)."""
    assert "AUTO_MERGE_STALE_LABEL: auto-merge-sweeper-stale" in TEXT
    # All three sweepers' label assignments are present and distinct, so no two
    # alarms dedup against the same issue.
    assert "STALE_LABEL: sweeper-stale" in TEXT  # copilot
    assert "FIX_CHECKS_STALE_LABEL: fix-checks-sweeper-stale" in TEXT  # fix-checks
    # Pull the ACTUAL label values out of the workflow (every `*STALE_LABEL:`
    # env assignment) and assert they are genuinely distinct. A hard-coded set
    # would pass even if two sweepers accidentally shared a label value; this
    # reads what the workflow really declares.
    values = re.findall(r"STALE_LABEL: (\S+)", TEXT)
    assert len(values) == 3, f"expected 3 STALE_LABEL definitions, got {values}"
    assert len(set(values)) == 3, f"label values not distinct: {values}"


def test_auto_merge_no_runs_is_not_an_alarm():
    """Before claude-auto-merge.yml is live on the default branch it has no run
    history; the watcher must stay quiet (no_runs), not false-alarm. The shell
    routes the no_runs verdict to the do-nothing branch."""
    block = _auto_merge_job_block()
    assert "No auto-merge sweeper run history yet; not alarming." in block


def test_auto_merge_gh_failure_is_loud():
    """A failed run-history query must fail the step loudly rather than be
    swallowed into an empty last_run that masquerades as a benign no_runs."""
    block = _auto_merge_job_block()
    assert "::error::Failed to query run history for $AUTO_MERGE_WORKFLOW" in block
    assert "exit 1" in block
