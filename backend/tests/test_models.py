import pytest
from datetime import datetime, date
from sqlalchemy import select
from app.models import Player, DataSourceStatus


@pytest.mark.asyncio
async def test_player_has_new_columns(test_db):
    p = Player(
        id="sleep_1234", name="Test Player", position="WR", team="DAL",
        age=25, years_exp=3, active=True, gsis_id="00-1234567", espn_id="9999",
    )
    test_db.add(p)
    await test_db.commit()
    fetched = await test_db.scalar(select(Player).where(Player.id == "sleep_1234"))
    assert fetched.active is True
    assert fetched.gsis_id == "00-1234567"
    assert fetched.espn_id == "9999"


@pytest.mark.asyncio
async def test_data_source_status_round_trip(test_db):
    now = datetime(2026, 5, 20, 3, 0, 0)
    s = DataSourceStatus(
        source="sleeper", last_updated=now, last_attempted=now,
        last_error=None, rows_upserted=1542,
    )
    test_db.add(s)
    await test_db.commit()
    fetched = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "sleeper"))
    assert fetched.rows_upserted == 1542
    assert fetched.last_error is None


@pytest.mark.asyncio
async def test_team_season_persists(test_db):
    from app.models import TeamSeason
    ts = TeamSeason(team="SF", season=2025, points_scored=423,
                    points_rank=6, last_updated=date(2026, 1, 1))
    test_db.add(ts)
    await test_db.commit()
    rows = (await test_db.scalars(select(TeamSeason))).all()
    assert len(rows) == 1
    assert rows[0].team == "SF"
    assert rows[0].points_scored == 423
