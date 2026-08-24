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
async def test_sleeper_normalizes_def_to_dst(test_db, mock_sleeper):
    """Sleeper returns team defenses with position 'DEF'; we store them as 'DST'."""
    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    bills = await test_db.scalar(select(Player).where(Player.id == "def_1"))
    assert bills is not None
    assert bills.position == "DST", f"Expected DST, got {bills.position}"


def _one_player_payload(team):
    """Sleeper feed with a single active player whose team we control."""
    return {
        "4017": {
            "player_id": "4017", "first_name": "Josh", "last_name": "Allen",
            "full_name": "Josh Allen", "position": "QB", "team": team,
            "age": 29, "years_exp": 7, "active": True,
            "gsis_id": "00-0034796", "espn_id": 3918298,
        },
    }


@pytest.mark.asyncio
async def test_sleeper_free_agent_survives_and_keeps_history(test_db):
    """A player who becomes a free agent (team X -> None) is NOT deleted, and his
    FK-linked PlayerStat/Projection/ADPData rows survive the second sync (#791)."""
    from app.models import PlayerStat, Projection, ADPData
    from datetime import date

    fetcher = SleeperFetcher()

    # First sync: player is rostered on BUF.
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(
            return_value=Response(200, json=_one_player_payload("BUF")))
        await fetcher.fetch(test_db)

    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen is not None and allen.team == "BUF"

    # Seed history that the cascade would wipe on a hard-delete.
    test_db.add(PlayerStat(player_id="4017", season=2025, pass_yards=4000))
    test_db.add(Projection(
        player_id="4017", source="espn", scoring_format="ppr",
        projected_points=300.0, last_updated=date.today(),
    ))
    test_db.add(ADPData(
        player_id="4017", format="ppr", adp=12.0,
        adp_source="fantasypros", last_updated=date.today(),
    ))
    await test_db.commit()

    # Second sync: player is now a free agent (team=None) but still active.
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(
            return_value=Response(200, json=_one_player_payload(None)))
        await fetcher.fetch(test_db)

    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen is not None, "free agent must not be hard-deleted"
    assert allen.team is None
    # History survived — no cascade fired.
    assert await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "4017")) is not None
    assert await test_db.scalar(select(Projection).where(Projection.player_id == "4017")) is not None
    assert await test_db.scalar(select(ADPData).where(ADPData.player_id == "4017")) is not None


@pytest.mark.asyncio
async def test_sleeper_free_agent_resigns_resumes_team_context(test_db):
    """A re-signed free agent (team None -> real team) resumes normal team data
    without re-seeding, because the row was never destroyed (#791)."""
    from app.models import PlayerStat

    fetcher = SleeperFetcher()

    # Sync as a free agent first, with history attached.
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(
            return_value=Response(200, json=_one_player_payload(None)))
        await fetcher.fetch(test_db)
    test_db.add(PlayerStat(player_id="4017", season=2025, pass_yards=4000))
    await test_db.commit()

    # Re-signs to KC.
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(
            return_value=Response(200, json=_one_player_payload("KC")))
        await fetcher.fetch(test_db)

    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen is not None and allen.team == "KC"
    # Pre-existing history is still attached — no blank-slate re-creation.
    assert await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "4017")) is not None


@pytest.mark.asyncio
async def test_sleeper_inactive_player_still_pruned(test_db):
    """A player Sleeper marks inactive (retired) is still hard-deleted — only
    unrostered-but-active free agents are preserved (#791)."""
    test_db.add(Player(id="retired_guy", name="Old Guy", position="WR", team="DEN", active=True))
    await test_db.commit()

    payload = {
        "retired_guy": {
            "player_id": "retired_guy", "full_name": "Old Guy", "position": "WR",
            "team": None, "active": False,
        },
    }
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(200, json=payload))
        fetcher = SleeperFetcher()
        await fetcher.fetch(test_db)

    assert await test_db.scalar(select(Player).where(Player.id == "retired_guy")) is None


@pytest.mark.asyncio
async def test_sleeper_skips_non_fantasy_positions(test_db):
    """The position gate stands on its own now that it no longer shares a
    condition with the team check (#791): linemen, punters and entries with no
    position at all are skipped regardless of team or ``active``, and an
    existing row for one of them is pruned like any other unseen player."""
    test_db.add(Player(id="ol_1", name="Some Guard", position="QB", team="DEN", active=True))
    await test_db.commit()

    payload = {
        "4017": {
            "player_id": "4017", "full_name": "Josh Allen", "position": "QB",
            "team": "BUF", "active": True,
        },
        # Rostered and active, but not a fantasy position — must never persist.
        "ol_1": {
            "player_id": "ol_1", "full_name": "Some Guard", "position": "OL",
            "team": "DEN", "active": True,
        },
        "p_1": {
            "player_id": "p_1", "full_name": "Some Punter", "position": "P",
            "team": "KC", "active": True,
        },
        # Sleeper occasionally emits entries with no position key at all.
        "no_pos_1": {
            "player_id": "no_pos_1", "full_name": "Mystery Man",
            "team": "SF", "active": True,
        },
    }
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(200, json=payload))
        fetcher = SleeperFetcher()
        result = await fetcher.fetch(test_db)

    assert result.success
    assert result.rows_upserted == 1, "only the QB counts toward the upsert total"
    ids = {p.id for p in (await test_db.scalars(select(Player))).all()}
    assert ids == {"4017"}, f"non-fantasy positions leaked into the DB: {ids - {'4017'}}"


@pytest.mark.asyncio
async def test_sleeper_handles_http_error(test_db):
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(503, text="Service Unavailable"))
        fetcher = SleeperFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "503" in (result.error or "")
        assert result.rows_upserted == 0
