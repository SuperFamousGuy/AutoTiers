import pytest
from datetime import datetime
from sqlalchemy import select
from app.models import DataSourceStatus
from app.data.status import upsert_status, get_all_status


@pytest.mark.asyncio
async def test_upsert_status_inserts_new(test_db):
    now = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="sleeper", last_attempted=now,
                        success=True, rows_upserted=1000, error=None)
    await test_db.commit()
    row = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "sleeper"))
    assert row.rows_upserted == 1000
    assert row.last_updated == now
    assert row.last_error is None


@pytest.mark.asyncio
async def test_upsert_status_updates_existing(test_db):
    t1 = datetime(2026, 5, 19, 12, 0, 0)
    t2 = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="sleeper", last_attempted=t1, success=True, rows_upserted=500, error=None)
    await test_db.commit()
    await upsert_status(test_db, source="sleeper", last_attempted=t2, success=True, rows_upserted=600, error=None)
    await test_db.commit()
    row = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "sleeper"))
    assert row.rows_upserted == 600
    assert row.last_updated == t2


@pytest.mark.asyncio
async def test_upsert_status_failure_keeps_last_updated(test_db):
    """When a refresh fails, last_attempted advances but last_updated does not."""
    t1 = datetime(2026, 5, 19, 12, 0, 0)
    t2 = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="espn", last_attempted=t1, success=True, rows_upserted=400, error=None)
    await test_db.commit()
    await upsert_status(test_db, source="espn", last_attempted=t2, success=False, rows_upserted=0, error="HTTP 503")
    await test_db.commit()
    row = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "espn"))
    assert row.last_updated == t1   # unchanged
    assert row.last_attempted == t2  # advanced
    assert row.last_error == "HTTP 503"


@pytest.mark.asyncio
async def test_get_all_status_returns_dict(test_db):
    now = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="sleeper", last_attempted=now, success=True, rows_upserted=10, error=None)
    await upsert_status(test_db, source="espn", last_attempted=now, success=False, rows_upserted=0, error="bad")
    await test_db.commit()
    result = await get_all_status(test_db)
    assert set(result.keys()) == {"sleeper", "espn"}
    assert result["sleeper"]["rows_upserted"] == 10
    assert result["espn"]["last_error"] == "bad"
