import asyncio
import json
import pytest
import respx
import pandas as pd
from datetime import datetime
from httpx import Response
from pathlib import Path

from sqlalchemy import select
from app.models import Player, PlayerStat, Projection, DataSourceStatus
from app.data.fetcher import DataFetcher
from app.data.sources.base import SourceResult


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


@pytest.mark.asyncio
async def test_refresh_propagates_cancellation(test_db, monkeypatch):
    """Cancelling the task mid-loop must propagate CancelledError, not swallow it.

    Regression for issue #660: the loop used `except BaseException`, which caught
    asyncio.CancelledError and kept running — defeating cooperative cancellation on
    shutdown/--reload/timeout. The refresh must end cancelled and NOT advance to the
    remaining downstream sources.
    """
    from app.data.sources.sleeper import SleeperFetcher
    from app.data.sources.nfl_data import NflDataFetcher
    from app.data.sources.fantasypros import FantasyProsFetcher
    from app.data.sources.cbs import CBSFetcher

    nfl_fetch_started = asyncio.Event()
    downstream_after_cancel_called = False

    async def fake_sleeper_fetch(self, db):
        return SourceResult(source="sleeper", rows_upserted=1, last_attempted=datetime.utcnow(), success=True)

    async def blocking_nfl_fetch(self, db):
        nfl_fetch_started.set()
        # Block so the task is parked in this await when we cancel it.
        await asyncio.sleep(3600)
        return SourceResult(source="nfl_data_py", rows_upserted=0, last_attempted=datetime.utcnow(), success=True)

    async def record_call(self, db):
        nonlocal downstream_after_cancel_called
        downstream_after_cancel_called = True
        return SourceResult(source="x", rows_upserted=0, last_attempted=datetime.utcnow(), success=True)

    monkeypatch.setattr(SleeperFetcher, "fetch", fake_sleeper_fetch)
    monkeypatch.setattr(NflDataFetcher, "fetch", blocking_nfl_fetch)
    monkeypatch.setattr(FantasyProsFetcher, "fetch", record_call)
    monkeypatch.setattr(CBSFetcher, "fetch", record_call)

    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    task = asyncio.create_task(fetcher.refresh_all(test_db))

    await asyncio.wait_for(nfl_fetch_started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # The loop stopped: it never advanced to the sources after nfl_data_py.
    assert downstream_after_cancel_called is False

    # Best-effort bookkeeping status was recorded for the cancelled source.
    nfl_status = await test_db.scalar(
        select(DataSourceStatus).where(DataSourceStatus.source == "nfl_data_py")
    )
    assert nfl_status is not None
    assert "shutdown" in nfl_status.last_error


@pytest.mark.asyncio
async def test_refresh_cancellation_propagates_even_if_bookkeeping_fails(test_db, monkeypatch):
    """A failure while recording the shutdown status must never mask CancelledError.

    Guards the best-effort `except Exception` inside the cancellation handler
    (issue #660): if persisting the "skipped — shutdown" status raises, the
    original cancellation must still propagate.
    """
    from app.data.sources.sleeper import SleeperFetcher
    from app.data.sources.nfl_data import NflDataFetcher

    nfl_fetch_started = asyncio.Event()

    async def ok_sleeper(self, db):
        return SourceResult(source="sleeper", rows_upserted=1, last_attempted=datetime.utcnow(), success=True)

    async def blocking_nfl_fetch(self, db):
        nfl_fetch_started.set()
        await asyncio.sleep(3600)

    orig_persist = DataFetcher._persist

    async def flaky_persist(db, result):
        if result.error == "skipped — shutdown":
            raise RuntimeError("db already closed")
        return await orig_persist(db, result)

    monkeypatch.setattr(SleeperFetcher, "fetch", ok_sleeper)
    monkeypatch.setattr(NflDataFetcher, "fetch", blocking_nfl_fetch)
    monkeypatch.setattr(DataFetcher, "_persist", staticmethod(flaky_persist))

    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    task = asyncio.create_task(fetcher.refresh_all(test_db))

    await asyncio.wait_for(nfl_fetch_started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_refresh_continues_on_plain_exception(test_db, monkeypatch):
    """A non-HTTP exception from a source becomes a failed SourceResult; loop continues.

    Guards the `except Exception` branch (issue #660): switching away from
    `except BaseException` must not narrow which ordinary errors are tolerated.
    """
    from app.data.sources.sleeper import SleeperFetcher
    from app.data.sources.nfl_data import NflDataFetcher
    from app.data.sources.fantasypros import FantasyProsFetcher
    from app.data.sources.cbs import CBSFetcher

    async def ok_sleeper(self, db):
        return SourceResult(source="sleeper", rows_upserted=1, last_attempted=datetime.utcnow(), success=True)

    async def boom_nfl(self, db):
        raise RuntimeError("kaboom")

    async def ok_fantasypros(self, db):
        return SourceResult(source="fantasypros", rows_upserted=2, last_attempted=datetime.utcnow(), success=True)

    async def ok_cbs(self, db):
        return SourceResult(source="cbs", rows_upserted=3, last_attempted=datetime.utcnow(), success=True)

    monkeypatch.setattr(SleeperFetcher, "fetch", ok_sleeper)
    monkeypatch.setattr(NflDataFetcher, "fetch", boom_nfl)
    monkeypatch.setattr(FantasyProsFetcher, "fetch", ok_fantasypros)
    monkeypatch.setattr(CBSFetcher, "fetch", ok_cbs)

    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)

    assert results["nfl_data_py"]["last_error"] is not None
    assert "kaboom" in results["nfl_data_py"]["last_error"]
    # The failure was isolated: sources after nfl_data_py still ran and succeeded.
    assert results["fantasypros"]["last_error"] is None
    assert results["cbs"]["last_error"] is None
