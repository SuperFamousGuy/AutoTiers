import pytest
from app.engine.rules import (
    Rule, RuleCondition, RuleEffect, EffectType, PlayerContext,
    RuleResult, apply_rules,
)
from app.engine.builtin_rules import BUILTIN_RULES


def _ctx(**overrides) -> PlayerContext:
    defaults = dict(
        player_id="p1", position="RB", age=25,
        snap_pct=0.70, carry_share=0.65, target_share=0.15,
        games_played=16, years_exp=3, adp=5.0,
        projected_score=200.0, new_team=False, new_coach=False,
        actual_tds=8, expected_tds=7.0,
        actual_tds_above_expected=None, red_zone_looks=None,
        is_over_the_hill=None, projection_unavailable=None,
        prior_touches=None, injured_two_years_ago=None,
        bad_offense_team=None, above_market_contract=None,
        opportunity_score_z=None,
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def make_ctx(**overrides) -> PlayerContext:
    defaults = dict(
        player_id="p1", position="WR", age=27,
        snap_pct=None, carry_share=None, target_share=None,
        games_played=17, years_exp=4, adp=None,
        projected_score=100.0, new_team=False, new_coach=False,
        actual_tds=None, expected_tds=None, actual_tds_above_expected=None,
        red_zone_looks=None, is_over_the_hill=None, projection_unavailable=None,
        prior_touches=None, injured_two_years_ago=None,
        bad_offense_team=None, above_market_contract=None,
        opportunity_score_z=None,
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def _rule(field, operator, value, effect_type, effect_value, weight=1.0, enabled=True) -> Rule:
    return Rule(
        name=f"{field}_{operator}_{value}",
        conditions=[RuleCondition(field=field, operator=operator, value=value)],
        effect=RuleEffect(type=effect_type, value=effect_value),
        enabled=enabled,
        weight=weight,
    )


def test_multiplier_applied_when_condition_met():
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92)
    result = apply_rules(200.0, _ctx(age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0 * 0.92)
    assert rule.name in result.rules_applied


def test_condition_not_met_skips_rule():
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92)
    result = apply_rules(200.0, _ctx(age=25), [rule])
    assert result.adjusted_score == pytest.approx(200.0)
    assert result.rules_applied == []


def test_disabled_rule_is_skipped():
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92, enabled=False)
    result = apply_rules(200.0, _ctx(age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0)


def test_flat_bonus():
    rule = _rule("target_share", ">=", 0.25, EffectType.FLAT_BONUS, 20.0)
    result = apply_rules(200.0, _ctx(target_share=0.28), [rule])
    assert result.adjusted_score == pytest.approx(220.0)


def test_flat_penalty():
    rule = _rule("carry_share", "<", 0.50, EffectType.FLAT_PENALTY, 30.0)
    result = apply_rules(200.0, _ctx(carry_share=0.40), [rule])
    assert result.adjusted_score == pytest.approx(170.0)


def test_flag_does_not_change_score():
    rule = _rule("new_team", "==", True, EffectType.FLAG, "New Team")
    result = apply_rules(200.0, _ctx(new_team=True), [rule])
    assert result.adjusted_score == pytest.approx(200.0)
    assert "New Team" in result.flags


def test_weight_scales_multiplier_distance():
    # weight=2.0 doubles the distance from 1.0: 0.92 → distance=-0.08 → actual=1.0+(-0.08*2.0)=0.84
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92, weight=2.0)
    result = apply_rules(200.0, _ctx(age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0 * 0.84)


def test_weight_scales_flat_bonus():
    rule = _rule("target_share", ">=", 0.25, EffectType.FLAT_BONUS, 20.0, weight=2.0)
    result = apply_rules(200.0, _ctx(target_share=0.28), [rule])
    assert result.adjusted_score == pytest.approx(240.0)


def test_multiple_rules_compound_in_order():
    rule1 = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92)
    rule2 = _rule("carry_share", "<", 0.50, EffectType.FLAT_PENALTY, 30.0)
    result = apply_rules(200.0, _ctx(age=30, carry_share=0.40), [rule1, rule2])
    # 200 * 0.92 = 184; 184 - 30 = 154
    assert result.adjusted_score == pytest.approx(154.0)
    assert len(result.rules_applied) == 2


def test_null_field_causes_condition_to_be_false():
    rule = _rule("snap_pct", "<", 0.50, EffectType.MULTIPLIER, 0.90)
    result = apply_rules(200.0, _ctx(snap_pct=None), [rule])
    assert result.adjusted_score == pytest.approx(200.0)


def test_multi_condition_rule_requires_all_conditions():
    rule = Rule(
        name="rb_age",
        conditions=[
            RuleCondition(field="position", operator="==", value="RB"),
            RuleCondition(field="age", operator=">=", value=28),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.92),
        enabled=True,
        weight=1.0,
    )
    # Both conditions met
    result = apply_rules(200.0, _ctx(position="RB", age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0 * 0.92)
    # Only one condition met — rule skipped
    result2 = apply_rules(200.0, _ctx(position="WR", age=30), [rule])
    assert result2.adjusted_score == pytest.approx(200.0)


def test_builtin_rules_is_nonempty_list_of_rules():
    assert isinstance(BUILTIN_RULES, list)
    assert len(BUILTIN_RULES) >= 10
    for rule in BUILTIN_RULES:
        assert isinstance(rule, Rule)
        assert rule.name
        assert rule.conditions


def test_builtin_rules_count_is_20():
    """Adding Opportunity Over-Producer and Under-Producer rules (was 18)."""
    assert len(BUILTIN_RULES) == 20


def test_all_builtin_rules_have_descriptions():
    for rule in BUILTIN_RULES:
        assert rule.description, f"Rule '{rule.name}' is missing a description"
        assert len(rule.description) > 20, f"Rule '{rule.name}' description is suspiciously short"


def test_projection_unavailable_halves_score():
    rule = next(r for r in BUILTIN_RULES if r.name == "Projection Unavailable")
    ctx = make_ctx(projection_unavailable=True)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 50.0
    assert "Projection Unavailable" in result.rules_applied


def test_projection_unavailable_skipped_when_false():
    rule = next(r for r in BUILTIN_RULES if r.name == "Projection Unavailable")
    ctx = make_ctx(projection_unavailable=False)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "Projection Unavailable" not in result.rules_applied


def test_over_the_hill_fires_when_age_at_threshold():
    rule = next(r for r in BUILTIN_RULES if r.name == "Over the Hill")
    ctx = make_ctx(is_over_the_hill=True)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0  # penalty applied
    assert "Over the Hill" in result.rules_applied


def test_over_the_hill_does_not_fire_when_false():
    rule = next(r for r in BUILTIN_RULES if r.name == "Over the Hill")
    ctx = make_ctx(is_over_the_hill=False)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "Over the Hill" not in result.rules_applied


def test_over_the_hill_skipped_when_none():
    """K/DST/missing age have is_over_the_hill=None — rule shouldn't fire."""
    rule = next(r for r in BUILTIN_RULES if r.name == "Over the Hill")
    ctx = make_ctx(is_over_the_hill=None)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0


def test_td_regression_positive_fires_above_threshold():
    rule = next(r for r in BUILTIN_RULES if r.name == "TD Regression")
    ctx = make_ctx(actual_tds_above_expected=4.0)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0  # multiplier < 1.0


def test_td_regression_positive_does_not_fire_below_threshold():
    rule = next(r for r in BUILTIN_RULES if r.name == "TD Regression")
    ctx = make_ctx(actual_tds_above_expected=2.0)  # below threshold of 3.0
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "TD Regression" not in result.rules_applied


def test_red_zone_premium_fires_above_25():
    rule = next(r for r in BUILTIN_RULES if r.name == "Red Zone Usage Premium")
    ctx = make_ctx(red_zone_looks=30)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score > 100.0


def test_red_zone_premium_skipped_when_none():
    rule = next(r for r in BUILTIN_RULES if r.name == "Red Zone Usage Premium")
    ctx = make_ctx(red_zone_looks=None)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "Red Zone Usage Premium" not in result.rules_applied


def test_apply_rules_tracks_per_rule_applications():
    """RuleResult.applications has before/after/delta per rule."""
    rule = Rule(
        name="Test Bonus",
        conditions=[RuleCondition(field="position", operator="==", value="WR")],
        effect=RuleEffect(type=EffectType.FLAT_BONUS, value=20.0),
    )
    ctx = make_ctx(position="WR", projected_score=100.0)
    result = apply_rules(100.0, ctx, [rule])

    assert len(result.applications) == 1
    app = result.applications[0]
    assert app.name == "Test Bonus"
    assert app.before_score == 100.0
    assert app.after_score == 120.0
    assert app.delta == 20.0


def test_370_touches_rule_fires_on_rb_with_high_touches():
    rule = next(r for r in BUILTIN_RULES if r.name == "370 Touches")
    ctx = _ctx(prior_touches=375)
    result = apply_rules(200.0, ctx, [rule])
    assert "370 Touches" in result.rules_applied
    assert result.adjusted_score == 180.0  # 200 * 0.90


def test_370_touches_rule_does_not_fire_under_threshold():
    rule = next(r for r in BUILTIN_RULES if r.name == "370 Touches")
    ctx = _ctx(prior_touches=369)
    result = apply_rules(200.0, ctx, [rule])
    assert "370 Touches" not in result.rules_applied


def test_player_context_accepts_prior_touches():
    ctx = _ctx(prior_touches=385)
    assert ctx.prior_touches == 385


def test_player_context_accepts_injured_two_years_ago():
    ctx = _ctx(position="WR", injured_two_years_ago=True)
    assert ctx.injured_two_years_ago is True


def test_player_context_accepts_bad_offense_team():
    ctx = _ctx(position="WR", bad_offense_team=True)
    assert ctx.bad_offense_team is True


def test_player_context_accepts_above_market_contract():
    ctx = _ctx(position="WR", above_market_contract=True)
    assert ctx.above_market_contract is True


def test_year_after_rule_fires_on_wr_injured_two_seasons_ago():
    rule = next(r for r in BUILTIN_RULES if r.name == "Year After the Year After")
    ctx = _ctx(position="WR", injured_two_years_ago=True)
    result = apply_rules(200.0, ctx, [rule])
    assert "Year After the Year After" in result.rules_applied
    assert result.adjusted_score == 220.0  # 200 * 1.10


def test_year_after_rule_does_not_fire_when_false():
    rule = next(r for r in BUILTIN_RULES if r.name == "Year After the Year After")
    ctx = _ctx(position="WR", injured_two_years_ago=False)
    result = apply_rules(200.0, ctx, [rule])
    assert "Year After the Year After" not in result.rules_applied


def test_bad_offense_rule_fires():
    rule = next(r for r in BUILTIN_RULES if r.name == "Bad Offense")
    ctx = _ctx(position="WR", bad_offense_team=True)
    result = apply_rules(200.0, ctx, [rule])
    assert "Bad Offense" in result.rules_applied
    assert result.adjusted_score == 186.0  # 200 * 0.93


def test_bad_offense_rule_does_not_fire_when_none():
    rule = next(r for r in BUILTIN_RULES if r.name == "Bad Offense")
    ctx = _ctx(position="K", bad_offense_team=None)
    result = apply_rules(200.0, ctx, [rule])
    assert "Bad Offense" not in result.rules_applied


def test_follow_the_money_rule_fires():
    rule = next(r for r in BUILTIN_RULES if r.name == "Follow the Money")
    ctx = _ctx(position="WR", above_market_contract=True)
    result = apply_rules(200.0, ctx, [rule])
    assert "Follow the Money" in result.rules_applied
    assert result.adjusted_score == 210.0  # 200 * 1.05


def test_follow_the_money_rule_does_not_fire():
    rule = next(r for r in BUILTIN_RULES if r.name == "Follow the Money")
    ctx = _ctx(position="WR", above_market_contract=False)
    result = apply_rules(200.0, ctx, [rule])
    assert "Follow the Money" not in result.rules_applied


def test_apply_rules_applications_track_sequential_state():
    """Each application records the score state AT THAT POINT, not the final state."""
    rule_a = Rule(
        name="Bonus A",
        conditions=[RuleCondition(field="position", operator="==", value="WR")],
        effect=RuleEffect(type=EffectType.FLAT_BONUS, value=10.0),
    )
    rule_b = Rule(
        name="Multiplier B",
        conditions=[RuleCondition(field="position", operator="==", value="WR")],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.5),
    )
    ctx = make_ctx(position="WR")
    result = apply_rules(100.0, ctx, [rule_a, rule_b])

    # rule_a: 100 -> 110 (delta +10)
    # rule_b: 110 -> 55 (delta -55)
    assert len(result.applications) == 2
    assert result.applications[0].before_score == 100.0
    assert result.applications[0].after_score == 110.0
    assert result.applications[1].before_score == 110.0
    assert result.applications[1].after_score == 55.0
    assert result.adjusted_score == 55.0
