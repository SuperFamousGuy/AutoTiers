"""Regression test for issue #608.

``_get_stat`` used to return ``max(stats, key=season)`` — the newest PlayerStat
on file regardless of which season it belonged to. ``NflDataFetcher`` retains up
to three prior seasons and never deletes rows, so a player who missed last
season (injury, retirement, out of the league) still has an older row. That
stale row (a full ~16-game workload) was fed into ``blend_scores``'s prior-year
games ramp, which therefore applied NO discount — so a 2-3-year-old healthy
season was blended in at full prior-year weight, exactly the case the ramp
exists to catch.

The fix makes ``_get_stat`` season-exact: it only returns the ``current_year-1``
row and returns ``None`` otherwise, so a stale-only player carries
``prior_year_actual=None`` and the prior-year term drops out of the blend.

These tests drive the full HTTP path with two otherwise-identical WRs whose only
difference is the SEASON their stat row belongs to.
"""
from datetime import datetime

import pytest

from app.models.player import Player, PlayerStat
from app.models.projection import Projection


# Consensus projection every seeded player shares. Low relative to the prior
# actual so that blending the prior in visibly moves projected_score_raw up.
CONSENSUS = 100.0


def _stat(pid: str, season: int) -> PlayerStat:
    """A healthy full-season WR line (16 games) — high PPR prior actual."""
    return PlayerStat(
        player_id=pid, season=season,
        targets=140, receptions=100, rec_yards=1400.0, rec_tds=10,
        rush_att=0, rush_yards=0.0, rush_tds=0,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
        games_played=16, red_zone_looks=12,
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
        # Heavy prior-year weight so an included prior clearly moves the blend.
        "weight_prior_year": 0.5,
        "weight_espn": 0.0,
        "weight_consensus": 0.5,
        "rules": {},
    }


def _find(resp_json: dict, pid: str) -> dict:
    return next(p for p in resp_json["players"] if p["player_id"] == pid)


@pytest.mark.asyncio
async def test_stale_only_stat_is_not_blended_at_full_prior_weight(async_client, test_db):
    """A player whose ONLY stat row is current_year-3 (16 games) must not have
    that stale season blended in — prior_year_actual is None and the raw score
    collapses to consensus-only, not pulled up toward the old season."""
    current_year = datetime.utcnow().year
    prior_season = current_year - 1
    stale_season = current_year - 3

    # STALE: only a 3-season-old row, no current_year-1 row.
    test_db.add(Player(id="stale", name="Stale WR", position="WR", team="AAA", age=29, years_exp=7))
    test_db.add(_stat("stale", stale_season))
    test_db.add(Projection(player_id="stale", source="fantasypros",
                           scoring_format="ppr", projected_points=CONSENSUS))

    # FRESH: identical line, but on the genuine prior season — the control.
    test_db.add(Player(id="fresh", name="Fresh WR", position="WR", team="BBB", age=25, years_exp=3))
    test_db.add(_stat("fresh", prior_season))
    test_db.add(Projection(player_id="fresh", source="fantasypros",
                           scoring_format="ppr", projected_points=CONSENSUS))
    await test_db.commit()

    resp = await async_client.post("/api/generate", json=_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    stale = _find(data, "stale")
    fresh = _find(data, "fresh")

    # The genuine prior season IS blended: a real prior actual is exposed and it
    # pulls the raw score above the consensus-only value.
    assert fresh["prior_year_actual"] is not None
    assert fresh["projected_score_raw"] > CONSENSUS

    # The stale-only player carries NO prior actual, so the prior term drops out
    # and the raw score is exactly consensus-only — NOT pulled up like `fresh`.
    assert stale["prior_year_actual"] is None
    assert stale["projected_score_raw"] == pytest.approx(CONSENSUS)
    # The bug: stale would have blended to the same high value as `fresh`.
    assert stale["projected_score_raw"] < fresh["projected_score_raw"]


@pytest.mark.asyncio
async def test_normal_prior_year_row_is_byte_identical(async_client, test_db):
    """A player with a normal current_year-1 row behaves exactly as before the
    fix: the prior actual is present and blended at full weight (16 games >=
    full_season_games default, so no games discount)."""
    prior_season = datetime.utcnow().year - 1

    test_db.add(Player(id="normal", name="Normal WR", position="WR", team="CCC", age=26, years_exp=4))
    test_db.add(_stat("normal", prior_season))
    test_db.add(Projection(player_id="normal", source="fantasypros",
                           scoring_format="ppr", projected_points=CONSENSUS))
    await test_db.commit()

    resp = await async_client.post("/api/generate", json=_body())
    assert resp.status_code == 200, resp.text
    normal = _find(resp.json(), "normal")

    prior = normal["prior_year_actual"]
    assert prior is not None and prior > CONSENSUS
    # 16 games >= default full_season_games (14) -> no discount -> plain 50/50 blend.
    assert normal["projected_score_raw"] == pytest.approx(0.5 * prior + 0.5 * CONSENSUS)
