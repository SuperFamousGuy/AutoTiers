import pytest
from unittest.mock import patch, AsyncMock
from app.api.data import _run_refresh


@pytest.mark.asyncio
async def test_data_refresh_endpoint_returns_started(async_client):
    with patch("app.api.data._run_refresh", new_callable=AsyncMock):
        resp = await async_client.post("/api/data/refresh")
    assert resp.status_code == 200
    assert resp.json() == {"status": "refresh started"}


@pytest.mark.asyncio
async def test_run_refresh_calls_fetcher():
    mock_db = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.data.AsyncSessionLocal", return_value=mock_session_cm), \
         patch("app.api.data.fetcher.refresh_all", new_callable=AsyncMock) as mock_refresh:
        await _run_refresh()
        mock_refresh.assert_called_once_with(mock_db)


@pytest.mark.asyncio
async def test_run_refresh_logs_exception_on_failure():
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.data.AsyncSessionLocal", return_value=mock_session_cm), \
         patch("app.api.data.fetcher.refresh_all", side_effect=RuntimeError("boom")), \
         patch("app.api.data.logger.exception") as mock_log:
        await _run_refresh()
        mock_log.assert_called_once()
