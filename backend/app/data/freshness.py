"""Pure data-freshness staleness decision (issue #401).

The prod scheduler is a single ``desired_count=1`` in-process APScheduler. Twice
now it has silently stopped refreshing data — an OOM crash-loop (2026-06-09 →
2026-06-21) and a ``--reload`` reload-loop (PR #340) — and BOTH outages were
found by a user spotting the stale banner, not by an alarm.

This module holds the *pure* decision of whether the data behind
``/api/data/status`` has gone stale, so it can be unit-tested at the boundary
(the place off-by-one and timezone bugs hide) and exposed via ``/api/data/health``
for an HTTP health check / uptime monitor to alarm on.

The signal: every scheduler cycle calls ``fetcher.refresh_all`` which writes a
fresh ``last_attempted`` for *every* source — even on failure (see
``app.data.status.upsert_status``). So when the scheduler is running, the OLDEST
``last_attempted`` across all sources is recent. If even the oldest attempt is
older than the threshold, no source has been attempted in a full window — the
scheduler is dead or frozen. That mirrors the issue's proposed check
("age of the oldest ``last_attempted`` exceeding a threshold, e.g. > 2h").
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Mapping, Optional


def _parse_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, normalising to aware UTC.

    Accepts a trailing ``Z`` (``fromisoformat`` rejects it before 3.11) and
    treats a naive timestamp as UTC — the scheduler writes ``datetime.utcnow()``
    (naive) into the DB, so the values this sees are UTC wall-clock.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_now(now: Optional[datetime | str]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, str):
        return _parse_ts(now)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


@dataclass(frozen=True)
class FreshnessVerdict:
    """Outcome of a data-freshness check.

    ``stale`` is the single field a monitor should alarm on. ``status`` is the
    human-facing bucket: ``no_data`` (nothing tracked yet — never alarm),
    ``healthy`` (oldest attempt within the window), or ``stale``.
    """

    status: str
    stale: bool
    threshold_seconds: int
    oldest_attempt_age_seconds: Optional[float]
    newest_attempt_age_seconds: Optional[float]
    oldest_source: Optional[str]
    sources_tracked: int
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_data_freshness(
    statuses: Mapping[str, Mapping[str, object]],
    now: Optional[datetime | str] = None,
    threshold_hours: float = 2.0,
) -> FreshnessVerdict:
    """Decide whether the tracked data sources have gone stale.

    Args:
        statuses: the ``{source: {...}}`` mapping returned by
            ``app.data.status.get_all_status`` (each value carries a
            ``last_attempted`` ISO string or ``None``).
        now: reference time (datetime or ISO string). Defaults to current UTC.
            Injectable so tests are deterministic.
        threshold_hours: a source's oldest attempt may be at most this old
            before the data is considered stale. Must be > 0.

    Returns:
        A :class:`FreshnessVerdict`. ``status == "no_data"`` (never an alarm)
        when no source has a recorded attempt — before the first refresh there
        is legitimately nothing to be stale about.
    """
    if threshold_hours <= 0:
        raise ValueError("threshold_hours must be positive")

    ref = _coerce_now(now)
    threshold_seconds = int(round(threshold_hours * 3600))

    # Collect (source, age_seconds) for every source with a usable attempt.
    ages: list[tuple[str, float]] = []
    for source, row in statuses.items():
        raw = row.get("last_attempted") if isinstance(row, Mapping) else None
        if not raw:
            continue
        attempted = _parse_ts(raw) if isinstance(raw, str) else _coerce_now(raw)
        # Clock skew can put a just-written timestamp marginally in the future;
        # clamp to 0 rather than report a negative age (or raise on a live path).
        age = max(0.0, (ref - attempted).total_seconds())
        ages.append((source, age))

    if not ages:
        return FreshnessVerdict(
            status="no_data",
            stale=False,
            threshold_seconds=threshold_seconds,
            oldest_attempt_age_seconds=None,
            newest_attempt_age_seconds=None,
            oldest_source=None,
            sources_tracked=len(statuses),
            detail="No data source has a recorded refresh attempt yet.",
        )

    oldest_source, oldest_age = max(ages, key=lambda pair: pair[1])
    newest_age = min(age for _, age in ages)
    stale = oldest_age > threshold_seconds

    if stale:
        detail = (
            f"Oldest attempt is source '{oldest_source}' at "
            f"{oldest_age / 3600:.1f}h ago, past the {threshold_hours:g}h "
            f"threshold — the scheduler may be down or frozen."
        )
    else:
        detail = (
            f"Oldest attempt ({oldest_source}) is {oldest_age / 3600:.1f}h ago, "
            f"within the {threshold_hours:g}h threshold."
        )

    return FreshnessVerdict(
        status="stale" if stale else "healthy",
        stale=stale,
        threshold_seconds=threshold_seconds,
        oldest_attempt_age_seconds=oldest_age,
        newest_attempt_age_seconds=newest_age,
        oldest_source=oldest_source,
        sources_tracked=len(statuses),
        detail=detail,
    )
