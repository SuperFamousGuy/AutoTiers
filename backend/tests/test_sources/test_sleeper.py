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
    assert result.rows_upserted == 8
    players = (await test_db.scalars(select(Player))).all()
    ids = {p.id for p in players}
    assert "4017" in ids
    assert "1234_inactive" not in ids


@pytest.mark.asyncio
async def test_sleeper_deletes_orphaned_players(test_db, mock_sleeper):
    """Players not in the current Sleeper response are hard-deleted (with cascade)."""
    test_db.add(Player(id="ghost_player", name="Old Guy", position="WR", team="DEN", active=True))
    await test_db.commit()

    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    ghost = await test_db.scalar(select(Player).where(Player.id == "ghost_player"))
    assert ghost is None


@pytest.mark.asyncio
async def test_sleeper_orphan_delete_cascades_to_dependent_rows(test_db, mock_sleeper):
    """Deleting an orphaned Player also clears its stats/projections/ADP via cascade FK."""
    from app.models import PlayerStat, Projection, ADPData
    from datetime import date

    # Seed a player not in the Sleeper fixture, plus dependent rows.
    test_db.add(Player(id="ghost_player", name="Old Guy", position="WR", team="DEN", active=True))
    await test_db.commit()

    test_db.add(PlayerStat(player_id="ghost_player", season=2025, receptions=50))
    test_db.add(Projection(
        player_id="ghost_player", source="espn", scoring_format="ppr",
        projected_points=100.0, last_updated=date.today(),
    ))
    test_db.add(ADPData(
        player_id="ghost_player", format="ppr", adp=200.0,
        adp_source="fantasypros", last_updated=date.today(),
    ))
    await test_db.commit()

    # Refresh — ghost should be deleted with all its dependents.
    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)

    assert await test_db.scalar(select(Player).where(Player.id == "ghost_player")) is None
    assert await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "ghost_player")) is None
    assert await test_db.scalar(select(Projection).where(Projection.player_id == "ghost_player")) is None
    assert await test_db.scalar(select(ADPData).where(ADPData.player_id == "ghost_player")) is None


@pytest.mark.asyncio
async def test_sleeper_populates_cross_ids(test_db, mock_sleeper):
    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen.gsis_id == "00-0034796"
    assert allen.espn_id == "3918298"
    assert allen.team == "BUF"


@pytest.mark.asyncio
async def test_sleeper_preserves_cross_ids_on_transient_omission(test_db):
    """Sleeper transiently drops gsis_id/espn_id; a re-fetch must NOT wipe them.

    Regression for #837: an unconditional overwrite silently nulls a
    previously-correct gsis_id, dropping the player from every downstream
    nfl_data_py join (which keys on Player.gsis_id.is_not(None)).
    """
    # Seed the player as if a prior pull correctly populated its cross-IDs.
    test_db.add(Player(
        id="4017", name="Josh Allen", position="QB", team="BUF", active=True,
        gsis_id="00-0034796", espn_id="3918298",
    ))
    await test_db.commit()

    # Fixture payload where 4017's cross-id fields are absent (gsis_id) / null (espn_id).
    payload = {
        "4017": {
            "player_id": "4017", "full_name": "Josh Allen",
            "position": "QB", "team": "BUF", "active": True,
            "espn_id": None,
        },
    }
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(200, json=payload))
        result = await SleeperFetcher().fetch(test_db)
        assert result.success

    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen.gsis_id == "00-0034796"  # unchanged, not wiped to None
    assert allen.espn_id == "3918298"     # unchanged, not wiped to None


@pytest.mark.asyncio
async def test_sleeper_normalizes_def_to_dst(test_db, mock_sleeper):
    """Sleeper returns team defenses with position 'DEF'; we store them as 'DST'."""
    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    bills = await test_db.scalar(select(Player).where(Player.id == "def_1"))
    assert bills is not None
    assert bills.position == "DST", f"Expected DST, got {bills.position}"


@pytest.mark.asyncio
async def test_sleeper_handles_http_error(test_db):
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(503, text="Service Unavailable"))
        fetcher = SleeperFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "503" in (result.error or "")
        assert result.rows_upserted == 0
