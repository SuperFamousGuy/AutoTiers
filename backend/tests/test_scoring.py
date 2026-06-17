import pytest
from app.engine.scoring import (
    ScoringFormat, LeagueType, LeagueSettings, PlayerStats,
    calculate_fantasy_points, blend_scores, _games_scale, PriorYearRamp,
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


# T6: covered by test_blend_all_missing_returns_zero above
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


# Issue #309 — prior-year weight conditioned on games played for injury-shortened seasons.


def test_blend_games_played_none_is_no_op():
    """Default (prior_year_games=None) must reproduce the pre-#309 behaviour exactly."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.0, weight_consensus=0.60)
    without_games = blend_scores(300.0, None, 340.0, s)
    with_none = blend_scores(300.0, None, 340.0, s, prior_year_games=None)
    assert with_none == without_games


def test_blend_full_season_unaffected():
    """A healthy full-season prior (>= full_season_games) is NOT discounted."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.0, weight_consensus=0.60)
    baseline = blend_scores(300.0, None, 340.0, s)
    full = blend_scores(300.0, None, 340.0, s, prior_year_games=17)
    assert full == baseline


def test_blend_injury_shortened_lifts_toward_projection():
    """A low-games prior is down-weighted, pulling the blend toward consensus."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    # McCaffrey scenario from issue #309: prior 42.3 over ~4 games, consensus 287.8.
    dragged = blend_scores(42.3, None, 287.8, s, prior_year_games=None)
    discounted = blend_scores(42.3, None, 287.8, s, prior_year_games=4, full_season_games=14)
    assert dragged == 214.15  # locks the pre-fix drag
    # Discount must lift the blend strictly toward projection-only (287.8)...
    assert dragged < discounted < 287.8
    # ...and land within ~1 tier (~30 pts here) of projection-only.
    assert (287.8 - discounted) < 35.0


def test_blend_zero_games_drops_prior_entirely():
    """Zero games => prior weight scaled to 0 => blend equals projection-only."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    result = blend_scores(42.3, None, 287.8, s, prior_year_games=0, full_season_games=14)
    assert result == 287.8


def test_blend_rookie_zero_prior_year_unaffected_by_games():
    """Rookie (prior_year_actual=None) is unaffected regardless of games value."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    baseline = blend_scores(None, None, 200.0, s)
    rookie = blend_scores(None, None, 200.0, s, prior_year_games=0, full_season_games=14)
    assert rookie == baseline == 200.0


def test_blend_games_discount_is_monotonic_in_games():
    """More games played => prior carries more weight => blend closer to prior."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    # prior (42.3) is far below consensus (287.8); more games => lower blend.
    b2 = blend_scores(42.3, None, 287.8, s, prior_year_games=2, full_season_games=14)
    b6 = blend_scores(42.3, None, 287.8, s, prior_year_games=6, full_season_games=14)
    b10 = blend_scores(42.3, None, 287.8, s, prior_year_games=10, full_season_games=14)
    assert b2 > b6 > b10


# Issue #315 — configurable games-played threshold + selectable ramp shape.
# Mathematician sign-off: full_season_games validated to [1, 17]; STEEP = base**2
# (convex, tighter discount than LINEAR on the open interval). Invariants below
# map 1:1 to the sign-off's enumerated assertions.


def test_games_scale_linear_endpoints_and_clamp():
    """scale(0)=0, scale(F)=1, scale(>F) clamps to 1, interior is the fraction."""
    assert _games_scale(0, 14) == 0.0
    assert _games_scale(14, 14) == 1.0
    assert _games_scale(17, 14) == 1.0  # 17-game season under a 14 threshold
    assert _games_scale(7, 14) == pytest.approx(0.5)


def test_games_scale_steep_is_convex_and_tighter_than_linear():
    """STEEP <= LINEAR strictly on 0 < g < F, equal at the endpoints."""
    for g in range(1, 14):
        assert _games_scale(g, 14, PriorYearRamp.STEEP) < _games_scale(g, 14, PriorYearRamp.LINEAR)
    assert _games_scale(0, 14, PriorYearRamp.STEEP) == 0.0
    assert _games_scale(14, 14, PriorYearRamp.STEEP) == 1.0
    assert _games_scale(4, 14, PriorYearRamp.STEEP) == pytest.approx((4 / 14) ** 2)


def test_games_scale_monotonic_non_decreasing_both_shapes():
    """More games never decreases the retained prior-year weight."""
    for shape in (PriorYearRamp.LINEAR, PriorYearRamp.STEEP):
        vals = [_games_scale(g, 14, shape) for g in range(0, 20)]
        assert all(later >= earlier for earlier, later in zip(vals, vals[1:]))


def test_games_scale_non_positive_threshold_disables_discount():
    """F <= 0 is a degenerate threshold -> no discount, games ignored, any shape."""
    assert _games_scale(0, 0) == 1.0
    assert _games_scale(3, -5) == 1.0
    assert _games_scale(3, 0, PriorYearRamp.STEEP) == 1.0


def test_games_scale_rejects_unknown_ramp_shape():
    """An unrecognized shape must raise, not silently fall back to linear."""
    with pytest.raises(ValueError):
        _games_scale(4, 14, "exponential")


def test_blend_configurable_threshold_changes_discount():
    """A smaller threshold treats the same games as more complete (less discount)."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    default_f = blend_scores(42.3, None, 287.8, s, prior_year_games=7, full_season_games=14)
    small_f = blend_scores(42.3, None, 287.8, s, prior_year_games=7, full_season_games=8)
    # Less discount keeps more of the (low) prior, pulling the blend lower.
    assert small_f < default_f
    assert small_f == pytest.approx(220.85, abs=0.02)  # F=8, g=7 -> scale 0.875
    # games >= threshold => full credit => identical to the no-games baseline.
    full = blend_scores(42.3, None, 287.8, s, prior_year_games=8, full_season_games=8)
    assert full == blend_scores(42.3, None, 287.8, s)


def test_blend_ramp_none_games_is_shape_invariant():
    """prior_year_games=None => scale 1.0 regardless of ramp_shape (backward compat)."""
    s = _settings(weight_prior_year=0.40, weight_espn=0.0, weight_consensus=0.60)
    baseline = blend_scores(300.0, None, 340.0, s)
    steep_none = blend_scores(300.0, None, 340.0, s, prior_year_games=None, ramp_shape=PriorYearRamp.STEEP)
    assert steep_none == baseline


def test_blend_mccaffrey_linear_vs_steep_pinned():
    """Mathematician-pinned numbers for the McCaffrey case (g=4, F=14)."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    linear = blend_scores(42.3, None, 287.8, s, prior_year_games=4, full_season_games=14,
                          ramp_shape=PriorYearRamp.LINEAR)
    steep = blend_scores(42.3, None, 287.8, s, prior_year_games=4, full_season_games=14,
                         ramp_shape=PriorYearRamp.STEEP)
    assert linear == pytest.approx(261.02, abs=0.02)
    assert steep == pytest.approx(279.50, abs=0.02)
    # STEEP applies a lighter prior-year pull -> closer to projection-only (287.8).
    assert linear < steep < 287.8


def test_blend_ramp_shape_accepts_raw_string():
    """The enum and its raw string value must produce identical results."""
    s = _settings(weight_prior_year=0.30, weight_espn=0.0, weight_consensus=0.70)
    enum_call = blend_scores(42.3, None, 287.8, s, prior_year_games=4, ramp_shape=PriorYearRamp.STEEP)
    str_call = blend_scores(42.3, None, 287.8, s, prior_year_games=4, ramp_shape="steep")
    assert enum_call == str_call


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
