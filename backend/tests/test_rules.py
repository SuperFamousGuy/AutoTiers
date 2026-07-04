import pytest
from app.engine.rules import (
    Rule, RuleCondition, RuleEffect, EffectType, PlayerContext,
    RuleResult, apply_rules,
)
from app.engine.builtin_rules import BUILTIN_RULES
from app.api.generate import DOME_TEAMS, ELEVATION_TEAM, COLD_WEATHER_TEAMS


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
        opportunity_score_z=None, is_favorite=None,
        plays_in_dome=None, is_denver_kicker=None,
        cold_weather_kicker=None,
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
        opportunity_score_z=None, is_favorite=None,
        plays_in_dome=None, is_denver_kicker=None,
        cold_weather_kicker=None,
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


def test_builtin_rules_count_is_25():
    """Splitting flat '370 Touches' into two age bands (was 24)."""
    assert len(BUILTIN_RULES) == 25


def test_opportunity_rules_categorized_as_regression():
    """Opportunity Over-Producer and Under-Producer must group with TD Regression."""
    from app.api.rules import _categorize
    assert _categorize("Opportunity Over-Producer") == "Regression"
    assert _categorize("Opportunity Under-Producer") == "Regression"


def test_all_builtin_rules_have_descriptions():
    for rule in BUILTIN_RULES:
        assert rule.description, f"Rule '{rule.name}' is missing a description"
        assert len(rule.description) > 20, f"Rule '{rule.name}' description is suspiciously short"


def test_projection_unavailable_halves_score():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Projection Unavailable"), enabled=True)
    ctx = make_ctx(projection_unavailable=True)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 50.0
    assert "Projection Unavailable" in result.rules_applied


def test_projection_unavailable_skipped_when_false():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Projection Unavailable"), enabled=True)
    ctx = make_ctx(projection_unavailable=False)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "Projection Unavailable" not in result.rules_applied


def test_over_the_hill_fires_when_age_at_threshold():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Over the Hill"), enabled=True)
    ctx = make_ctx(is_over_the_hill=True)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0  # penalty applied
    assert "Over the Hill" in result.rules_applied


def test_over_the_hill_does_not_fire_when_false():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Over the Hill"), enabled=True)
    ctx = make_ctx(is_over_the_hill=False)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "Over the Hill" not in result.rules_applied


def test_over_the_hill_skipped_when_none():
    """K/DST/missing age have is_over_the_hill=None — rule shouldn't fire."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Over the Hill"), enabled=True)
    ctx = make_ctx(is_over_the_hill=None)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0


def test_td_regression_positive_fires_above_threshold():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "TD Regression"), enabled=True)
    ctx = make_ctx(actual_tds_above_expected=4.0)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0  # multiplier < 1.0


def test_td_regression_positive_does_not_fire_below_threshold():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "TD Regression"), enabled=True)
    ctx = make_ctx(actual_tds_above_expected=2.0)  # below threshold of 3.0
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "TD Regression" not in result.rules_applied


def test_red_zone_premium_fires_above_25():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Red Zone Usage Premium"), enabled=True)
    ctx = make_ctx(red_zone_looks=30)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score > 100.0


def test_red_zone_premium_skipped_when_none():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Red Zone Usage Premium"), enabled=True)
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
        enabled=True,
    )
    ctx = make_ctx(position="WR", projected_score=100.0)
    result = apply_rules(100.0, ctx, [rule])

    assert len(result.applications) == 1
    app = result.applications[0]
    assert app.name == "Test Bonus"
    assert app.before_score == 100.0
    assert app.after_score == 120.0
    assert app.delta == 20.0


def _touches_band(name: str):
    import dataclasses
    return dataclasses.replace(
        next(r for r in BUILTIN_RULES if r.name == name), enabled=True
    )


def test_370_touches_young_band_fires_on_young_rb():
    rule = _touches_band("370 Touches (Young RB)")
    ctx = _ctx(prior_touches=375, age=24)
    result = apply_rules(200.0, ctx, [rule])
    assert "370 Touches (Young RB)" in result.rules_applied
    assert result.adjusted_score == 174.0  # 200 * 0.87


def test_370_touches_veteran_band_fires_on_veteran_rb():
    rule = _touches_band("370 Touches (Veteran RB)")
    ctx = _ctx(prior_touches=375, age=29)
    result = apply_rules(200.0, ctx, [rule])
    assert "370 Touches (Veteran RB)" in result.rules_applied
    assert result.adjusted_score == 150.0  # 200 * 0.75


def test_370_touches_young_and_veteran_give_different_multipliers():
    """Acceptance criterion (#498): a 24yo and a 29yo 380-touch RB differ."""
    young = _touches_band("370 Touches (Young RB)")
    veteran = _touches_band("370 Touches (Veteran RB)")
    young_score = apply_rules(200.0, _ctx(prior_touches=380, age=24), [young, veteran]).adjusted_score
    veteran_score = apply_rules(200.0, _ctx(prior_touches=380, age=29), [young, veteran]).adjusted_score
    assert young_score == 174.0   # young band only
    assert veteran_score == 150.0  # veteran band only
    assert young_score != veteran_score


def test_370_touches_bands_are_mutually_exclusive_at_boundary():
    """age 26 -> young only; age 27 -> veteran only. No overlap, no gap."""
    young = _touches_band("370 Touches (Young RB)")
    veteran = _touches_band("370 Touches (Veteran RB)")
    at_26 = apply_rules(200.0, _ctx(prior_touches=380, age=26), [young, veteran])
    at_27 = apply_rules(200.0, _ctx(prior_touches=380, age=27), [young, veteran])
    assert at_26.rules_applied == ["370 Touches (Young RB)"]
    assert at_27.rules_applied == ["370 Touches (Veteran RB)"]


def test_370_touches_neither_band_fires_under_touch_threshold():
    young = _touches_band("370 Touches (Young RB)")
    veteran = _touches_band("370 Touches (Veteran RB)")
    result = apply_rules(200.0, _ctx(prior_touches=369, age=24), [young, veteran])
    assert result.rules_applied == []
    assert result.adjusted_score == 200.0


def test_370_touches_neither_band_fires_when_age_unknown():
    """Documented behavior: a 370+ touch RB with unknown age fires neither band.

    `_evaluate` treats a None field as a non-match, so both age conditions fail.
    This is deliberate (see builtin_rules.py) — locked here so a future edit
    can't silently start (or keep) penalizing missing-age players by accident.
    """
    young = _touches_band("370 Touches (Young RB)")
    veteran = _touches_band("370 Touches (Veteran RB)")
    result = apply_rules(200.0, _ctx(prior_touches=380, age=None), [young, veteran])
    assert result.rules_applied == []
    assert result.adjusted_score == 200.0


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
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Year After the Year After"), enabled=True)
    ctx = _ctx(position="WR", injured_two_years_ago=True)
    result = apply_rules(200.0, ctx, [rule])
    assert "Year After the Year After" in result.rules_applied
    assert result.adjusted_score == 220.0  # 200 * 1.10


def test_year_after_rule_does_not_fire_when_false():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Year After the Year After"), enabled=True)
    ctx = _ctx(position="WR", injured_two_years_ago=False)
    result = apply_rules(200.0, ctx, [rule])
    assert "Year After the Year After" not in result.rules_applied


def test_bad_offense_rule_fires():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Bad Offense"), enabled=True)
    ctx = _ctx(position="WR", bad_offense_team=True)
    result = apply_rules(200.0, ctx, [rule])
    assert "Bad Offense" in result.rules_applied
    assert result.adjusted_score == 186.0  # 200 * 0.93


def test_bad_offense_rule_does_not_fire_when_none():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Bad Offense"), enabled=True)
    ctx = _ctx(position="K", bad_offense_team=None)
    result = apply_rules(200.0, ctx, [rule])
    assert "Bad Offense" not in result.rules_applied


def test_follow_the_money_rule_fires():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Follow the Money"), enabled=True)
    ctx = _ctx(position="WR", above_market_contract=True)
    result = apply_rules(200.0, ctx, [rule])
    assert "Follow the Money" in result.rules_applied
    assert result.adjusted_score == 210.0  # 200 * 1.05


def test_follow_the_money_rule_does_not_fire():
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Follow the Money"), enabled=True)
    ctx = _ctx(position="WR", above_market_contract=False)
    result = apply_rules(200.0, ctx, [rule])
    assert "Follow the Money" not in result.rules_applied


def test_position_gate_skips_rule_when_position_not_in_list():
    """A rule with positions=["RB"] must not fire on a WR player."""
    rule = Rule(
        name="RB Only Rule",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.50)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        positions=["RB"],
        enabled=True,
    )
    # WR player with carry_share that would trigger the condition — rule should not fire.
    ctx = make_ctx(position="WR", carry_share=0.30)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "RB Only Rule" not in result.rules_applied


def test_position_gate_fires_rule_when_position_matches():
    """A rule with positions=["RB"] must fire on a matching RB player."""
    rule = Rule(
        name="RB Only Rule",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.50)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        positions=["RB"],
        enabled=True,
    )
    ctx = make_ctx(position="RB", carry_share=0.30)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0
    assert "RB Only Rule" in result.rules_applied


def test_position_gate_none_fires_on_all_positions():
    """A rule with positions=None must fire on any position (no gate applied)."""
    rule = Rule(
        name="Any Position Rule",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.50)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        positions=None,
        enabled=True,
    )
    for pos in ["QB", "RB", "WR", "TE", "K", "DST"]:
        ctx = make_ctx(position=pos, carry_share=0.30)
        result = apply_rules(100.0, ctx, [rule])
        assert result.adjusted_score < 100.0, f"Rule should fire on position {pos}"


def test_position_gate_empty_list_fires_on_all_positions():
    """A rule with positions=[] is treated identically to None — applies to all."""
    rule = Rule(
        name="Any Position Rule",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.50)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        positions=[],
        enabled=True,
    )
    ctx = make_ctx(position="WR", carry_share=0.30)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0
    assert "Any Position Rule" in result.rules_applied


def test_position_gate_multi_position_list():
    """A rule with positions=["WR", "TE"] fires on WR and TE but not RB."""
    rule = Rule(
        name="Receiver Rule",
        conditions=[RuleCondition(field="target_share", operator=">=", value=0.25)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.07),
        positions=["WR", "TE"],
        enabled=True,
    )
    wr_ctx = make_ctx(position="WR", target_share=0.30)
    te_ctx = make_ctx(position="TE", target_share=0.30)
    rb_ctx = make_ctx(position="RB", target_share=0.30)

    assert apply_rules(100.0, wr_ctx, [rule]).adjusted_score > 100.0
    assert apply_rules(100.0, te_ctx, [rule]).adjusted_score > 100.0
    assert apply_rules(100.0, rb_ctx, [rule]).adjusted_score == 100.0


def test_builtin_rb_committee_penalty_has_rb_position():
    rule = next(r for r in BUILTIN_RULES if r.name == "RB Committee Penalty")
    assert rule.positions == ["RB"]


def test_builtin_target_share_premium_has_rb_wr_te_positions():
    rule = next(r for r in BUILTIN_RULES if r.name == "Target Share Premium")
    assert rule.positions == ["RB", "WR", "TE"]


def test_builtin_370_touches_bands_have_rb_position():
    for name in ("370 Touches (Young RB)", "370 Touches (Veteran RB)"):
        rule = next(r for r in BUILTIN_RULES if r.name == name)
        assert rule.positions == ["RB"]


def test_builtin_handcuff_rb_has_rb_position():
    rule = next(r for r in BUILTIN_RULES if r.name == "Handcuff RB")
    assert rule.positions == ["RB"]


def test_builtin_over_the_hill_has_skill_positions_including_k():
    rule = next(r for r in BUILTIN_RULES if r.name == "Over the Hill")
    assert set(rule.positions) == {"QB", "RB", "WR", "TE", "K"}


def test_builtin_year_after_the_year_after_has_expanded_positions():
    rule = next(r for r in BUILTIN_RULES if r.name == "Year After the Year After")
    assert set(rule.positions) == {"QB", "RB", "WR", "TE", "K"}


def test_builtin_bad_offense_has_skill_positions():
    rule = next(r for r in BUILTIN_RULES if r.name == "Bad Offense")
    assert set(rule.positions) == {"QB", "RB", "WR", "TE"}


def test_builtin_follow_the_money_has_skill_positions():
    rule = next(r for r in BUILTIN_RULES if r.name == "Follow the Money")
    assert set(rule.positions) == {"QB", "RB", "WR", "TE"}


def test_builtin_rules_without_positions_default_to_none():
    """Rules not in the position-aware rules should have positions=None."""
    no_position_rule_names = {
        "New Team Penalty", "New Head Coach",
        "Contract Year Flag", "Injury History",
        "Availability Risk", "TD Regression", "Opportunity Over-Producer",
        "Opportunity Under-Producer", "Red Zone Usage Premium",
        "Projection Unavailable", "Favorites",
    }
    for rule in BUILTIN_RULES:
        if rule.name in no_position_rule_names:
            assert rule.positions is None, f"Rule '{rule.name}' should have positions=None"


def test_builtin_declining_snap_has_rb_wr_te_positions():
    """Declining Snap% now applies only to RB/WR/TE (not QB, K, or DST)."""
    rule = next(r for r in BUILTIN_RULES if r.name == "Declining Snap%")
    assert rule.positions == ["RB", "WR", "TE"]


def test_apply_rules_applications_track_sequential_state():
    """Each application records the score state AT THAT POINT, not the final state."""
    rule_a = Rule(
        name="Bonus A",
        conditions=[RuleCondition(field="position", operator="==", value="WR")],
        effect=RuleEffect(type=EffectType.FLAT_BONUS, value=10.0),
        enabled=True,
    )
    rule_b = Rule(
        name="Multiplier B",
        conditions=[RuleCondition(field="position", operator="==", value="WR")],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.5),
        enabled=True,
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


# ---------------------------------------------------------------------------
# Dome Kicker and Mile High Kicker tests
# ---------------------------------------------------------------------------

def test_dome_teams_contains_exactly_11_teams():
    """DOME_TEAMS must contain exactly the 11 documented teams."""
    expected = {"DET", "MIN", "NO", "LV", "DAL", "HOU", "IND", "ARI", "ATL", "LAR", "LAC"}
    assert DOME_TEAMS == expected


def test_elevation_team_is_den():
    assert ELEVATION_TEAM == "DEN"


def test_dome_kicker_fires_on_k_with_plays_in_dome_true():
    """plays_in_dome=True on a K → Dome Kicker fires (+4%)."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    ctx = make_ctx(position="K", plays_in_dome=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Dome Kicker" in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 1.04)


def test_dome_kicker_does_not_fire_on_non_k_position():
    """plays_in_dome=True on a QB → position gate blocks Dome Kicker."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    ctx = make_ctx(position="QB", plays_in_dome=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Dome Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_dome_kicker_does_not_fire_when_plays_in_dome_false():
    """plays_in_dome=False on a K → condition fails, rule skipped."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    ctx = make_ctx(position="K", plays_in_dome=False)
    result = apply_rules(100.0, ctx, [rule])
    assert "Dome Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_dome_kicker_does_not_fire_when_plays_in_dome_none():
    """plays_in_dome=None on a K → _evaluate short-circuits to False."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    ctx = make_ctx(position="K", plays_in_dome=None)
    result = apply_rules(100.0, ctx, [rule])
    assert "Dome Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_mile_high_kicker_fires_on_k_with_is_denver_kicker_true():
    """is_denver_kicker=True on a K → Mile High Kicker fires (+5%)."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Mile High Kicker"), enabled=True)
    ctx = make_ctx(position="K", is_denver_kicker=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Mile High Kicker" in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 1.05)


def test_mile_high_kicker_does_not_fire_on_non_k_position():
    """is_denver_kicker=True on a WR → position gate blocks Mile High Kicker."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Mile High Kicker"), enabled=True)
    ctx = make_ctx(position="WR", is_denver_kicker=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Mile High Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_both_dome_and_mile_high_rules_do_not_stack_for_den_k():
    """DEN is NOT a dome team — a Denver K gets only Mile High, not Dome Kicker."""
    import dataclasses
    dome_rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    mhk_rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Mile High Kicker"), enabled=True)
    # DEN kicker: plays_in_dome=False (DEN not in DOME_TEAMS), is_denver_kicker=True
    ctx = make_ctx(position="K", plays_in_dome=False, is_denver_kicker=True)
    result = apply_rules(100.0, ctx, [dome_rule, mhk_rule])
    assert "Mile High Kicker" in result.rules_applied
    assert "Dome Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 1.05)


def test_both_dome_and_mile_high_rules_stack_when_both_true():
    """A hypothetical K with plays_in_dome=True AND is_denver_kicker=True gets both multipliers."""
    import dataclasses
    dome_rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    mhk_rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Mile High Kicker"), enabled=True)
    ctx = make_ctx(position="K", plays_in_dome=True, is_denver_kicker=True)
    result = apply_rules(100.0, ctx, [dome_rule, mhk_rule])
    assert "Dome Kicker" in result.rules_applied
    assert "Mile High Kicker" in result.rules_applied
    # 100 * 1.04 * 1.05 = 109.2
    assert result.adjusted_score == pytest.approx(100.0 * 1.04 * 1.05)


def test_dome_kicker_rule_has_k_position():
    """Dome Kicker must carry positions=["K"]."""
    rule = next(r for r in BUILTIN_RULES if r.name == "Dome Kicker")
    assert rule.positions == ["K"]


def test_mile_high_kicker_rule_has_k_position():
    """Mile High Kicker must carry positions=["K"]."""
    rule = next(r for r in BUILTIN_RULES if r.name == "Mile High Kicker")
    assert rule.positions == ["K"]


def test_den_not_in_dome_teams():
    """Denver is not a dome team — the two bonuses are separate signals."""
    assert "DEN" not in DOME_TEAMS


def test_dome_kicker_applications_appear_in_rule_applications():
    """When Dome Kicker fires, its RuleApplication is present in result.applications."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Dome Kicker"), enabled=True)
    ctx = make_ctx(position="K", plays_in_dome=True)
    result = apply_rules(100.0, ctx, [rule])
    assert len(result.applications) == 1
    app = result.applications[0]
    assert app.name == "Dome Kicker"
    assert app.before_score == 100.0
    assert app.after_score == pytest.approx(104.0)
    assert app.delta == pytest.approx(4.0)


def test_mile_high_kicker_applications_appear_in_rule_applications():
    """When Mile High Kicker fires, its RuleApplication is present in result.applications."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Mile High Kicker"), enabled=True)
    ctx = make_ctx(position="K", is_denver_kicker=True)
    result = apply_rules(100.0, ctx, [rule])
    assert len(result.applications) == 1
    app = result.applications[0]
    assert app.name == "Mile High Kicker"
    assert app.before_score == 100.0
    assert app.after_score == pytest.approx(105.0)
    assert app.delta == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# FIX 1 — WR age threshold 30→31
# ---------------------------------------------------------------------------

def test_over_the_hill_age_wr_threshold_is_31():
    """OVER_THE_HILL_AGE["WR"] must be 31 (raised from 30 per 2024-25 research)."""
    from app.engine.builtin_rules import OVER_THE_HILL_AGE
    assert OVER_THE_HILL_AGE["WR"] == 31


def test_wr_age_30_does_not_trigger_over_the_hill():
    """A 30-year-old WR must NOT have is_over_the_hill=True after the threshold raise."""
    from app.engine.builtin_rules import OVER_THE_HILL_AGE
    age = 30
    position = "WR"
    is_over_the_hill = age >= OVER_THE_HILL_AGE[position]
    assert is_over_the_hill is False


def test_wr_age_31_triggers_over_the_hill():
    """A 31-year-old WR must have is_over_the_hill=True (new threshold)."""
    from app.engine.builtin_rules import OVER_THE_HILL_AGE
    import dataclasses
    age = 31
    position = "WR"
    is_over_the_hill = age >= OVER_THE_HILL_AGE[position]
    assert is_over_the_hill is True

    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Over the Hill"), enabled=True)
    ctx = make_ctx(position="WR", is_over_the_hill=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Over the Hill" in result.rules_applied
    assert result.adjusted_score < 100.0


# ---------------------------------------------------------------------------
# FIX 2 — Sophomore Leap positional gate
# ---------------------------------------------------------------------------

def test_sophomore_leap_fires_on_wr():
    """Second-year WR must receive the Sophomore Leap boost."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap"), enabled=True)
    ctx = make_ctx(position="WR", years_exp=1)
    result = apply_rules(100.0, ctx, [rule])
    assert "Sophomore Leap" in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 1.08)


def test_sophomore_leap_fires_on_te():
    """Second-year TE must receive the Sophomore Leap boost."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap"), enabled=True)
    ctx = make_ctx(position="TE", years_exp=1)
    result = apply_rules(100.0, ctx, [rule])
    assert "Sophomore Leap" in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 1.08)


def test_sophomore_leap_fires_on_qb():
    """Second-year QB must receive the Sophomore Leap boost."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap"), enabled=True)
    ctx = make_ctx(position="QB", years_exp=1)
    result = apply_rules(100.0, ctx, [rule])
    assert "Sophomore Leap" in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 1.08)


def test_sophomore_leap_does_not_fire_on_rb():
    """Second-year RB must NOT receive the Sophomore Leap boost (no evidence base for RBs)."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap"), enabled=True)
    ctx = _ctx(position="RB", years_exp=1)
    result = apply_rules(100.0, ctx, [rule])
    assert "Sophomore Leap" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_sophomore_leap_does_not_fire_on_k():
    """Second-year K must NOT receive the Sophomore Leap boost."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap"), enabled=True)
    ctx = make_ctx(position="K", years_exp=1)
    result = apply_rules(100.0, ctx, [rule])
    assert "Sophomore Leap" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_sophomore_leap_does_not_fire_on_dst():
    """Second-year DST must NOT receive the Sophomore Leap boost."""
    import dataclasses
    rule = dataclasses.replace(next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap"), enabled=True)
    ctx = make_ctx(position="DST", years_exp=1)
    result = apply_rules(100.0, ctx, [rule])
    assert "Sophomore Leap" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_builtin_sophomore_leap_has_wr_te_qb_positions():
    """Sophomore Leap must carry positions=["WR", "TE", "QB"] — no RB, K, or DST."""
    rule = next(r for r in BUILTIN_RULES if r.name == "Sophomore Leap")
    assert set(rule.positions) == {"WR", "TE", "QB"}


# ---------------------------------------------------------------------------
# FIX 3 — Rule weight clamp [0.0, 2.0]
# ---------------------------------------------------------------------------

def test_rule_override_schema_rejects_weight_above_2():
    """RuleOverrideSchema must reject weight > 2.0 with a validation error."""
    from pydantic import ValidationError
    from app.schemas.rules import RuleOverrideSchema
    with pytest.raises(ValidationError):
        RuleOverrideSchema(name="Projection Unavailable", enabled=True, weight=2.1)


def test_rule_override_schema_rejects_weight_below_0():
    """RuleOverrideSchema must reject weight < 0.0 with a validation error."""
    from pydantic import ValidationError
    from app.schemas.rules import RuleOverrideSchema
    with pytest.raises(ValidationError):
        RuleOverrideSchema(name="Projection Unavailable", enabled=True, weight=-0.1)


def test_rule_override_schema_accepts_weight_at_bounds():
    """RuleOverrideSchema must accept weights exactly at 0.0 and 2.0."""
    from app.schemas.rules import RuleOverrideSchema
    low = RuleOverrideSchema(name="Test", enabled=True, weight=0.0)
    high = RuleOverrideSchema(name="Test", enabled=True, weight=2.0)
    assert low.weight == 0.0
    assert high.weight == 2.0


def test_rule_schema_rejects_weight_above_2():
    """RuleSchema must also reject weight > 2.0."""
    from pydantic import ValidationError
    from app.schemas.rules import RuleSchema, RuleConditionSchema, RuleEffectSchema
    from app.engine.rules import EffectType
    with pytest.raises(ValidationError):
        RuleSchema(
            name="Bad Weight Rule",
            conditions=[RuleConditionSchema(field="age", operator=">=", value=30)],
            effect=RuleEffectSchema(type=EffectType.MULTIPLIER, value=0.9),
            weight=3.0,
        )


def test_weight_2_on_projection_unavailable_does_not_go_negative():
    """weight=2.0 on Projection Unavailable (multiplier=0.50) must not produce negative score.

    actual_multiplier = 1.0 + (0.50 - 1.0) * 2.0 = 1.0 + (-0.5 * 2.0) = 0.0
    score = 100.0 * 0.0 = 0.0  (floor, not negative)
    """
    rule = Rule(
        name="Projection Unavailable",
        conditions=[RuleCondition(field="projection_unavailable", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.50),
        enabled=True,
        weight=2.0,
    )
    ctx = make_ctx(projection_unavailable=True)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score >= 0.0
    assert result.adjusted_score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Cold-Weather Kicker tests
# ---------------------------------------------------------------------------

def test_cold_weather_teams_contains_exactly_8_teams():
    """COLD_WEATHER_TEAMS must contain exactly the 8 documented teams."""
    expected = {"GB", "BUF", "NE", "CHI", "CLE", "PIT", "CIN", "KC"}
    assert COLD_WEATHER_TEAMS == expected


def test_cold_weather_teams_no_overlap_with_dome_teams():
    """COLD_WEATHER_TEAMS and DOME_TEAMS must be mutually exclusive."""
    assert COLD_WEATHER_TEAMS & DOME_TEAMS == frozenset()


def test_den_not_in_cold_weather_teams():
    """DEN is excluded from COLD_WEATHER_TEAMS — altitude handled separately."""
    assert "DEN" not in COLD_WEATHER_TEAMS


def test_elevation_team_not_in_cold_weather_teams():
    """ELEVATION_TEAM must not appear in COLD_WEATHER_TEAMS."""
    assert ELEVATION_TEAM not in COLD_WEATHER_TEAMS


def test_cold_weather_kicker_fires_on_k_with_cold_weather_kicker_true():
    """cold_weather_kicker=True on a K → Cold-Weather Kicker fires (-4%)."""
    import dataclasses
    rule = dataclasses.replace(
        next(r for r in BUILTIN_RULES if r.name == "Cold-Weather Kicker"), enabled=True
    )
    ctx = make_ctx(position="K", cold_weather_kicker=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Cold-Weather Kicker" in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0 * 0.96)


def test_cold_weather_kicker_does_not_fire_on_non_k_position():
    """cold_weather_kicker=True on a QB → position gate blocks Cold-Weather Kicker."""
    import dataclasses
    rule = dataclasses.replace(
        next(r for r in BUILTIN_RULES if r.name == "Cold-Weather Kicker"), enabled=True
    )
    ctx = make_ctx(position="QB", cold_weather_kicker=True)
    result = apply_rules(100.0, ctx, [rule])
    assert "Cold-Weather Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_cold_weather_kicker_does_not_fire_when_false():
    """cold_weather_kicker=False on a K → condition fails, rule skipped."""
    import dataclasses
    rule = dataclasses.replace(
        next(r for r in BUILTIN_RULES if r.name == "Cold-Weather Kicker"), enabled=True
    )
    ctx = make_ctx(position="K", cold_weather_kicker=False)
    result = apply_rules(100.0, ctx, [rule])
    assert "Cold-Weather Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_cold_weather_kicker_does_not_fire_when_none():
    """cold_weather_kicker=None on a K → _evaluate short-circuits to False."""
    import dataclasses
    rule = dataclasses.replace(
        next(r for r in BUILTIN_RULES if r.name == "Cold-Weather Kicker"), enabled=True
    )
    ctx = make_ctx(position="K", cold_weather_kicker=None)
    result = apply_rules(100.0, ctx, [rule])
    assert "Cold-Weather Kicker" not in result.rules_applied
    assert result.adjusted_score == pytest.approx(100.0)


def test_cold_weather_kicker_rule_has_k_position():
    """Cold-Weather Kicker must carry positions=["K"]."""
    rule = next(r for r in BUILTIN_RULES if r.name == "Cold-Weather Kicker")
    assert rule.positions == ["K"]
