"""Tests for the Opportunity Over-Producer / Under-Producer rules.

Mirrors the style of test_rules.py's TD Regression coverage (lines
~193-203). We make a PlayerContext directly and run apply_rules.
"""
import pytest
from app.engine.rules import (
    PlayerContext, apply_rules, EffectType, RuleCondition, RuleEffect, Rule,
)
from app.engine.builtin_rules import BUILTIN_RULES


def make_ctx(**overrides) -> PlayerContext:
    """Construct a minimal PlayerContext with sane defaults for these tests."""
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
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def _over_producer_rule() -> Rule:
    """Locate the over-producer rule from BUILTIN_RULES."""
    return next(r for r in BUILTIN_RULES if r.name == "Opportunity Over-Producer")


def _under_producer_rule() -> Rule:
    return next(r for r in BUILTIN_RULES if r.name == "Opportunity Under-Producer")


def test_over_producer_fires_at_threshold():
    rule = _over_producer_rule()
    ctx = make_ctx(opportunity_score_z=1.5)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    # z = 1.5 → fires → -8%. 180 × 0.92 = 165.6
    assert result.adjusted_score == pytest.approx(165.6, abs=0.01)
    assert "Opportunity Over-Producer" in result.rules_applied


def test_over_producer_does_not_fire_below_threshold():
    rule = _over_producer_rule()
    ctx = make_ctx(opportunity_score_z=1.49)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Over-Producer" not in result.rules_applied


def test_over_producer_does_not_fire_when_z_is_none():
    rule = _over_producer_rule()
    ctx = make_ctx(opportunity_score_z=None)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Over-Producer" not in result.rules_applied


def test_under_producer_fires_at_negative_threshold():
    rule = _under_producer_rule()
    ctx = make_ctx(opportunity_score_z=-1.5)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    # z = -1.5 → fires → +8%. 180 × 1.08 = 194.4
    assert result.adjusted_score == pytest.approx(194.4, abs=0.01)
    assert "Opportunity Under-Producer" in result.rules_applied


def test_under_producer_does_not_fire_above_negative_threshold():
    rule = _under_producer_rule()
    ctx = make_ctx(opportunity_score_z=-1.49)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Under-Producer" not in result.rules_applied


def test_neither_rule_fires_at_zero():
    over = _over_producer_rule()
    under = _under_producer_rule()
    ctx = make_ctx(opportunity_score_z=0.0)
    result = apply_rules(ctx.projected_score, ctx, [over, under])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Over-Producer" not in result.rules_applied
    assert "Opportunity Under-Producer" not in result.rules_applied


def test_only_one_direction_fires_at_a_time():
    """The two rules are mutually exclusive by threshold construction."""
    over = _over_producer_rule()
    under = _under_producer_rule()
    # Strongly positive z
    ctx_pos = make_ctx(opportunity_score_z=2.5)
    result_pos = apply_rules(ctx_pos.projected_score, ctx_pos, [over, under])
    assert "Opportunity Over-Producer" in result_pos.rules_applied
    assert "Opportunity Under-Producer" not in result_pos.rules_applied
    # Strongly negative z
    ctx_neg = make_ctx(opportunity_score_z=-2.5)
    result_neg = apply_rules(ctx_neg.projected_score, ctx_neg, [over, under])
    assert "Opportunity Under-Producer" in result_neg.rules_applied
    assert "Opportunity Over-Producer" not in result_neg.rules_applied
