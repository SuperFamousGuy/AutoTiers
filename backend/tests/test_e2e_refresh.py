"""End-to-end: run refresh against fixtures, then call /api/generate and verify real output."""
import json
import pytest
import respx
import pandas as pd
from httpx import Response
from pathlib import Path
from datetime import date, datetime

from app.data.fetcher import DataFetcher


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def all_mocks(monkeypatch):
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")
    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    sleeper_fix = json.loads((FIXTURES / "sleeper_players.json").read_text())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(200, json=sleeper_fix))
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_projections_wr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        # CBS: scaffold-only, no real fixture data — mock as failing.
        router.get(url__regex=r"https://www\.cbssports\.com/.*").mock(return_value=Response(500))
        # Spotrac: mock all per-position pages as empty so the fetcher succeeds.
        router.get(url__regex=r"https://www\.spotrac\.com/nfl/positional/.*").mock(
            return_value=Response(200, text="<html><body></body></html>")
        )
        yield router


@pytest.mark.asyncio
async def test_refresh_then_generate_returns_real_players(async_client, test_db, all_mocks):
    # Refresh
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)
    # CBS is scaffold-only (mocked to fail). Other sources must succeed.
    for src, r in results.items():
        if src == "cbs":
            continue
        assert r["last_error"] is None, f"{src} failed: {r['last_error']}"

    # Generate
    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.4, "weight_espn": 0.3,
        "weight_consensus": 0.3, "weight_adp": 0.0, "rules": [],
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    # We seeded Chase (WR) and Jefferson (WR) via Sleeper, both have real projections.
    names = {p["name"] for p in body["players"]}
    assert "Ja'Marr Chase" in names
    assert "Justin Jefferson" in names

    # data_as_of is now today (all sources just refreshed).
    # Use UTC date to match datetime.utcnow() used in production fetchers.
    assert body["data_as_of"] == datetime.utcnow().date().isoformat()

    # At least one player should have rules_applied (from PBP-derived rules firing).
    any_rules = any(p["rules_applied"] for p in body["players"])
    assert any_rules, "expected at least one rule to apply after PBP data loaded"
