"""Draft-capital ingestion in NflDataFetcher (#770).

Lives outside tests/test_sources (which is OOM-heavy and ignored in CI) so the
draft-population path in app/data/sources/nfl_data.py is exercised by the default
suite. All nfl_data_py network calls are monkeypatched — no network access.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.models import Player
from app.data.sources.nfl_data import NflDataFetcher, _safe_int_or_none


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, 1),
        (2.0, 2),
        (None, None),
        (float("nan"), None),
    ],
)
def test_safe_int_or_none(value, expected):
    assert _safe_int_or_none(value) == expected


@pytest.fixture
def mock_nfl_sources(monkeypatch):
    """Neutralize every nfl_data_py network call except import_draft_picks.

    Seasonal/snap/pbp/schedule all return empty frames so ``fetch`` still
    succeeds (no seasonal rows, ``last_err`` stays None). The individual test
    overrides ``import_draft_picks``.
    """
    import app.data.sources.nfl_data as mod
    monkeypatch.setattr(mod, "import_seasonal_data", lambda years: pd.DataFrame())
    monkeypatch.setattr(mod, "import_snap_counts", lambda years: pd.DataFrame())
    monkeypatch.setattr(mod, "import_pbp_data", lambda years: pd.DataFrame())
    monkeypatch.setattr(mod, "import_schedules", lambda years: pd.DataFrame())
    return mod


@pytest.mark.asyncio
async def test_draft_capital_populated_and_none_handling(test_db, mock_nfl_sources, monkeypatch):
    draft_df = pd.DataFrame([
        {"season": 2025, "round": 1, "pick": 12, "gsis_id": "00-0000001"},
        {"season": 2025, "round": 3, "pick": 80, "gsis_id": "00-0000002"},
        # Missing round/pick (e.g. undrafted row) → both resolve to None.
        {"season": 2025, "round": float("nan"), "pick": float("nan"), "gsis_id": "00-0000003"},
        # gsis not in our player table → silently skipped, no crash.
        {"season": 2025, "round": 1, "pick": 1, "gsis_id": "00-9999999"},
    ])
    monkeypatch.setattr(mock_nfl_sources, "import_draft_picks", lambda years: draft_df.copy())

    test_db.add(Player(id="p1", name="First Rounder", position="RB", team="NE", gsis_id="00-0000001"))
    test_db.add(Player(id="p2", name="Third Rounder", position="RB", team="NE", gsis_id="00-0000002"))
    test_db.add(Player(id="p3", name="Undrafted", position="RB", team="NE", gsis_id="00-0000003"))
    await test_db.commit()

    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success

    p1 = await test_db.scalar(select(Player).where(Player.id == "p1"))
    p2 = await test_db.scalar(select(Player).where(Player.id == "p2"))
    p3 = await test_db.scalar(select(Player).where(Player.id == "p3"))
    assert (p1.draft_round, p1.draft_pick) == (1, 12)
    assert (p2.draft_round, p2.draft_pick) == (3, 80)
    assert (p3.draft_round, p3.draft_pick) == (None, None)


@pytest.mark.asyncio
async def test_draft_capital_fetch_failure_is_non_fatal(test_db, mock_nfl_sources, monkeypatch):
    """import_draft_picks raising must not fail the whole fetcher (#770)."""
    def _boom(years):
        raise RuntimeError("nflreadpy is down")

    monkeypatch.setattr(mock_nfl_sources, "import_draft_picks", _boom)
    test_db.add(Player(id="p1", name="Rook", position="RB", team="NE", gsis_id="00-0000001"))
    await test_db.commit()

    fetcher = NflDataFetcher(prior_seasons=1, latest_season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success

    p1 = await test_db.scalar(select(Player).where(Player.id == "p1"))
    assert p1.draft_round is None
    assert p1.draft_pick is None
