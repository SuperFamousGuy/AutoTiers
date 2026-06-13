"""Tests for the new Favorites builtin rule."""
import pytest
from app.engine.rules import PlayerContext, apply_rules, Rule
from app.engine.builtin_rules import BUILTIN_RULES


def make_ctx(**overrides) -> PlayerContext:
    defaults = dict(
        player_id="p", position="WR", age=25, snap_pct=0.7,
        carry_share=None, target_share=0.20, games_played=16,
        years_exp=4, adp=50.0, projected_score=180.0,
        new_team=False, new_coach=False,
        actual_tds=None, expected_tds=None, actual_tds_above_expected=None,
        red_zone_looks=None, is_over_the_hill=None,
        projection_unavailable=None, prior_touches=None,
        injured_two_years_ago=None, bad_offense_team=None,
        above_market_contract=None, opportunity_score_z=None,
        is_favorite=None,
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def _favorites_rule() -> Rule:
    import dataclasses
    return dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Favorites"), enabled=True)


def test_favorites_rule_fires_when_is_favorite_true():
    rule = _favorites_rule()
    ctx = make_ctx(is_favorite=True)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    # 180 × 1.05 = 189
    assert result.adjusted_score == pytest.approx(189.0, abs=0.01)
    assert "Favorites" in result.rules_applied


def test_favorites_rule_does_not_fire_when_is_favorite_false():
    rule = _favorites_rule()
    ctx = make_ctx(is_favorite=False)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Favorites" not in result.rules_applied


def test_favorites_rule_does_not_fire_when_is_favorite_is_none():
    """None must mean 'not evaluated' — silent no-op for anon users."""
    rule = _favorites_rule()
    ctx = make_ctx(is_favorite=None)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Favorites" not in result.rules_applied
