import asyncio

import pytest
from unittest.mock import patch, AsyncMock
from app.api.data import _run_refresh
from app.data.fetcher import fetcher


@pytest.fixture(autouse=True)
def _reset_refresh_flag():
    """Keep the process-global refresh slot hermetic per test.

    Some tests mock out _run_refresh (so its finally-block end_refresh() never
    runs) or deliberately claim the slot; without this reset a leaked flag
    would make a later test see a spurious 409 / skipped refresh.
    """
    fetcher.end_refresh()
    yield
    fetcher.end_refresh()


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


@pytest.mark.asyncio
async def test_run_refresh_releases_slot_on_success():
    """The refresh slot must be freed after a successful run (issue #827)."""
    assert fetcher.try_begin_refresh() is True  # simulate the endpoint claiming it
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.data.AsyncSessionLocal", return_value=mock_session_cm), \
         patch("app.api.data.fetcher.refresh_all", new_callable=AsyncMock):
        await _run_refresh()
    assert fetcher.is_refreshing is False


@pytest.mark.asyncio
async def test_run_refresh_releases_slot_on_failure():
    """A failed run must not wedge the slot permanently (issue #827)."""
    assert fetcher.try_begin_refresh() is True
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.data.AsyncSessionLocal", return_value=mock_session_cm), \
         patch("app.api.data.fetcher.refresh_all", side_effect=RuntimeError("boom")):
        await _run_refresh()
    assert fetcher.is_refreshing is False


@pytest.mark.asyncio
async def test_concurrent_refresh_returns_409(async_client):
    """A second POST while a refresh is in flight returns 409 and schedules
    no second run; once the first completes, a subsequent POST succeeds
    (issue #827 acceptance criteria)."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_refresh(db):
        started.set()
        await release.wait()
        return {}

    with patch("app.api.data.fetcher.refresh_all", side_effect=slow_refresh):
        # POST #1 blocks until its background refresh finishes (Starlette runs
        # BackgroundTasks before the ASGI call returns), so drive it as a task.
        first = asyncio.create_task(async_client.post("/api/data/refresh"))
        # Wait until the first refresh is genuinely in flight.
        await asyncio.wait_for(started.wait(), timeout=2)

        # POST #2 while #1 is pending -> 409, no second refresh scheduled.
        resp2 = await async_client.post("/api/data/refresh")
        assert resp2.status_code == 409
        assert resp2.json() == {"detail": "A data refresh is already in progress."}

        # Let the first refresh resolve and drain its background task.
        release.set()
        resp1 = await asyncio.wait_for(first, timeout=2)
        assert resp1.status_code == 200
        assert resp1.json() == {"status": "refresh started"}

    # Slot released -> a fresh POST schedules normally.
    with patch("app.api.data.fetcher.refresh_all", new_callable=AsyncMock):
        resp3 = await async_client.post("/api/data/refresh")
    assert resp3.status_code == 200
    assert resp3.json() == {"status": "refresh started"}
    assert fetcher.is_refreshing is False


def test_try_begin_refresh_is_mutually_exclusive():
    """Unit-level check of the claim/release primitive (issue #827)."""
    assert fetcher.is_refreshing is False
    assert fetcher.try_begin_refresh() is True
    assert fetcher.is_refreshing is True
    # A second claim while held is refused.
    assert fetcher.try_begin_refresh() is False
    fetcher.end_refresh()
    assert fetcher.is_refreshing is False
    # Releasable and re-claimable after.
    assert fetcher.try_begin_refresh() is True
    fetcher.end_refresh()
