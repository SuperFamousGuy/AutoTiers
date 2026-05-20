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
    assert len(BUILTIN_RULES) >= 15
    for rule in BUILTIN_RULES:
        assert isinstance(rule, Rule)
        assert rule.name
        assert rule.conditions
