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
    # Schedule not required for these tests — return empty DataFrame.
    monkeypatch.setattr(mod, "import_schedules", lambda years: pd.DataFrame())


def test_nfl_fetcher_accepts_prior_seasons():
    fetcher = NflDataFetcher(prior_seasons=3, latest_season=2025)
    assert fetcher.seasons_to_load == [2025, 2024, 2023]


@pytest.mark.asyncio
async def test_nfl_data_upserts_seasonal_stats(test_db, mock_nfl_data):
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", gsis_id="00-0034796"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", gsis_id="00-0036900"))
    await test_db.commit()

    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
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

    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
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
    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 0


@pytest.fixture
def mock_nfl_data_with_pbp(monkeypatch):
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")

    import app.data.sources.nfl_data as mod
    monkeypatch.setattr(mod, "import_seasonal_data", lambda years: seasonal_df.copy())
    monkeypatch.setattr(mod, "import_snap_counts", lambda years: snap_df.copy())
    monkeypatch.setattr(mod, "import_pbp_data", lambda years: pbp_df.copy())
    monkeypatch.setattr(mod, "import_schedules", lambda years: pd.DataFrame())


@pytest.mark.asyncio
async def test_nfl_fetcher_upserts_stats_for_multiple_seasons(test_db, mock_nfl_data):
    """Multi-season fetch produces a PlayerStat row per (player, season)."""
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", gsis_id="00-0034796"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", gsis_id="00-0036900"))
    await test_db.commit()

    fetcher = NflDataFetcher(prior_seasons=3, latest_season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success
    # 2 players × 3 seasons = 6 upserted rows
    assert result.rows_upserted == 6

    for season in (2023, 2024, 2025):
        allen = await test_db.scalar(
            select(PlayerStat).where(PlayerStat.player_id == "4017", PlayerStat.season == season)
        )
        assert allen is not None, f"missing Allen stats for season {season}"
        assert allen.pass_yards == 4180.0


@pytest.fixture
def mock_nfl_data_with_schedule(monkeypatch):
    """Like mock_nfl_data but also stubs import_schedules to return a 2-game season."""
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    schedule_df = pd.DataFrame([
        {"season": 2025, "home_team": "SF", "away_team": "KC", "home_score": 10, "away_score": 28},
        {"season": 2025, "home_team": "KC", "away_team": "SF", "home_score": 35, "away_score": 21},
    ])

    import app.data.sources.nfl_data as mod
    monkeypatch.setattr(mod, "import_seasonal_data", lambda years: seasonal_df.copy())
    monkeypatch.setattr(mod, "import_snap_counts", lambda years: snap_df.copy())
    monkeypatch.setattr(mod, "import_pbp_data", lambda years: pd.DataFrame())
    monkeypatch.setattr(mod, "import_schedules", lambda years: schedule_df.copy())


@pytest.mark.asyncio
async def test_nfl_fetcher_populates_team_seasons(test_db, mock_nfl_data_with_schedule):
    from app.models import TeamSeason
    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success

    rows = (await test_db.scalars(select(TeamSeason))).all()
    by_team = {r.team: r.points_scored for r in rows}
    assert by_team["SF"] == 31   # 10 (home) + 21 (away)
    assert by_team["KC"] == 63   # 28 (away) + 35 (home)


@pytest.mark.asyncio
async def test_nfl_data_computes_pbp_derived_fields(test_db, mock_nfl_data_with_pbp):
    test_db.add(Player(id="8112", name="Bijan Robinson", position="RB", team="ATL", gsis_id="00-0039169"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", gsis_id="00-0036900"))
    test_db.add(Player(id="4866", name="Saquon Barkley", position="RB", team="PHI", gsis_id="00-0034844"))
    test_db.add(Player(id="6786", name="Justin Jefferson", position="WR", team="MIN", gsis_id="00-0036322"))
    await test_db.commit()

    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
    await fetcher.fetch(test_db)

    bijan = await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "8112"))
    assert bijan.red_zone_looks == 2
    assert bijan.expected_tds == pytest.approx(0.80, abs=0.01)

    chase = await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "6794"))
    assert chase.red_zone_looks == 3
    assert chase.expected_tds == pytest.approx(1.38, abs=0.01)
