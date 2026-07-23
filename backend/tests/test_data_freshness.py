"""Tests for the data-freshness staleness alarm (issue #401).

`app/data/freshness.py` holds the pure decision of whether the data behind
`/api/data/status` has gone stale (the scheduler stopped refreshing). These
lock in the boundary conditions — timezone handling and the > vs >= threshold
edge — and the `/api/data/health` endpoint's status-code contract that a
monitor alarms on.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.data.freshness import FreshnessVerdict, evaluate_data_freshness
from app.data.status import RETIRED_SOURCES, upsert_status

NOW = datetime(2026, 6, 22, 13, 0, 0, tzinfo=timezone.utc)


def _status(hours_ago: float, source: str = "sleeper") -> dict:
    """A single-source status mapping whose last_attempted is `hours_ago` old."""
    ts = (NOW - timedelta(hours=hours_ago)).replace(tzinfo=None).isoformat()
    return {source: {"last_attempted": ts, "last_updated": ts, "last_error": None, "rows_upserted": 1}}


# --------------------------------------------------------------------------- #
# Pure decision                                                               #
# --------------------------------------------------------------------------- #
def test_recent_attempt_is_healthy():
    v = evaluate_data_freshness(_status(0.5), now=NOW)
    assert isinstance(v, FreshnessVerdict)
    assert v.status == "healthy"
    assert v.stale is False
    assert v.oldest_source == "sleeper"
    assert v.oldest_attempt_age_seconds == pytest.approx(1800.0)


def test_old_attempt_alarms():
    v = evaluate_data_freshness(_status(12), now=NOW)
    assert v.status == "stale"
    assert v.stale is True
    assert "scheduler may be down" in v.detail


def test_no_sources_is_not_an_alarm():
    """Before the first refresh there is nothing to be stale about."""
    v = evaluate_data_freshness({}, now=NOW)
    assert v.status == "no_data"
    assert v.stale is False
    assert v.oldest_attempt_age_seconds is None
    assert v.sources_tracked == 0


def test_null_last_attempted_is_ignored():
    statuses = {"sleeper": {"last_attempted": None, "last_updated": None}}
    v = evaluate_data_freshness(statuses, now=NOW)
    assert v.status == "no_data"
    assert v.stale is False
    assert v.sources_tracked == 1  # tracked, but no usable attempt


def test_boundary_exactly_at_threshold_is_healthy():
    # Default threshold 2h; the comparison is strictly `>`, so exactly 2h is OK.
    v = evaluate_data_freshness(_status(2.0), now=NOW, threshold_hours=2.0)
    assert v.stale is False
    assert v.status == "healthy"


def test_boundary_just_past_threshold_is_stale():
    v = evaluate_data_freshness(_status(2.0 + 1 / 3600), now=NOW, threshold_hours=2.0)
    assert v.stale is True


def test_staleness_keys_on_oldest_source():
    # One fresh, one stale source: the oldest drives the alarm even though
    # another source was attempted seconds ago.
    statuses = {**_status(0.01, "sleeper"), **_status(9, "espn")}
    v = evaluate_data_freshness(statuses, now=NOW, threshold_hours=2.0)
    assert v.stale is True
    assert v.oldest_source == "espn"
    assert v.newest_attempt_age_seconds == pytest.approx(36.0, abs=1.0)


def test_all_fresh_multiple_sources_healthy():
    statuses = {**_status(0.5, "sleeper"), **_status(1.0, "espn")}
    v = evaluate_data_freshness(statuses, now=NOW, threshold_hours=2.0)
    assert v.stale is False
    assert v.oldest_source == "espn"


def test_z_suffix_timestamp_parsed():
    statuses = {"sleeper": {"last_attempted": "2026-06-22T12:00:00Z"}}
    v = evaluate_data_freshness(statuses, now=NOW)
    assert v.oldest_attempt_age_seconds == pytest.approx(3600.0)


def test_offset_timestamp_normalised():
    # 12:00 at +02:00 == 10:00Z == 3h before 13:00Z.
    statuses = {"sleeper": {"last_attempted": "2026-06-22T12:00:00+02:00"}}
    v = evaluate_data_freshness(statuses, now=NOW, threshold_hours=2.0)
    assert v.oldest_attempt_age_seconds == pytest.approx(10800.0)
    assert v.stale is True


def test_future_timestamp_clamped_not_negative():
    # Clock skew should not yield a negative age or a 500 on the live endpoint.
    v = evaluate_data_freshness(_status(-0.5), now=NOW)
    assert v.oldest_attempt_age_seconds == 0.0
    assert v.stale is False


def test_now_defaults_to_utc_when_omitted():
    statuses = {"sleeper": {"last_attempted": datetime.now(timezone.utc).isoformat()}}
    v = evaluate_data_freshness(statuses)
    assert v.stale is False
    assert v.status == "healthy"


def test_now_accepts_iso_string():
    v = evaluate_data_freshness(_status(3), now="2026-06-22T13:00:00Z", threshold_hours=2.0)
    assert v.stale is True


def test_threshold_is_reported_in_seconds():
    v = evaluate_data_freshness(_status(0.5), now=NOW, threshold_hours=2.0)
    assert v.threshold_seconds == 7200


def test_non_positive_threshold_raises():
    with pytest.raises(ValueError):
        evaluate_data_freshness(_status(1), now=NOW, threshold_hours=0)


def test_to_dict_is_json_friendly():
    v = evaluate_data_freshness(_status(1), now=NOW)
    d = v.to_dict()
    assert d["status"] == "healthy"
    assert set(d) == {
        "status", "stale", "threshold_seconds", "oldest_attempt_age_seconds",
        "newest_attempt_age_seconds", "oldest_source", "sources_tracked", "detail",
    }


# --------------------------------------------------------------------------- #
# /api/data/health endpoint                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_health_endpoint_no_data_returns_200(async_client):
    resp = await async_client.get("/api/data/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "no_data"
    assert body["stale"] is False


@pytest.mark.asyncio
async def test_health_endpoint_fresh_returns_200(async_client, test_db):
    await upsert_status(
        test_db, source="sleeper", last_attempted=datetime.utcnow(),
        success=True, rows_upserted=10, error=None,
    )
    await test_db.commit()
    resp = await async_client.get("/api/data/health")
    assert resp.status_code == 200
    assert resp.json()["stale"] is False


@pytest.mark.asyncio
async def test_health_endpoint_stale_returns_503(async_client, test_db):
    stale_ts = datetime.utcnow() - timedelta(hours=12)
    await upsert_status(
        test_db, source="sleeper", last_attempted=stale_ts,
        success=False, rows_upserted=0, error="boom",
    )
    await test_db.commit()
    resp = await async_client.get("/api/data/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["stale"] is True
    assert body["status"] == "stale"
    assert body["oldest_source"] == "sleeper"


@pytest.mark.asyncio
async def test_health_endpoint_retired_stale_source_ignored(async_client, test_db):
    """A lingering retired-source row must not fire a false 503 (#786).

    Between a retirement deploy and the next `purge_retired_status()` cycle, a
    retired source's row stops advancing `last_attempted`. It must not become the
    "oldest attempt" that trips the stale alarm while every live source is fresh.
    """
    retired = RETIRED_SOURCES[0]
    stale_ts = datetime.utcnow() - timedelta(hours=12)
    await upsert_status(
        test_db, source=retired, last_attempted=stale_ts,
        success=False, rows_upserted=0, error="retired",
    )
    await upsert_status(
        test_db, source="sleeper", last_attempted=datetime.utcnow(),
        success=True, rows_upserted=10, error=None,
    )
    await test_db.commit()
    resp = await async_client.get("/api/data/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is False
    assert body["oldest_source"] == "sleeper"


@pytest.mark.asyncio
async def test_health_endpoint_only_retired_stale_source_is_no_data(async_client, test_db):
    """If the ONLY tracked row is a stale retired source, that's not an alarm.

    Excluding it leaves no live source with a usable attempt, which reads as
    `no_data` (200), never a stale 503.
    """
    retired = RETIRED_SOURCES[0]
    stale_ts = datetime.utcnow() - timedelta(hours=12)
    await upsert_status(
        test_db, source=retired, last_attempted=stale_ts,
        success=False, rows_upserted=0, error="retired",
    )
    await test_db.commit()
    resp = await async_client.get("/api/data/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is False
    assert body["status"] == "no_data"
