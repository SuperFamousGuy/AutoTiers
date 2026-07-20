import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock
from app.scheduler import _refresh_job, setup_scheduler, scheduler
from app.data.fetcher import fetcher


@pytest.fixture(autouse=True)
def _reset_refresh_flag():
    # Keep the process-global refresh slot hermetic (issue #827).
    fetcher.end_refresh()
    yield
    fetcher.end_refresh()


@pytest.mark.asyncio
async def test_refresh_job_calls_fetcher():
    mock_db = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.scheduler.AsyncSessionLocal", return_value=mock_session_cm) as mock_sl, \
         patch("app.scheduler.fetcher.refresh_all", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = {"nfl_data_py": "stub"}
        await _refresh_job()
        mock_sl.assert_called_once()
        mock_refresh.assert_called_once_with(mock_db)
    # The job must release the slot when it finishes (issue #827).
    assert fetcher.is_refreshing is False


@pytest.mark.asyncio
async def test_refresh_job_releases_slot_on_failure():
    """A failing scheduled run must release the slot via finally so it doesn't
    wedge every future refresh (issue #827). Guards against a regression that
    drops the finally-block release.
    """
    mock_db = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.scheduler.AsyncSessionLocal", return_value=mock_session_cm), \
         patch("app.scheduler.fetcher.refresh_all", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            await _refresh_job()
    # The slot must be freed even though the job errored.
    assert fetcher.is_refreshing is False


@pytest.mark.asyncio
async def test_refresh_job_skips_when_refresh_in_progress():
    """A scheduler tick that lands while a refresh is already in flight must
    skip rather than launch a duplicate refresh_all run (issue #827)."""
    assert fetcher.try_begin_refresh() is True  # simulate an in-flight admin refresh
    with patch("app.scheduler.AsyncSessionLocal") as mock_sl, \
         patch("app.scheduler.fetcher.refresh_all", new_callable=AsyncMock) as mock_refresh:
        await _refresh_job()
        mock_sl.assert_not_called()
        mock_refresh.assert_not_called()
    # The skip must NOT release the slot the other run still owns.
    assert fetcher.is_refreshing is True
    fetcher.end_refresh()


@pytest.mark.asyncio
async def test_setup_scheduler_adds_hourly_job():
    if scheduler.running:
        scheduler.shutdown()
    for job in scheduler.get_jobs():
        job.remove()
    setup_scheduler()
    try:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert "hourly_refresh" in job_ids
    finally:
        scheduler.shutdown()


@pytest.mark.asyncio
async def test_setup_scheduler_fires_immediately_on_boot():
    """The hourly job must be scheduled to fire right away on boot, not +1h.

    Guards the stale-data incident fix: after a deploy redeploys the scheduler
    task, data should refresh immediately rather than waiting up to an hour.
    """
    if scheduler.running:
        scheduler.shutdown()
    for job in scheduler.get_jobs():
        job.remove()
    setup_scheduler()
    try:
        job = scheduler.get_job("hourly_refresh")
        assert job.next_run_time is not None
        # Scheduled at ≈ now, not an hour out — and not stuck far in the past
        # either, so bound it on both sides rather than just the upper end.
        now = datetime.now(ZoneInfo("UTC"))
        assert now - timedelta(minutes=1) <= job.next_run_time <= now + timedelta(seconds=5)
    finally:
        scheduler.shutdown()
