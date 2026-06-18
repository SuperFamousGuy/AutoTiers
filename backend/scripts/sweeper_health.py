"""Staleness/health evaluation for the copilot-review cron sweeper.

Issue #348: GitHub's scheduled (cron) workflows are not a guaranteed
heartbeat. Two failure modes can silently stop the
`claude-address-copilot-review.yml` sweeper (added by PR #344) without any
signal:

  1. **Cron drift / skipped ticks.** GitHub may delay or drop scheduled
     ticks under load. A single skipped tick is harmless (the work signal is
     idempotent), but a *run* of consecutive misses means Copilot reviews are
     piling up unaddressed.
  2. **60-day inactivity auto-disable.** GitHub automatically DISABLES
     scheduled workflows in a repository that has had no commit activity for
     60 days. A disabled sweeper stops firing entirely and emits no error —
     the classic "no staleness alarm" gap (compare the scheduler stale-data
     incident).

This module holds the *pure, testable* decision: given the timestamp of the
sweeper's most recent run and the current time, decide whether it has gone
stale (missed more than an allowed number of ticks). The workflow
(`claude-sweeper-health.yml`) is a thin shell wrapper that fetches the last
run time via `gh` and feeds it here; keeping the arithmetic in Python lets us
unit-test the boundary conditions that shell math gets wrong.

The alarm deliberately lives in a SEPARATE workflow from the sweeper: a check
embedded in the sweeper could not fire when the sweeper itself is disabled,
which is precisely the case we most need to catch.

Run standalone (used by the workflow):

    python3 backend/scripts/sweeper_health.py \
        --last-run "2026-06-18T11:50:00Z" \
        --now "2026-06-18T13:05:00Z" \
        --interval-minutes 10 \
        --max-missed-ticks 6

Exit code is 0 always (the workflow inspects the JSON on stdout and decides
what to do); parse errors exit non-zero so a malformed input is loud rather
than silently "healthy".
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class StalenessVerdict:
    """Structured result of a staleness evaluation."""

    status: str  # "healthy" | "stale" | "no_runs"
    stale: bool
    minutes_since_last_run: Optional[float]
    missed_ticks: Optional[int]
    interval_minutes: int
    max_missed_ticks: int
    last_run: Optional[str]
    now: str
    detail: str


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z' (GitHub's form).

    Always returns a timezone-aware UTC datetime. A naive timestamp is
    assumed to be UTC rather than rejected, so a stray non-suffixed value
    from the API does not crash the alarm.
    """
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_staleness(
    last_run: Optional[str],
    now: str,
    interval_minutes: int = 10,
    max_missed_ticks: int = 6,
) -> StalenessVerdict:
    """Decide whether the sweeper has gone stale.

    Args:
        last_run: ISO-8601 timestamp of the sweeper's most recent run, or
            None/empty when the sweeper has never run. "Never run" is treated
            as a non-alarm condition (status "no_runs"): before PR #344 is
            merged the workflow has no history on the default branch, and we
            do not want a perpetual false alarm. A *disabled* sweeper still
            has past runs, so the "latest run too old" path below catches the
            failure mode we actually care about.
        now: ISO-8601 timestamp for the current time.
        interval_minutes: The sweeper's cron cadence, in minutes (the `*/10`
            in its schedule => 10).
        max_missed_ticks: How many consecutive ticks may be missed before we
            alarm. The allowed gap is
            ``interval_minutes * (max_missed_ticks + 1)`` minutes: one
            interval is the normal spacing between runs, so a gap only counts
            as "missed" beyond that. Default 6 gives a ~70-minute grace
            window over a 10-minute cadence, generous enough to absorb
            ordinary GitHub cron drift without nagging.

    Returns:
        A StalenessVerdict. ``stale`` is True only for status "stale".

    Raises:
        ValueError: if interval_minutes is non-positive, if max_missed_ticks
            is negative, or if last_run is in the future relative to now.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if max_missed_ticks < 0:
        raise ValueError("max_missed_ticks must be >= 0")

    now_dt = _parse_iso(now)

    if last_run is None or str(last_run).strip() == "":
        return StalenessVerdict(
            status="no_runs",
            stale=False,
            minutes_since_last_run=None,
            missed_ticks=None,
            interval_minutes=interval_minutes,
            max_missed_ticks=max_missed_ticks,
            last_run=None,
            now=now_dt.isoformat(),
            detail=(
                "Sweeper has no run history yet; nothing to alarm on. This is "
                "expected before the sweeper workflow is live on the default "
                "branch."
            ),
        )

    last_dt = _parse_iso(last_run)
    minutes_since = (now_dt - last_dt).total_seconds() / 60.0

    if minutes_since < 0:
        raise ValueError(
            f"last_run ({last_dt.isoformat()}) is after now ({now_dt.isoformat()})"
        )

    # One interval is the normal spacing; only the time beyond the first
    # interval counts toward "missed" ticks.
    missed_ticks = max(0, int((minutes_since - interval_minutes) // interval_minutes))
    allowed_gap = interval_minutes * (max_missed_ticks + 1)
    is_stale = minutes_since > allowed_gap

    if is_stale:
        detail = (
            f"Sweeper last ran {minutes_since:.0f} min ago "
            f"(~{missed_ticks} missed ticks at a {interval_minutes}-min cadence). "
            f"That exceeds the allowed gap of {allowed_gap} min "
            f"({max_missed_ticks} missed ticks). The sweeper may have drifted, "
            f"been skipped repeatedly, or been auto-disabled after 60 days of "
            f"repo inactivity."
        )
    else:
        detail = (
            f"Sweeper last ran {minutes_since:.0f} min ago "
            f"(within the allowed gap of {allowed_gap} min). Healthy."
        )

    return StalenessVerdict(
        status="stale" if is_stale else "healthy",
        stale=is_stale,
        minutes_since_last_run=round(minutes_since, 2),
        missed_ticks=missed_ticks,
        interval_minutes=interval_minutes,
        max_missed_ticks=max_missed_ticks,
        last_run=last_dt.isoformat(),
        now=now_dt.isoformat(),
        detail=detail,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--last-run",
        default="",
        help="ISO-8601 timestamp of the sweeper's most recent run "
        "(empty if it has never run).",
    )
    parser.add_argument(
        "--now",
        required=True,
        help="ISO-8601 timestamp for the current time.",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=10,
        help="Sweeper cron cadence in minutes (default: 10).",
    )
    parser.add_argument(
        "--max-missed-ticks",
        type=int,
        default=6,
        help="Allowed consecutive missed ticks before alarming (default: 6).",
    )
    args = parser.parse_args(argv)

    verdict = evaluate_staleness(
        last_run=args.last_run,
        now=args.now,
        interval_minutes=args.interval_minutes,
        max_missed_ticks=args.max_missed_ticks,
    )
    json.dump(asdict(verdict), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
