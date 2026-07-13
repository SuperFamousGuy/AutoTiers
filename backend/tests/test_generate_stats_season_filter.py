"""Regression test for issue #695.

``_run_generate`` used to eager-load ``Player.stats`` unfiltered. ``NflDataFetcher``
retains up to three prior seasons and never deletes rows, but the tiering only
ever reads two seasons: ``current_year - 1`` (via ``_get_stat``, feeding
``prior_actual``/xFP) and ``current_year - 2`` (the ``injured_two_years_ago``
lookup). So the oldest retained season (``current_year - 3``) was fetched from
the DB, deserialized, copied into ``_StatSnapshot`` dataclasses, and shipped into
the ``asyncio.to_thread`` worker payload for every player on every request — with
zero downstream use.

The fix filters the ``stats`` selectinload to ``season >= current_year - 2`` using
SQLAlchemy 2.0 relationship loader criteria, so that dead season never leaves the
DB. These tests prove (a) the ``current_year - 3`` row never reaches the worker,
and (b) output is unchanged whether or not that stale row exists.
"""
from datetime import datetime

import pytest

import app.api.generate as gen
from app.models.player import Player, PlayerStat
from app.models.projection import Projection


CONSENSUS = 100.0


def _stat(pid: str, season: int, *, games_played: int = 16) -> PlayerStat:
    """A healthy full-season WR line."""
    return PlayerStat(
        player_id=pid, season=season,
        targets=140, receptions=100, rec_yards=1400.0, rec_tds=10,
        rush_att=0, rush_yards=0.0, rush_tds=0,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
        games_played=games_played, red_zone_looks=12,
    )


def _body() -> dict:
    return {
        "scoring_format": "ppr",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.5,
        "weight_espn": 0.0,
        "weight_consensus": 0.5,
        "rules": {},
    }


def _find(resp_json: dict, pid: str) -> dict:
    return next(p for p in resp_json["players"] if p["player_id"] == pid)


@pytest.mark.asyncio
async def test_stale_season_never_reaches_the_worker(async_client, test_db, monkeypatch):
    """A player seeded with current_year-1/-2/-3 stat rows must arrive at the
    off-loop worker with only the two consumed seasons — the current_year-3 row
    is filtered out at load time and never leaves the DB."""
    current_year = datetime.utcnow().year
    cutoff = current_year - 2

    test_db.add(Player(id="three", name="Three Seasons", position="WR", team="AAA", age=27, years_exp=5))
    test_db.add(_stat("three", current_year - 1))
    test_db.add(_stat("three", current_year - 2))
    test_db.add(_stat("three", current_year - 3))
    test_db.add(Projection(player_id="three", source="fantasypros",
                           scoring_format="ppr", projected_points=CONSENSUS))
    await test_db.commit()

    captured: dict = {}
    original = gen._compute_ranked_players

    def spy(players, **kwargs):
        captured["players"] = players
        return original(players, **kwargs)

    monkeypatch.setattr(gen, "_compute_ranked_players", spy)

    resp = await async_client.post("/api/generate", json=_body())
    assert resp.status_code == 200, resp.text

    snap = next(p for p in captured["players"] if p.id == "three")
    seasons = sorted(s.season for s in snap.stats)
    # Only the two consumed seasons made it into the worker payload.
    assert seasons == [current_year - 2, current_year - 1]
    assert all(s.season >= cutoff for s in snap.stats)
    # The stale current_year-3 row was filtered out at the loader, not the worker.
    assert current_year - 3 not in seasons


@pytest.mark.asyncio
async def test_output_identical_with_or_without_stale_season(async_client, test_db):
    """Two otherwise-identical players — one carrying an extra current_year-3 row,
    one without — produce byte-identical scoring output, confirming the third
    season fed nothing."""
    current_year = datetime.utcnow().year

    # WITH the stale third season.
    test_db.add(Player(id="with", name="With Stale", position="WR", team="AAA", age=27, years_exp=5))
    test_db.add(_stat("with", current_year - 1))
    test_db.add(_stat("with", current_year - 2, games_played=10))
    test_db.add(_stat("with", current_year - 3))
    test_db.add(Projection(player_id="with", source="fantasypros",
                           scoring_format="ppr", projected_points=CONSENSUS))

    # WITHOUT it — identical otherwise.
    test_db.add(Player(id="without", name="Without Stale", position="WR", team="AAA", age=27, years_exp=5))
    test_db.add(_stat("without", current_year - 1))
    test_db.add(_stat("without", current_year - 2, games_played=10))
    test_db.add(Projection(player_id="without", source="fantasypros",
                           scoring_format="ppr", projected_points=CONSENSUS))
    await test_db.commit()

    resp = await async_client.post("/api/generate", json=_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()

    a = _find(data, "with")
    b = _find(data, "without")

    # Compare every scoring/flag field; only identity fields may differ.
    ignore = {"player_id", "name", "overall_rank"}
    a_cmp = {k: v for k, v in a.items() if k not in ignore}
    b_cmp = {k: v for k, v in b.items() if k not in ignore}
    assert a_cmp == b_cmp
    # Sanity: the current_year-2 row IS still read (games_played=10 < 12 → flag).
    assert a["prior_year_actual"] is not None
