import json
import pytest
import respx
from httpx import Response
from pathlib import Path

from sqlalchemy import select
from app.models import Player
from app.data.sources.sleeper import SleeperFetcher


FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "sleeper_players.json").read_text())


@pytest.fixture
def mock_sleeper():
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(200, json=FIXTURE))
        yield router


@pytest.mark.asyncio
async def test_sleeper_upserts_active_players(test_db, mock_sleeper):
    fetcher = SleeperFetcher()
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 7
    players = (await test_db.scalars(select(Player))).all()
    ids = {p.id for p in players}
    assert "4017" in ids
    assert "1234_inactive" not in ids


@pytest.mark.asyncio
async def test_sleeper_marks_missing_players_inactive(test_db, mock_sleeper):
    test_db.add(Player(id="ghost_player", name="Old Guy", position="WR", team="DEN", active=True))
    await test_db.commit()

    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    ghost = await test_db.scalar(select(Player).where(Player.id == "ghost_player"))
    assert ghost.active is False


@pytest.mark.asyncio
async def test_sleeper_populates_cross_ids(test_db, mock_sleeper):
    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen.gsis_id == "00-0034796"
    assert allen.espn_id == "3918298"
    assert allen.team == "BUF"


@pytest.mark.asyncio
async def test_sleeper_handles_http_error(test_db):
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(503, text="Service Unavailable"))
        fetcher = SleeperFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "503" in (result.error or "")
        assert result.rows_upserted == 0
