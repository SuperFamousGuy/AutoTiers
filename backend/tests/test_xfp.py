"""Unit tests for the xFP regression math.

These tests cover the pure-math layer — no DB, no async. The integration
into PlayerContext / the rule engine lives in test_xfp_rule.py.
"""
import pytest
from app.engine.scoring import LeagueSettings, LeagueType, ScoringFormat
from app.engine.xfp import (
    LeagueAverages,
    compute_league_averages,
    compute_xfp,
    compute_per_position_sigmas,
    compute_opportunity_score_z,
)


def _ppr_settings() -> LeagueSettings:
    return LeagueSettings(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.2,
        weight_espn=0.4,
        weight_consensus=0.4,
    )


# Minimal "stat-like" object the xfp module needs. We use a dataclass / dict
# so tests don't need an ORM session. The real call site passes
# app.models.player.PlayerStat instances; both must satisfy the same
# attribute-access protocol.
from dataclasses import dataclass


@dataclass
class _StubStat:
    position: str
    targets: int
    receptions: int
    rec_yards: float
    rec_tds: int
    rush_att: int
    rush_yards: float
    rush_tds: int
    red_zone_looks: int
    games_played: int
    pass_att: int = 0
    pass_yards: float = 0.0
    pass_tds: int = 0
    interceptions: int = 0


def test_league_averages_basic_two_wrs():
    """Two WRs, hand-computed averages."""
    stats = [
        _StubStat(position="WR", targets=100, receptions=70, rec_yards=900, rec_tds=6,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=15, games_played=16),
        _StubStat(position="WR", targets=80, receptions=55, rec_yards=700, rec_tds=4,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16),
    ]
    avg = compute_league_averages(stats, _ppr_settings())
    # rec pts (PPR, no bonus): WR1 = 70 + 90 = 160; WR2 = 55 + 70 = 125 → total 285.
    # total targets = 180 → pts/target = 285 / 180 = 1.5833...
    assert avg.pts_per_target["WR"] == pytest.approx(285.0 / 180.0)
    # rush pts: 0 / 0 → defined as 0.0 by guard
    assert avg.pts_per_carry.get("WR", 0.0) == 0.0
    # td pts: (6 + 4) × 6 = 60; rz looks = 25 → 60 / 25 = 2.4
    assert avg.pts_per_rz_look["WR"] == pytest.approx(2.4)


def test_league_averages_skips_low_games_played():
    """Players with games_played < 8 are excluded from averages (small-sample noise)."""
    stats = [
        _StubStat(position="WR", targets=100, receptions=70, rec_yards=900, rec_tds=6,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=15, games_played=16),
        # This injury-shortened season should NOT contribute to averages.
        _StubStat(position="WR", targets=10, receptions=8, rec_yards=120, rec_tds=2,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=3, games_played=3),
    ]
    avg = compute_league_averages(stats, _ppr_settings())
    # rec pts: 70 + 90 = 160; targets = 100; pts/target = 1.6
    assert avg.pts_per_target["WR"] == pytest.approx(1.6)


def test_compute_xfp_combines_target_carry_rzlook():
    """xFP = targets × pts/target + rush_att × pts/carry + rz_looks × pts/rzlook."""
    avg = LeagueAverages(
        pts_per_target={"WR": 1.5},
        pts_per_carry={"WR": 0.0},
        pts_per_rz_look={"WR": 2.0},
    )
    stat = _StubStat(position="WR", targets=80, receptions=50, rec_yards=600, rec_tds=4,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16)
    # xFP = 80 × 1.5 + 0 × 0 + 10 × 2 = 140.
    assert compute_xfp(stat, avg) == pytest.approx(140.0)


def test_compute_xfp_returns_none_for_unsupported_position():
    """K and DST never have target/carry/rz_looks; we can't compute xFP for them."""
    avg = LeagueAverages(pts_per_target={}, pts_per_carry={}, pts_per_rz_look={})
    stat = _StubStat(position="K", targets=0, receptions=0, rec_yards=0, rec_tds=0,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=0, games_played=16)
    assert compute_xfp(stat, avg) is None


def test_per_position_sigmas_uses_sample_stdev():
    """σ_gap is sample stdev (ddof=1), per position."""
    gaps_by_position = {"WR": [10.0, -10.0, 0.0]}  # mean 0, sample stdev = sqrt(200/2) ≈ 10
    sigmas = compute_per_position_sigmas(gaps_by_position)
    assert sigmas["WR"] == pytest.approx(10.0)


def test_per_position_sigmas_handles_too_few_samples():
    """Position with fewer than 2 samples → sigma undefined → entry omitted."""
    gaps_by_position = {"QB": [5.0]}  # only one sample
    sigmas = compute_per_position_sigmas(gaps_by_position)
    assert "QB" not in sigmas


def test_opportunity_score_z_basic():
    """z = (FP − xFP) / σ. Hand-checked."""
    avg = LeagueAverages(
        pts_per_target={"WR": 1.5},
        pts_per_carry={"WR": 0.0},
        pts_per_rz_look={"WR": 2.0},
    )
    sigmas = {"WR": 10.0}
    settings = _ppr_settings()
    # Stat: 80 targets, 50 rec, 600 yds, 4 rec_tds, 10 rz_looks
    # FP (rec yds + rec): 50 + 60 = 110; TDs: 4 × 6 = 24; total FP = 134.
    # xFP = 80 × 1.5 + 0 + 10 × 2 = 140.
    # gap = 134 − 140 = −6. z = −6 / 10 = −0.6.
    stat = _StubStat(position="WR", targets=80, receptions=50, rec_yards=600, rec_tds=4,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16)
    z = compute_opportunity_score_z(stat, avg, sigmas, settings)
    assert z == pytest.approx(-0.6)


def test_opportunity_score_z_returns_none_for_low_games_played():
    avg = LeagueAverages(pts_per_target={"WR": 1.5}, pts_per_carry={"WR": 0.0}, pts_per_rz_look={"WR": 2.0})
    sigmas = {"WR": 10.0}
    settings = _ppr_settings()
    stat = _StubStat(position="WR", targets=20, receptions=10, rec_yards=120, rec_tds=1,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=2, games_played=5)
    assert compute_opportunity_score_z(stat, avg, sigmas, settings) is None


def test_opportunity_score_z_returns_none_for_zero_opportunity():
    """A player with 0 targets + 0 carries + 0 rz_looks is not in the regression distribution."""
    avg = LeagueAverages(pts_per_target={"WR": 1.5}, pts_per_carry={"WR": 0.0}, pts_per_rz_look={"WR": 2.0})
    sigmas = {"WR": 10.0}
    settings = _ppr_settings()
    stat = _StubStat(position="WR", targets=0, receptions=0, rec_yards=0, rec_tds=0,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=0, games_played=16)
    assert compute_opportunity_score_z(stat, avg, sigmas, settings) is None


def test_opportunity_score_z_returns_none_when_sigma_missing():
    """If the position lacks enough samples for σ, we can't compute z."""
    avg = LeagueAverages(pts_per_target={"WR": 1.5}, pts_per_carry={"WR": 0.0}, pts_per_rz_look={"WR": 2.0})
    sigmas = {}  # no WR σ
    settings = _ppr_settings()
    stat = _StubStat(position="WR", targets=80, receptions=50, rec_yards=600, rec_tds=4,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16)
    assert compute_opportunity_score_z(stat, avg, sigmas, settings) is None
