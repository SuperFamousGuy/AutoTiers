"""Tests for the smaller endpoint files (players, data, main lifespan).

These fill in coverage gaps for thin routers and the app lifespan.
"""
import pytest
from unittest.mock import patch
from app.models.player import Player
from app.main import app, lifespan
from app.config import settings
from app.api.data import require_admin
from fastapi import HTTPException


# ---------------------- players router ----------------------

@pytest.mark.asyncio
async def test_list_players_returns_empty_when_db_empty(async_client):
    resp = await async_client.get("/api/players")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_players_returns_seeded_players_alpha_sorted(async_client, test_db):
    test_db.add(Player(id="b_id", name="Bijan Robinson", position="RB", team="ATL", age=23))
    test_db.add(Player(id="a_id", name="Amon-Ra St. Brown", position="WR", team="DET", age=26))
    await test_db.commit()

    resp = await async_client.get("/api/players")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # Sorted alphabetically by name
    assert body[0]["name"] == "Amon-Ra St. Brown"
    assert body[1]["name"] == "Bijan Robinson"
    # Each row has the documented shape
    assert set(body[0].keys()) == {"id", "name", "position", "team", "age"}


# ---------------------- data router ----------------------

@pytest.mark.asyncio
async def test_require_admin_no_key_configured_allows_anyone():
    # When admin_api_key is empty, require_admin should not raise
    with patch.object(settings, "admin_api_key", ""):
        await require_admin(x_api_key="")  # no exception
        await require_admin(x_api_key="anything")  # no exception


@pytest.mark.asyncio
async def test_require_admin_rejects_wrong_key():
    with patch.object(settings, "admin_api_key", "the-secret"):
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(x_api_key="wrong")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_accepts_correct_key():
    with patch.object(settings, "admin_api_key", "the-secret"):
        await require_admin(x_api_key="the-secret")  # no exception


# ---------------------- main lifespan ----------------------

@pytest.mark.asyncio
async def test_lifespan_no_scheduler_when_run_scheduler_false():
    """When RUN_SCHEDULER is false, lifespan should not start the scheduler."""
    with patch.object(settings, "run_scheduler", False):
        with patch("app.main.setup_scheduler") as mock_setup, patch("app.main.scheduler") as mock_sched:
            mock_sched.running = False
            async with lifespan(app):
                pass
            mock_setup.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_starts_and_shuts_down_scheduler_when_enabled():
    """When RUN_SCHEDULER is true, lifespan starts on entry and shuts down on exit."""
    with patch.object(settings, "run_scheduler", True):
        with patch("app.main.setup_scheduler") as mock_setup, patch("app.main.scheduler") as mock_sched:
            mock_sched.running = True
            async with lifespan(app):
                mock_setup.assert_called_once()
            mock_sched.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_skips_shutdown_when_scheduler_not_running():
    """If scheduler.running is False on exit, shutdown() should not be called."""
    with patch.object(settings, "run_scheduler", True):
        with patch("app.main.setup_scheduler"), patch("app.main.scheduler") as mock_sched:
            mock_sched.running = False
            async with lifespan(app):
                pass
            mock_sched.shutdown.assert_not_called()
