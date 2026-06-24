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


@pytest.fixture
def mock_all_sources(monkeypatch):
    """Wire all live sources to fixture data."""
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
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_projections_wr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/(qb|rb|te|k|dst)\.php.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/adp/ppr\.php").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_adp_ppr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/adp/(overall|half-point-ppr)\.php").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        # CBS: scaffold-only / unreliable scrape; mock as failing for now.
        router.get(url__regex=r"https://www\.cbssports\.com/.*").mock(return_value=Response(500))
        yield router


@pytest.mark.asyncio
async def test_refresh_runs_all_sources(test_db, mock_all_sources):
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)

    assert set(results.keys()) == {"sleeper", "nfl_data_py", "fantasypros", "cbs"}
    # CBS is mocked to fail (no real fixture data yet); others should succeed.
    for src, r in results.items():
        if src == "cbs":
            assert r["last_error"] is not None
            continue
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
    assert sources == {"sleeper", "nfl_data_py", "fantasypros", "cbs"}
    for s in statuses:
        assert s.last_attempted is not None
        if s.source == "cbs":
            # CBS is scaffold-only; mocked to fail in this fixture.
            assert s.last_error is not None
            continue
        assert s.last_updated is not None
        assert s.last_error is None


@pytest.mark.asyncio
async def test_refresh_continues_when_one_source_fails(test_db, monkeypatch):
    """When one downstream source fails, others still complete and persist."""
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")
    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(200, json=SLEEPER_FIXTURE))
        router.get(url__regex=r"https://www\.fantasypros\.com/.*").mock(return_value=Response(503))
        router.get(url__regex=r"https://www\.cbssports\.com/.*").mock(return_value=Response(500))

        fetcher = DataFetcher(prior_season=2025, current_season=2026)
        results = await fetcher.refresh_all(test_db)

    assert results["sleeper"]["last_error"] is None
    assert results["nfl_data_py"]["last_error"] is None
    assert results["fantasypros"]["last_error"] is not None and "503" in results["fantasypros"]["last_error"]
    assert results["cbs"]["last_error"] is not None

    fp_status = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "fantasypros"))
    assert fp_status.last_updated is None
    assert "503" in fp_status.last_error


@pytest.mark.asyncio
async def test_refresh_purges_retired_source_status(test_db, mock_all_sources):
    """A stale status row for a retired source (spotrac) is dropped on refresh."""
    from datetime import datetime
    test_db.add(DataSourceStatus(
        source="spotrac", last_attempted=datetime.utcnow(), rows_upserted=0,
        last_error="404 retired",
    ))
    await test_db.commit()

    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)

    assert "spotrac" not in results
    remaining = {s.source for s in (await test_db.scalars(select(DataSourceStatus))).all()}
    assert "spotrac" not in remaining


@pytest.mark.asyncio
async def test_refresh_returns_skipped_when_sleeper_fails(test_db):
    """If Sleeper fails, downstream sources need its player map — they're skipped."""
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(503))

        fetcher = DataFetcher(prior_season=2025, current_season=2026)
        results = await fetcher.refresh_all(test_db)

    assert "503" in results["sleeper"]["last_error"]
    for src in ("nfl_data_py", "fantasypros", "cbs"):
        assert "skipped" in (results[src]["last_error"] or "").lower()
