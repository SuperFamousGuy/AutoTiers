"""Staleness/health evaluation for the Claude cron sweepers.

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

Issue #373 extends the same alarm to the `claude-fix-pr-checks.yml` sweeper
(added by PR #372). That sweeper has a richer health signal: every tick runs
a cheap `scan` job, and its *healthy idle* state is a SUCCESSFUL scan that
found no eligible PRs (`any=false`). So for the fix-checks sweeper a fresh
run is not enough — the alarm must distinguish:

  * **idle but healthy** — the scan job is still completing successfully
    (whether or not it found work), versus
  * **broken** — the sweeper is still ticking, but its scan job has stopped
    succeeding within the allowed window (the scan logic itself is failing).

`evaluate_staleness` holds the copilot sweeper's decision (last run vs. now).
`evaluate_scan_sweeper_health` holds the fix-checks decision, layering the
"is the scan still succeeding?" check on top of the same staleness math. Both
are *pure and testable*: the workflow (`claude-sweeper-health.yml`) is a thin
shell wrapper that fetches the timestamps via `gh` and feeds them here;
keeping the arithmetic in Python lets us unit-test the boundary conditions
that shell math gets wrong.

The alarm deliberately lives in a SEPARATE workflow from the sweepers: a
check embedded in a sweeper could not fire when the sweeper itself is
disabled, which is precisely the case we most need to catch.

Run standalone (used by the workflow):

    # copilot sweeper (staleness only)
    python3 backend/scripts/sweeper_health.py \
        --last-run "2026-06-18T11:50:00Z" \
        --now "2026-06-18T13:05:00Z" \
        --interval-minutes 10 \
        --max-missed-ticks 6

    # fix-checks sweeper (staleness + scan-success)
    python3 backend/scripts/sweeper_health.py \
        --mode scan \
        --last-run "2026-06-18T12:58:00Z" \
        --last-success "2026-06-18T12:58:00Z" \
        --now "2026-06-18T13:05:00Z" \
        --interval-minutes 10 \
        --max-missed-ticks 23

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


@dataclass(frozen=True)
class ScanSweeperVerdict:
    """Structured result of a scan-sweeper (fix-checks) health evaluation.

    Unlike the copilot sweeper, the fix-checks sweeper exposes two timestamps:
    ``last_run`` (its most recent tick, any conclusion) tells us whether it is
    still firing at all; ``last_success`` (the most recent run whose scan job
    succeeded) tells us whether the scan logic is still working. The ``status``
    folds them into one of four outcomes — see ``evaluate_scan_sweeper_health``.
    """

    status: str  # "healthy" | "stale" | "broken" | "no_runs"
    stale: bool  # not ticking at all (cron drift / auto-disable)
    broken: bool  # ticking, but the scan job is not succeeding
    minutes_since_last_run: Optional[float]
    minutes_since_last_success: Optional[float]
    missed_ticks: Optional[int]
    interval_minutes: int
    max_missed_ticks: int
    allowed_gap_minutes: int
    last_run: Optional[str]
    last_success: Optional[str]
    now: str
    detail: str


def evaluate_scan_sweeper_health(
    last_run: Optional[str],
    last_success: Optional[str],
    now: str,
    interval_minutes: int = 10,
    max_missed_ticks: int = 6,
) -> ScanSweeperVerdict:
    """Decide the health of a scan-based sweeper (`claude-fix-pr-checks.yml`).

    The fix-checks sweeper (issue #373 / PR #372) runs a cheap ``scan`` job
    every tick. Its *healthy idle* path is a SUCCESSFUL scan that found no
    eligible PRs (``any=false``) — so a fresh run alone does not prove health;
    the scan must also be *succeeding*. This layers that distinction on top of
    the staleness math in ``evaluate_staleness``:

      * ``no_runs`` — the sweeper has never run (not live on the default branch
        yet). Not an alarm, mirroring ``evaluate_staleness``.
      * ``stale`` — the most recent run (any conclusion) is older than the
        allowed gap. The sweeper has stopped ticking entirely: cron drift,
        repeated skipped ticks, or the 60-day auto-disable. Same failure mode
        the copilot sweeper alarms on.
      * ``broken`` — the sweeper is still ticking (a recent run exists) but its
        scan job has not *succeeded* within the allowed gap (or has never
        succeeded). The scan logic itself is failing; idle-but-healthy is ruled
        out because an idle tick still produces a successful scan.
      * ``healthy`` — a recent run exists AND the scan job succeeded within the
        allowed gap. Covers both "did work" and "idle, nothing to do".

    Args:
        last_run: ISO-8601 timestamp of the sweeper's most recent run of any
            conclusion, or None/empty when it has never run.
        last_success: ISO-8601 timestamp of the most recent run whose scan job
            succeeded, or None/empty when no scan has ever succeeded.
        now: ISO-8601 timestamp for the current time.
        interval_minutes: The sweeper's cron cadence in minutes.
        max_missed_ticks: Allowed consecutive missed ticks before alarming.
            The allowed gap is ``interval_minutes * (max_missed_ticks + 1)``,
            identical to ``evaluate_staleness`` so the two sweepers share one
            grace-window definition.

    Returns:
        A ScanSweeperVerdict.

    Raises:
        ValueError: if interval_minutes is non-positive, if max_missed_ticks is
            negative, or if either timestamp is in the future relative to now.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if max_missed_ticks < 0:
        raise ValueError("max_missed_ticks must be >= 0")

    now_dt = _parse_iso(now)
    allowed_gap = interval_minutes * (max_missed_ticks + 1)

    if last_run is None or str(last_run).strip() == "":
        return ScanSweeperVerdict(
            status="no_runs",
            stale=False,
            broken=False,
            minutes_since_last_run=None,
            minutes_since_last_success=None,
            missed_ticks=None,
            interval_minutes=interval_minutes,
            max_missed_ticks=max_missed_ticks,
            allowed_gap_minutes=allowed_gap,
            last_run=None,
            last_success=None,
            now=now_dt.isoformat(),
            detail=(
                "Fix-checks sweeper has no run history yet; nothing to alarm "
                "on. This is expected before the sweeper workflow is live on "
                "the default branch."
            ),
        )

    last_run_dt = _parse_iso(last_run)
    minutes_since_run = (now_dt - last_run_dt).total_seconds() / 60.0
    if minutes_since_run < 0:
        raise ValueError(
            f"last_run ({last_run_dt.isoformat()}) is after now "
            f"({now_dt.isoformat()})"
        )
    missed_ticks = max(
        0, int((minutes_since_run - interval_minutes) // interval_minutes)
    )

    has_success = last_success is not None and str(last_success).strip() != ""
    if has_success:
        last_success_dt = _parse_iso(last_success)
        minutes_since_success: Optional[float] = (
            now_dt - last_success_dt
        ).total_seconds() / 60.0
        if minutes_since_success < 0:
            raise ValueError(
                f"last_success ({last_success_dt.isoformat()}) is after now "
                f"({now_dt.isoformat()})"
            )
        last_success_iso: Optional[str] = last_success_dt.isoformat()
    else:
        minutes_since_success = None
        last_success_iso = None

    not_ticking = minutes_since_run > allowed_gap
    # Scan is failing if it has never succeeded, or its last success is older
    # than the allowed gap while the sweeper itself is still ticking.
    scan_failing = (minutes_since_success is None) or (
        minutes_since_success > allowed_gap
    )

    if not_ticking:
        status = "stale"
        detail = (
            f"Fix-checks sweeper last ran {minutes_since_run:.0f} min ago "
            f"(~{missed_ticks} missed ticks at a {interval_minutes}-min "
            f"cadence). That exceeds the allowed gap of {allowed_gap} min "
            f"({max_missed_ticks} missed ticks). The sweeper may have drifted, "
            f"been skipped repeatedly, or been auto-disabled after 60 days of "
            f"repo inactivity."
        )
    elif scan_failing:
        status = "broken"
        if minutes_since_success is None:
            since = "the scan job has never succeeded"
        else:
            since = (
                f"its last successful scan was {minutes_since_success:.0f} min "
                f"ago"
            )
        detail = (
            f"Fix-checks sweeper is still ticking (last run "
            f"{minutes_since_run:.0f} min ago) but {since}, exceeding the "
            f"allowed gap of {allowed_gap} min. The scan job is failing rather "
            f"than completing — a healthy idle tick still produces a "
            f"successful scan with no eligible PRs."
        )
    else:
        status = "healthy"
        detail = (
            f"Fix-checks sweeper scan succeeded {minutes_since_success:.0f} min "
            f"ago (last run {minutes_since_run:.0f} min ago), within the "
            f"allowed gap of {allowed_gap} min. Healthy."
        )

    return ScanSweeperVerdict(
        status=status,
        stale=not_ticking,
        broken=(status == "broken"),
        minutes_since_last_run=round(minutes_since_run, 2),
        minutes_since_last_success=(
            round(minutes_since_success, 2)
            if minutes_since_success is not None
            else None
        ),
        missed_ticks=missed_ticks,
        interval_minutes=interval_minutes,
        max_missed_ticks=max_missed_ticks,
        allowed_gap_minutes=allowed_gap,
        last_run=last_run_dt.isoformat(),
        last_success=last_success_iso,
        now=now_dt.isoformat(),
        detail=detail,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("staleness", "scan"),
        default="staleness",
        help="Which sweeper to evaluate: 'staleness' (copilot-review, last "
        "run vs now) or 'scan' (fix-pr-checks, also requires a successful "
        "scan within the window). Default: staleness.",
    )
    parser.add_argument(
        "--last-run",
        default="",
        help="ISO-8601 timestamp of the sweeper's most recent run "
        "(empty if it has never run).",
    )
    parser.add_argument(
        "--last-success",
        default="",
        help="ISO-8601 timestamp of the sweeper's most recent SUCCESSFUL scan "
        "run (empty if none). Only used in --mode scan.",
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

    if args.mode == "scan":
        verdict = evaluate_scan_sweeper_health(
            last_run=args.last_run,
            last_success=args.last_success,
            now=args.now,
            interval_minutes=args.interval_minutes,
            max_missed_ticks=args.max_missed_ticks,
        )
    else:
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
