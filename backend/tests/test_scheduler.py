import pytest
from unittest.mock import patch, AsyncMock
from app.scheduler import _refresh_job, setup_scheduler, scheduler


@pytest.mark.asyncio
async def test_refresh_job_calls_fetcher():
    with patch("app.scheduler.fetcher.refresh_all", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = {"nfl_data_py": "stub"}
        await _refresh_job()
        mock_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_setup_scheduler_adds_two_jobs():
    if scheduler.running:
        scheduler.shutdown()
    setup_scheduler()
    try:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert "weekly_refresh" in job_ids
        assert "daily_refresh" in job_ids
    finally:
        scheduler.shutdown()
