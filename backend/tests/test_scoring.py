import pytest
from app.engine.scoring import (
    ScoringFormat, LeagueType, LeagueSettings, PlayerStats,
    calculate_fantasy_points, blend_scores,
)


def _settings(**overrides) -> LeagueSettings:
    defaults = dict(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.40,
        weight_espn=0.30,
        weight_consensus=0.30,
    )
    defaults.update(overrides)
    return LeagueSettings(**defaults)


def _stats(**overrides) -> PlayerStats:
    defaults = dict(
        targets=0, receptions=0, rec_yards=0.0, rec_tds=0,
        rush_att=0, rush_yards=0.0, rush_tds=0,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
        games_played=17,
    )
    defaults.update(overrides)
    return PlayerStats(**defaults)


def test_ppr_receptions_score_one_point_each():
    stats = _stats(receptions=8, rec_yards=100.0, rec_tds=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.PPR), position="WR")
    # 8*1 + 100*0.1 + 1*6 = 8 + 10 + 6 = 24
    assert pts == pytest.approx(24.0)


def test_standard_no_reception_points():
    stats = _stats(receptions=8, rec_yards=100.0, rec_tds=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.STANDARD), position="WR")
    # 100*0.1 + 1*6 = 16
    assert pts == pytest.approx(16.0)


def test_half_ppr_receptions_score_half_point():
    stats = _stats(receptions=8)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.HALF_PPR), position="WR")
    assert pts == pytest.approx(4.0)


def test_te_premium_gives_te_extra_half_point_per_reception():
    stats = _stats(receptions=6, rec_yards=60.0)
    te_pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.TE_PREMIUM), position="TE")
    wr_pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.TE_PREMIUM), position="WR")
    # TE gets 1.5/rec, WR gets 1.0/rec; difference = 6 * 0.5 = 3
    assert te_pts == pytest.approx(wr_pts + 3.0)


def test_rushing_yards_and_td():
    stats = _stats(rush_att=20, rush_yards=105.0, rush_tds=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.STANDARD, bonus_100yd_rushing=True), position="RB")
    # 105*0.1 + 1*6 + 3 bonus = 10.5 + 6 + 3 = 19.5
    assert pts == pytest.approx(19.5)


def test_100yd_bonus_not_awarded_under_threshold():
    stats = _stats(rush_yards=99.0)
    pts = calculate_fantasy_points(stats, _settings(bonus_100yd_rushing=True), position="RB")
    assert pts == pytest.approx(9.9)


def test_six_point_passing_tds():
    stats = _stats(pass_yards=300.0, pass_tds=3)
    pts = calculate_fantasy_points(stats, _settings(qb_td_points=6.0), position="QB")
    # 300*0.04 + 3*6 = 12 + 18 = 30
    assert pts == pytest.approx(30.0)


def test_interception_penalty():
    stats = _stats(interceptions=2)
    pts = calculate_fantasy_points(stats, _settings(), position="QB")
    assert pts == pytest.approx(-4.0)


def test_blend_all_sources():
    s = _settings(weight_prior_year=0.4, weight_espn=0.3, weight_consensus=0.3)
    result = blend_scores(prior_year_actual=300.0, espn_projection=350.0, consensus_projection=340.0, settings=s)
    expected = 300.0 * 0.4 + 350.0 * 0.3 + 340.0 * 0.3
    assert result == pytest.approx(expected)


def test_blend_redistributes_weight_when_source_missing():
    s = _settings(weight_prior_year=0.4, weight_espn=0.3, weight_consensus=0.3)
    result = blend_scores(prior_year_actual=None, espn_projection=300.0, consensus_projection=280.0, settings=s)
    # espn + consensus weights = 0.6; redistribute to 0.3/0.6 and 0.3/0.6
    expected = (300.0 * 0.3 + 280.0 * 0.3) / 0.6
    assert result == pytest.approx(expected)


def test_blend_all_missing_returns_zero():
    result = blend_scores(None, None, None, settings=_settings())
    assert result == 0.0
