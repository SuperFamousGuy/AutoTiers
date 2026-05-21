import pytest
from pathlib import Path
from datetime import date
import pandas as pd

from sqlalchemy import select
from app.models import Player, PlayerStat
from app.data.sources.nfl_data import NflDataFetcher


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def mock_nfl_data(monkeypatch):
    """Make nfl_data_py.import_seasonal_data and import_snap_counts read local CSVs."""
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")

    import app.data.sources.nfl_data as mod
    monkeypatch.setattr(mod, "import_seasonal_data", lambda years: seasonal_df.copy())
    monkeypatch.setattr(mod, "import_snap_counts", lambda years: snap_df.copy())
    # PBP not required for these tests — return empty DataFrame.
    monkeypatch.setattr(mod, "import_pbp_data", lambda years: pd.DataFrame())


@pytest.mark.asyncio
async def test_nfl_data_upserts_seasonal_stats(test_db, mock_nfl_data):
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", gsis_id="00-0034796"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", gsis_id="00-0036900"))
    await test_db.commit()

    fetcher = NflDataFetcher(season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 2

    allen_stat = await test_db.scalar(
        select(PlayerStat).where(PlayerStat.player_id == "4017", PlayerStat.season == 2025)
    )
    assert allen_stat.pass_yards == 4180.0
    assert allen_stat.pass_tds == 33
    assert allen_stat.rush_tds == 8

    chase_stat = await test_db.scalar(
        select(PlayerStat).where(PlayerStat.player_id == "6794", PlayerStat.season == 2025)
    )
    assert chase_stat.receptions == 127
    assert chase_stat.rec_tds == 17
    assert chase_stat.snap_pct == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_nfl_data_idempotent_on_rerun(test_db, mock_nfl_data):
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", gsis_id="00-0034796"))
    await test_db.commit()

    fetcher = NflDataFetcher(season=2025)
    await fetcher.fetch(test_db)
    await fetcher.fetch(test_db)  # second call

    stats = (await test_db.scalars(
        select(PlayerStat).where(PlayerStat.player_id == "4017", PlayerStat.season == 2025)
    )).all()
    assert len(stats) == 1  # unique constraint holds; one upserted row
    assert stats[0].pass_yards == 4180.0


@pytest.mark.asyncio
async def test_nfl_data_skips_unknown_gsis(test_db, mock_nfl_data):
    """If a CSV row's gsis_id doesn't match any Player.gsis_id, skip silently."""
    fetcher = NflDataFetcher(season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 0
