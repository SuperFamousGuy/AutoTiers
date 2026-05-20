import pytest
from unittest.mock import patch, AsyncMock
from app.scheduler import _refresh_job, setup_scheduler, scheduler


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


@pytest.mark.asyncio
async def test_setup_scheduler_adds_two_jobs():
    if scheduler.running:
        scheduler.shutdown()
    for job in scheduler.get_jobs():
        job.remove()
    setup_scheduler()
    try:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert "weekly_refresh" in job_ids
        assert "daily_refresh" in job_ids
    finally:
        scheduler.shutdown()
