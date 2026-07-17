import pytest
from app.engine.scoring import (
    ScoringFormat, LeagueType, LeagueSettings, PlayerStats,
    calculate_fantasy_points, blend_scores, _games_scale, PriorYearRamp,
    _score_turnovers_and_conversions, _score_first_downs,
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


# --- Fumbles lost & 2-point conversions (#663) -----------------------------

def test_fumbles_lost_penalized_two_points_each():
    """ESPN/NFL.com/FantasyPros consensus default: -2 per fumble lost."""
    stats = _stats(rush_att=20, rush_yards=100.0, rush_tds=1, fumbles_lost=2)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.STANDARD), position="RB")
    # 100*0.1 + 1*6 + 2*(-2) = 10 + 6 - 4 = 12
    assert pts == pytest.approx(12.0)


def test_two_point_conversions_award_two_points_each():
    """Consensus default: +2 per 2-pt conversion, any play type, any position."""
    stats = _stats(receptions=5, rec_yards=40.0, two_pt_conversions=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.PPR), position="WR")
    # 5*1 + 40*0.1 + 1*2 = 5 + 4 + 2 = 11
    assert pts == pytest.approx(11.0)


def test_fumbles_and_two_pt_combined_matches_espn_defaults():
    """A QB who fumbles once and passes for a 2-pt conversion: -2 + 2 net zero swing."""
    stats = _stats(pass_yards=300.0, pass_tds=2, fumbles_lost=1, two_pt_conversions=1)
    pts = calculate_fantasy_points(stats, _settings(qb_td_points=4.0), position="QB")
    # 300*0.04 + 2*4 + 1*(-2) + 1*2 = 12 + 8 - 2 + 2 = 20
    assert pts == pytest.approx(20.0)


def test_fumbles_and_two_pt_default_to_zero_are_no_op():
    """Backward-compat: with both counts defaulting to 0, output is unchanged."""
    stats = _stats(receptions=8, rec_yards=100.0, rec_tds=1)
    with_defaults = calculate_fantasy_points(stats, _settings(), position="WR")
    explicit_zero = calculate_fantasy_points(
        _stats(receptions=8, rec_yards=100.0, rec_tds=1, fumbles_lost=0, two_pt_conversions=0),
        _settings(), position="WR",
    )
    assert with_defaults == pytest.approx(24.0)
    assert with_defaults == explicit_zero


def test_a_fumbler_scores_less_than_an_otherwise_identical_player():
    """Known-answer contrast: the only difference is the fumble → exactly -2."""
    clean = _stats(rush_att=15, rush_yards=90.0, rush_tds=1)
    fumbler = _stats(rush_att=15, rush_yards=90.0, rush_tds=1, fumbles_lost=1)
    settings = _settings(scoring_format=ScoringFormat.STANDARD)
    delta = calculate_fantasy_points(fumbler, settings, position="RB") - \
        calculate_fantasy_points(clean, settings, position="RB")
    assert delta == pytest.approx(-2.0)


def test_turnover_settings_are_configurable():
    """The -2/+2 defaults are overridable via LeagueSettings, not hardcoded."""
    stats = _stats(fumbles_lost=1, two_pt_conversions=1)
    settings = _settings(fumble_lost_points=-1.0, two_pt_points=3.0)
    assert _score_turnovers_and_conversions(stats, settings) == pytest.approx(2.0)
    assert calculate_fantasy_points(stats, settings) == pytest.approx(2.0)


# --- First-down bonus (#771) -----------------------------------------------

def test_first_down_bonus_awards_points_per_first_down_when_enabled():
    """Enabled bonus: default 1.0 per rushing/receiving first down, additive."""
    stats = _stats(rush_att=20, rush_yards=100.0, rush_tds=1, first_down_rush=6, first_down_rec=2)
    pts = calculate_fantasy_points(
        stats, _settings(scoring_format=ScoringFormat.STANDARD, bonus_first_downs=True), position="RB"
    )
    # 100*0.1 + 1*6 + (6+2)*1.0 = 10 + 6 + 8 = 24
    assert pts == pytest.approx(24.0)


def test_first_down_bonus_disabled_by_default_is_no_op():
    """Regression: with the bonus off (default), first downs never affect score."""
    with_fds = _stats(receptions=8, rec_yards=100.0, rec_tds=1, first_down_rush=3, first_down_rec=5)
    without = _stats(receptions=8, rec_yards=100.0, rec_tds=1)
    settings = _settings()  # bonus_first_downs=False by default
    scored_with = calculate_fantasy_points(with_fds, settings, position="WR")
    scored_without = calculate_fantasy_points(without, settings, position="WR")
    assert scored_with == pytest.approx(24.0)
    assert scored_with == scored_without


def test_first_down_counts_default_to_zero_are_no_op_even_when_enabled():
    """A player with zero first downs scores identically whether or not the
    bonus is enabled — the additive term is exactly zero."""
    stats = _stats(receptions=8, rec_yards=100.0, rec_tds=1)  # first_down_* default to 0
    off = calculate_fantasy_points(stats, _settings(bonus_first_downs=False), position="WR")
    on = calculate_fantasy_points(stats, _settings(bonus_first_downs=True), position="WR")
    assert off == pytest.approx(24.0)
    assert off == on


def test_first_down_bonus_gated_by_setting():
    """Same player, same first downs — the bonus applies only when enabled."""
    stats = _stats(receptions=8, rec_yards=100.0, first_down_rec=4)
    delta = calculate_fantasy_points(stats, _settings(bonus_first_downs=True), position="WR") - \
        calculate_fantasy_points(stats, _settings(bonus_first_downs=False), position="WR")
    assert delta == pytest.approx(4.0)  # 4 first downs * 1.0


def test_first_down_points_are_configurable():
    """The per-first-down value is overridable via LeagueSettings, not hardcoded."""
    stats = _stats(first_down_rush=3, first_down_rec=2)
    settings = _settings(bonus_first_downs=True, first_down_points=0.5)
    assert _score_first_downs(stats, settings) == pytest.approx(2.5)  # 5 * 0.5
    assert calculate_fantasy_points(stats, settings) == pytest.approx(2.5)


def test_score_first_downs_helper_returns_zero_when_disabled():
    """Direct helper check: disabled → 0.0 regardless of first-down counts."""
    stats = _stats(first_down_rush=10, first_down_rec=10)
    assert _score_first_downs(stats, _settings(bonus_first_downs=False)) == 0.0


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


# ---------------------------------------------------------------------------
# TE Premium (#525)
# ---------------------------------------------------------------------------


def test_te_premium_defaults_to_zero_on_league_settings():
    """The new field is opt-in: an existing LeagueSettings(...) construction that
    omits te_premium_bonus keeps the default 0.0, so nothing changes for it."""
    assert _ppr_settings().te_premium_bonus == 0.0


def test_te_premium_default_zero_byte_identical_for_te():
    """Acceptance: default 0.0 produces byte-identical output to current behavior,
    even for a TE. This is the regression guard on the whole feature."""
    s = _stats(receptions=90, rec_yards=1100.0, rec_tds=10)
    settings = _settings(scoring_format=ScoringFormat.PPR)  # te_premium_bonus defaults to 0.0
    # 90 rec + 110 rec-yds + 60 rec-TDs = 260, identical whether or not position is TE.
    assert calculate_fantasy_points(s, settings, position="TE") == 260.0
    assert calculate_fantasy_points(s, settings, position="WR") == 260.0


def test_te_premium_adds_to_te_receptions_on_top_of_ppr():
    """A 1.0 TE premium adds one point per TE reception, on top of the PPR value."""
    s = _stats(receptions=90, rec_yards=1100.0, rec_tds=10)
    settings = _settings(scoring_format=ScoringFormat.PPR, te_premium_bonus=1.0)
    # base PPR = 260; TE premium adds 90 * 1.0 = 90 -> 350
    assert calculate_fantasy_points(s, settings, position="TE") == pytest.approx(350.0)


def test_te_premium_is_case_insensitive():
    """Position matching must not depend on casing of the incoming position string."""
    s = _stats(receptions=10)
    settings = _settings(scoring_format=ScoringFormat.PPR, te_premium_bonus=0.5)
    # 10 rec * (1.0 PPR + 0.5 TEP) = 15
    assert calculate_fantasy_points(s, settings, position="te") == pytest.approx(15.0)


def test_te_premium_not_applied_to_non_te_positions():
    """WR/RB receptions must be unaffected by te_premium_bonus."""
    s = _stats(receptions=90, rec_yards=1100.0)
    settings = _settings(scoring_format=ScoringFormat.PPR, te_premium_bonus=1.5)
    # base PPR only: 90 + 110 = 200, no premium for a WR
    assert calculate_fantasy_points(s, settings, position="WR") == pytest.approx(200.0)


def test_te_premium_additive_on_standard_and_half_ppr():
    """TE premium is additive on top of whatever the base reception value is,
    including standard (0.0 base) and half-PPR (0.5 base)."""
    s = _stats(receptions=8)
    # standard: 0.0 base + 1.0 TEP per rec = 8
    std = _settings(scoring_format=ScoringFormat.STANDARD, te_premium_bonus=1.0)
    assert calculate_fantasy_points(s, std, position="TE") == pytest.approx(8.0)
    # half-ppr: 0.5 base + 1.0 TEP per rec = 12
    half = _settings(scoring_format=ScoringFormat.HALF_PPR, te_premium_bonus=1.0)
    assert calculate_fantasy_points(s, half, position="TE") == pytest.approx(12.0)


def test_score_receiving_te_premium_direct():
    """_score_receiving gates the premium on position and never touches TDs."""
    from app.engine.scoring import _score_receiving
    s = _empty_stats()
    s.receptions = 50
    s.rec_yards = 600.0
    s.rec_tds = 5
    settings = _settings(scoring_format=ScoringFormat.PPR, te_premium_bonus=0.5)
    # 50 * (1.0 + 0.5) + 60 yds = 135; TDs excluded
    assert _score_receiving(s, settings, "TE") == pytest.approx(135.0)
    # WR: no premium -> 50 + 60 = 110
    assert _score_receiving(s, settings, "WR") == pytest.approx(110.0)
    # default position arg (pre-#525 callers) -> no premium
    assert _score_receiving(s, settings) == pytest.approx(110.0)
