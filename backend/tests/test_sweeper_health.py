"""Tests for the copilot-review cron sweeper staleness alarm.

Issue #348: the sweeper (`claude-address-copilot-review.yml`) can silently
stop firing (cron drift, repeated skipped ticks, or the 60-day inactivity
auto-disable). `scripts/sweeper_health.py` holds the pure decision of whether
the sweeper has gone stale; these tests lock in the boundary conditions that
the shell wrapper relies on and that off-by-one math tends to get wrong.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from scripts.sweeper_health import (
    ScanSweeperVerdict,
    StalenessVerdict,
    evaluate_scan_sweeper_health,
    evaluate_staleness,
    main,
)

NOW = "2026-06-18T13:00:00Z"


def _at(minutes_ago: float) -> str:
    """ISO timestamp `minutes_ago` minutes before NOW."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 6, 18, 13, 0, 0, tzinfo=timezone.utc)
    return (base - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def test_recent_run_is_healthy():
    v = evaluate_staleness(last_run=_at(5), now=NOW)
    assert isinstance(v, StalenessVerdict)
    assert v.status == "healthy"
    assert v.stale is False
    assert v.minutes_since_last_run == pytest.approx(5.0)


def test_no_run_history_is_not_an_alarm():
    """Before the sweeper is live there is no run history; that must not alarm."""
    for empty in (None, "", "   "):
        v = evaluate_staleness(last_run=empty, now=NOW)
        assert v.status == "no_runs"
        assert v.stale is False
        assert v.minutes_since_last_run is None
        assert v.missed_ticks is None


def test_clearly_stale_run_alarms():
    # 3 hours ago at a 10-min cadence is far past any reasonable grace window.
    v = evaluate_staleness(last_run=_at(180), now=NOW)
    assert v.status == "stale"
    assert v.stale is True
    assert v.missed_ticks == 17  # (180 - 10) // 10
    assert "auto-disabled" in v.detail


def test_boundary_just_inside_allowed_gap_is_healthy():
    # Default: interval=10, max_missed_ticks=6 => allowed gap = 10*(6+1) = 70 min.
    v = evaluate_staleness(last_run=_at(70), now=NOW)
    assert v.stale is False
    assert v.status == "healthy"


def test_boundary_just_past_allowed_gap_is_stale():
    v = evaluate_staleness(last_run=_at(70.5), now=NOW)
    assert v.stale is True
    assert v.status == "stale"


def test_normal_cron_drift_within_one_interval_is_not_missed():
    # A run 12 min ago (2 min of drift on a 10-min cadence) is 0 missed ticks.
    v = evaluate_staleness(last_run=_at(12), now=NOW)
    assert v.missed_ticks == 0
    assert v.stale is False


def test_missed_ticks_arithmetic():
    # 45 min gap: (45 - 10) // 10 = 3 missed ticks, still within 6-tick grace.
    v = evaluate_staleness(last_run=_at(45), now=NOW)
    assert v.missed_ticks == 3
    assert v.stale is False


def test_z_suffix_and_offset_timestamps_are_equivalent():
    z = evaluate_staleness(last_run="2026-06-18T12:00:00Z", now=NOW)
    offset = evaluate_staleness(last_run="2026-06-18T12:00:00+00:00", now=NOW)
    assert z.minutes_since_last_run == offset.minutes_since_last_run == 60.0


def test_naive_timestamp_assumed_utc():
    v = evaluate_staleness(last_run="2026-06-18T12:30:00", now=NOW)
    assert v.minutes_since_last_run == pytest.approx(30.0)


def test_non_utc_offset_is_normalized():
    # 12:00 at +02:00 == 10:00Z == 180 min before 13:00Z.
    v = evaluate_staleness(last_run="2026-06-18T12:00:00+02:00", now=NOW)
    assert v.minutes_since_last_run == pytest.approx(180.0)
    assert v.stale is True


def test_custom_threshold_tightens_window():
    # With max_missed_ticks=1 the allowed gap is 10*2 = 20 min.
    v = evaluate_staleness(
        last_run=_at(25), now=NOW, interval_minutes=10, max_missed_ticks=1
    )
    assert v.stale is True
    assert v.max_missed_ticks == 1


def test_future_last_run_raises():
    with pytest.raises(ValueError):
        evaluate_staleness(last_run=_at(-5), now=NOW)


def test_non_positive_interval_raises():
    with pytest.raises(ValueError):
        evaluate_staleness(last_run=_at(5), now=NOW, interval_minutes=0)


def test_negative_max_missed_ticks_raises():
    with pytest.raises(ValueError):
        evaluate_staleness(last_run=_at(5), now=NOW, max_missed_ticks=-1)


def test_main_emits_json_and_exits_zero():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--last-run", _at(200), "--now", NOW])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["stale"] is True
    assert payload["status"] == "stale"


def test_main_no_runs_path():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--now", NOW])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["status"] == "no_runs"
    assert payload["stale"] is False


def test_main_respects_custom_flags():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(
            [
                "--last-run",
                _at(25),
                "--now",
                NOW,
                "--interval-minutes",
                "10",
                "--max-missed-ticks",
                "1",
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["stale"] is True


# --------------------------------------------------------------------------- #
# Fix-checks sweeper (issue #373): scan-based health.                         #
# The fix-checks sweeper's grace window mirrors the copilot one: an hourly    #
# configured cadence with max_missed_ticks=3 => allowed gap 60*(3+1)=240      #
# min. These tests use the same defaults (interval=10, max=6 => gap=70) the   #
# pure function ships with, except where they assert the production window.   #
# --------------------------------------------------------------------------- #


def test_scan_recent_run_and_success_is_healthy():
    v = evaluate_scan_sweeper_health(last_run=_at(5), last_success=_at(5), now=NOW)
    assert isinstance(v, ScanSweeperVerdict)
    assert v.status == "healthy"
    assert v.stale is False
    assert v.broken is False
    assert v.minutes_since_last_run == pytest.approx(5.0)
    assert v.minutes_since_last_success == pytest.approx(5.0)


def test_scan_idle_healthy_success_slightly_older_than_run():
    # An idle tick still produces a successful scan. Even if the most recent
    # tick is mid-flight (last_run a touch fresher than last_success), a
    # success well within the window is healthy.
    v = evaluate_scan_sweeper_health(last_run=_at(2), last_success=_at(12), now=NOW)
    assert v.status == "healthy"
    assert v.broken is False


def test_scan_no_run_history_is_not_an_alarm():
    for empty in (None, "", "   "):
        v = evaluate_scan_sweeper_health(last_run=empty, last_success=empty, now=NOW)
        assert v.status == "no_runs"
        assert v.stale is False
        assert v.broken is False
        assert v.minutes_since_last_run is None
        assert v.minutes_since_last_success is None


def test_scan_ticking_but_never_succeeded_is_broken():
    # Sweeper is firing (fresh run) but no scan has ever succeeded => broken,
    # NOT stale: the scan logic itself is failing.
    v = evaluate_scan_sweeper_health(last_run=_at(3), last_success=None, now=NOW)
    assert v.status == "broken"
    assert v.broken is True
    assert v.stale is False
    assert v.minutes_since_last_success is None
    assert "never succeeded" in v.detail


def test_scan_ticking_but_success_is_stale_is_broken():
    # Fresh runs, but the last successful scan is well past the window: the
    # scan has been failing for a while. Broken, not idle-healthy.
    v = evaluate_scan_sweeper_health(last_run=_at(3), last_success=_at(200), now=NOW)
    assert v.status == "broken"
    assert v.broken is True
    assert v.stale is False
    assert "scan job is failing" in v.detail


def test_scan_not_ticking_is_stale_even_if_scan_once_succeeded():
    # The whole sweeper stopped firing: last run is far older than the window.
    # That is "stale" (cron drift / auto-disable), which takes precedence over
    # the broken/healthy scan distinction.
    v = evaluate_scan_sweeper_health(last_run=_at(180), last_success=_at(180), now=NOW)
    assert v.status == "stale"
    assert v.stale is True
    assert v.broken is False
    assert "auto-disabled" in v.detail


def test_scan_boundary_just_inside_window_is_healthy():
    # Default interval=10, max=6 => allowed gap 70 min.
    v = evaluate_scan_sweeper_health(last_run=_at(70), last_success=_at(70), now=NOW)
    assert v.status == "healthy"


def test_scan_boundary_success_just_past_window_is_broken():
    # Run is fresh, but the last success is just past the 70-min gap.
    v = evaluate_scan_sweeper_health(last_run=_at(5), last_success=_at(70.5), now=NOW)
    assert v.status == "broken"
    assert v.broken is True


def test_scan_production_window_240_min():
    # The values wired into the workflow: hourly cadence, 3 missed ticks.
    common = dict(now=NOW, interval_minutes=60, max_missed_ticks=3)
    healthy = evaluate_scan_sweeper_health(
        last_run=_at(239), last_success=_at(239), **common
    )
    assert healthy.status == "healthy"
    assert healthy.allowed_gap_minutes == 240
    broken = evaluate_scan_sweeper_health(
        last_run=_at(5), last_success=_at(241), **common
    )
    assert broken.status == "broken"
    stale = evaluate_scan_sweeper_health(
        last_run=_at(241), last_success=_at(241), **common
    )
    assert stale.status == "stale"


def test_scan_future_last_run_raises():
    with pytest.raises(ValueError):
        evaluate_scan_sweeper_health(last_run=_at(-5), last_success=None, now=NOW)


def test_scan_future_last_success_raises():
    with pytest.raises(ValueError):
        evaluate_scan_sweeper_health(last_run=_at(5), last_success=_at(-5), now=NOW)


def test_scan_non_positive_interval_raises():
    with pytest.raises(ValueError):
        evaluate_scan_sweeper_health(
            last_run=_at(5), last_success=_at(5), now=NOW, interval_minutes=0
        )


def test_scan_negative_max_missed_ticks_raises():
    with pytest.raises(ValueError):
        evaluate_scan_sweeper_health(
            last_run=_at(5), last_success=_at(5), now=NOW, max_missed_ticks=-1
        )


def test_main_scan_mode_healthy():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(
            [
                "--mode",
                "scan",
                "--last-run",
                _at(5),
                "--last-success",
                _at(5),
                "--now",
                NOW,
            ]
        )
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["status"] == "healthy"
    assert payload["broken"] is False


def test_main_scan_mode_broken_when_no_success():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--mode", "scan", "--last-run", _at(5), "--now", NOW])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["status"] == "broken"
    assert payload["broken"] is True


def test_main_scan_mode_no_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--mode", "scan", "--now", NOW])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["status"] == "no_runs"
