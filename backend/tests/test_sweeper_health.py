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
    StalenessVerdict,
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


def test_main_emits_json_and_exits_zero(capsys=None):
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
