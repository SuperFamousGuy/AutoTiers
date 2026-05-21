import json
import pytest
import respx
import pandas as pd
from httpx import Response
from pathlib import Path

from sqlalchemy import select
from app.models import Player, PlayerStat, Projection, DataSourceStatus
from app.data.fetcher import DataFetcher


FIXTURES = Path(__file__).parent / "fixtures"
SLEEPER_FIXTURE = json.loads((FIXTURES / "sleeper_players.json").read_text())
ESPN_FIXTURE = json.loads((FIXTURES / "espn_projections.json").read_text())


@pytest.fixture
def mock_all_sources(monkeypatch):
    """Wire all 4 sources to fixture data."""
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")

    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/v1/players/nfl").mock(
            return_value=Response(200, json=SLEEPER_FIXTURE)
        )
        router.get(url__regex=r"https://fantasy\.espn\.com/apis/v3/games/ffl/.*").mock(
            return_value=Response(200, json=ESPN_FIXTURE)
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_projections_wr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/(qb|rb|te)\.php.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/adp/ppr\.php").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_adp_ppr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/adp/(overall|half-point-ppr)\.php").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        yield router


@pytest.mark.asyncio
async def test_refresh_runs_all_sources(test_db, mock_all_sources):
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)

    assert set(results.keys()) == {"sleeper", "nfl_data_py", "espn", "fantasypros"}
    for src, r in results.items():
        assert r["last_error"] is None, f"{src} unexpectedly failed: {r['last_error']}"

    players = (await test_db.scalars(select(Player))).all()
    assert len(players) >= 5

    stats = (await test_db.scalars(select(PlayerStat))).all()
    assert len(stats) >= 2

    projections = (await test_db.scalars(select(Projection))).all()
    assert len(projections) >= 2


@pytest.mark.asyncio
async def test_refresh_persists_status_rows(test_db, mock_all_sources):
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    await fetcher.refresh_all(test_db)

    statuses = (await test_db.scalars(select(DataSourceStatus))).all()
    sources = {s.source for s in statuses}
    assert sources == {"sleeper", "nfl_data_py", "espn", "fantasypros"}
    for s in statuses:
        assert s.last_attempted is not None
        assert s.last_updated is not None
        assert s.last_error is None


@pytest.mark.asyncio
async def test_refresh_continues_when_one_source_fails(test_db, monkeypatch):
    # Sleeper succeeds, ESPN fails, others get fixtures.
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")
    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(200, json=SLEEPER_FIXTURE))
        router.get(url__regex=r"https://fantasy\.espn\.com/.*").mock(return_value=Response(503))
        router.get(url__regex=r"https://www\.fantasypros\.com/.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )

        fetcher = DataFetcher(prior_season=2025, current_season=2026)
        results = await fetcher.refresh_all(test_db)

    assert results["sleeper"]["last_error"] is None
    assert results["nfl_data_py"]["last_error"] is None
    assert results["fantasypros"]["last_error"] is None
    assert results["espn"]["last_error"] is not None and "503" in results["espn"]["last_error"]

    espn_status = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "espn"))
    assert espn_status.last_updated is None
    assert "503" in espn_status.last_error


@pytest.mark.asyncio
async def test_refresh_returns_skipped_when_sleeper_fails(test_db):
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(503))

        fetcher = DataFetcher(prior_season=2025, current_season=2026)
        results = await fetcher.refresh_all(test_db)

    assert "503" in results["sleeper"]["last_error"]
    for src in ("nfl_data_py", "espn", "fantasypros"):
        assert "skipped" in (results[src]["last_error"] or "").lower()
