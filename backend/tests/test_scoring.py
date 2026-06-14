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


def test_blend_renormalizes_missing_sources():
    """Missing sources have their weight redistributed — active sources share the full weight budget."""
    settings = LeagueSettings(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.20,
        weight_espn=0.0,
        weight_consensus=0.80,
    )
    # Only prior_year available (espn disabled via weight=0, consensus=None).
    # Renorm: active = {(100.0, 0.20)}; W_active = 0.20; result = 100 * 0.20 / 0.20 = 100.0.
    result = blend_scores(
        prior_year_actual=100.0,
        espn_projection=None,
        consensus_projection=None,
        settings=settings,
    )
    assert result == 100.0


# --- Renormalization test suite T2-T10 (design doc 2026-06-14) ---

def test_blend_t2_espn_missing_weights_redistributed():
    """T2: ESPN missing — weight redistributed over prior + consensus."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
    result = blend_scores(300.0, None, 340.0, s)
    # (300*0.40 + 340*0.30) / 0.70 = 222 / 0.70 = 317.142...
    assert result == pytest.approx(317.14, abs=0.01)


def test_blend_t3_only_prior_year_returns_full_value():
    """T3: Only prior_year present — full prior-year value returned (not penalized at 40%)."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
    result = blend_scores(300.0, None, None, s)
    # 300 * (0.40 / 0.40) = 300.0
    assert result == pytest.approx(300.0)


def test_blend_t4_only_consensus_rookie_scenario():
    """T4: Only consensus present (rookie) — full consensus value returned."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
    result = blend_scores(None, None, 200.0, s)
    # 200 * (0.30 / 0.30) = 200.0
    assert result == pytest.approx(200.0)


def test_blend_t5_only_espn_present():
    """T5: Only ESPN present — full ESPN value returned."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
    result = blend_scores(None, 350.0, None, s)
    # 350 * (0.30 / 0.30) = 350.0
    assert result == pytest.approx(350.0)


def test_blend_t7_espn_weight_zero_data_exists_excluded():
    """T7: weight_espn=0.0 — ESPN data present but excluded from active set."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.0, weight_consensus=0.60)
    result = blend_scores(300.0, 350.0, 340.0, s)
    # ESPN excluded (w=0); W_active = 0.40 + 0.60 = 1.0
    # 300*(0.40/1.0) + 340*(0.60/1.0) = 120 + 204 = 324.0
    assert result == pytest.approx(324.0)


def test_blend_t8_all_weights_zero_returns_zero():
    """T8: All weights zero — must not crash; returns 0.0."""
    settings = LeagueSettings(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.0,
        weight_espn=0.0,
        weight_consensus=0.0,
    )
    result = blend_scores(300.0, 350.0, 340.0, settings)
    assert result == 0.0


def test_blend_t9_negative_prior_year_correctly_weighted():
    """T9: Negative prior-year score drags blend down without special-casing."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
    result = blend_scores(-10.0, None, 280.0, s)
    # (-10*0.40 + 280*0.30) / 0.70 = (-4 + 84) / 0.70 = 80 / 0.70 = 114.285...
    assert result == pytest.approx(114.29, abs=0.01)


def test_blend_t10_prior_year_zero_not_treated_as_missing():
    """T10: prior_year_actual=0.0 is not None — player who scored zero is not missing."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
    result = blend_scores(0.0, None, 200.0, s)
    # active = {(0.0, 0.40), (200.0, 0.30)}; W_active=0.70
    # (0.0*0.40 + 200.0*0.30) / 0.70 = 60 / 0.70 = 85.714...
    assert result == pytest.approx(85.71, abs=0.01)
    # Must NOT equal blend_scores(None, None, 200.0, s) = 200.0
    assert result != pytest.approx(200.0)


def test_blend_all_missing_returns_zero():
    result = blend_scores(None, None, None, settings=_settings())
    assert result == 0.0


# Step 1.1: New tests for factored helpers


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


def _empty_stats() -> PlayerStats:
    return PlayerStats(
        targets=0, receptions=0, rec_yards=0.0, rec_tds=0,
        rush_att=0, rush_yards=0.0, rush_tds=0,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
        games_played=1,
    )


def test_score_receiving_excludes_tds():
    from app.engine.scoring import _score_receiving
    s = _empty_stats()
    s.receptions = 50
    s.rec_yards = 600.0
    s.rec_tds = 5
    # Expect: 50 PPR pts + 60 yards pts; TDs excluded here.
    assert _score_receiving(s, _ppr_settings()) == 110.0


def test_score_rushing_excludes_tds():
    from app.engine.scoring import _score_rushing
    s = _empty_stats()
    s.rush_att = 200
    s.rush_yards = 1000.0
    s.rush_tds = 8
    # Expect: 100 yards pts; TDs excluded; carries don't score directly.
    assert _score_rushing(s, _ppr_settings()) == 100.0


def test_score_tds_only_sums_rec_and_rush():
    from app.engine.scoring import _score_tds_only
    s = _empty_stats()
    s.rec_tds = 4
    s.rush_tds = 6
    # Expect: 10 TDs × 6 = 60.
    assert _score_tds_only(s, _ppr_settings()) == 60.0


def test_calculate_fantasy_points_unchanged():
    """Regression: factoring must not change calculate_fantasy_points output."""
    s = _empty_stats()
    s.receptions = 50
    s.rec_yards = 600.0
    s.rec_tds = 5
    s.rush_att = 200
    s.rush_yards = 1000.0
    s.rush_tds = 8
    # 50 + 60 (rec yds + rec) + 30 (5 rec TDs) + 100 (rush yds) + 48 (8 rush TDs) = 288
    assert calculate_fantasy_points(s, _ppr_settings(), position="RB") == 288.0
