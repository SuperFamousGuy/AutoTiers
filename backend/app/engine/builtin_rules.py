from app.engine.rules import Rule, RuleCondition, RuleEffect, EffectType


def _rule(name: str, conditions: list[tuple], effect_type: EffectType, effect_value) -> Rule:
    return Rule(
        name=name,
        conditions=[RuleCondition(field=f, operator=op, value=v) for f, op, v in conditions],
        effect=RuleEffect(type=effect_type, value=effect_value),
        enabled=True,
        weight=1.0,
    )


BUILTIN_RULES: list[Rule] = [
    # Age / Longevity
    _rule("RB Age 28-29 Penalty", [("position", "==", "RB"), ("age", ">=", 28), ("age", "<", 30)], EffectType.MULTIPLIER, 0.92),
    _rule("RB Age 30-31 Penalty", [("position", "==", "RB"), ("age", ">=", 30), ("age", "<", 32)], EffectType.MULTIPLIER, 0.84),
    _rule("RB Age 32+ Penalty",   [("position", "==", "RB"), ("age", ">=", 32)],                   EffectType.MULTIPLIER, 0.76),
    _rule("WR Age 31-32 Penalty", [("position", "==", "WR"), ("age", ">=", 31), ("age", "<", 33)], EffectType.MULTIPLIER, 0.95),
    _rule("WR Age 33+ Penalty",   [("position", "==", "WR"), ("age", ">=", 33)],                   EffectType.MULTIPLIER, 0.90),
    _rule("Dynasty Youth Premium (<25)", [("age", "<", 25)],                                        EffectType.FLAT_BONUS, 15.0),

    # Usage
    _rule("RB Committee Discount",   [("position", "==", "RB"), ("carry_share", "<", 0.50)],   EffectType.MULTIPLIER, 0.85),
    _rule("Target Share Premium",    [("target_share", ">=", 0.25)],                           EffectType.FLAT_BONUS, 20.0),
    _rule("Declining Snap% Penalty", [("snap_pct", "<", 0.55)],                                EffectType.MULTIPLIER, 0.90),

    # Situation
    _rule("New Team Penalty",    [("new_team", "==", True)],                                    EffectType.MULTIPLIER, 0.90),
    _rule("New Head Coach",      [("new_coach", "==", True)],                                   EffectType.MULTIPLIER, 0.93),
    _rule("Sophomore Leap",      [("years_exp", "==", 1)],                                      EffectType.FLAT_BONUS, 15.0),
    _rule("Contract Year Flag",  [("years_exp", ">", 3)],                                       EffectType.FLAG, "Contract Year"),

    # Regression
    _rule("Injury History Penalty", [("games_played", "<", 12)],                               EffectType.MULTIPLIER, 0.88),
    _rule("TD Regression (positive)", [("actual_tds_above_expected", ">=", 3.0)],              EffectType.MULTIPLIER, 0.90),
    _rule("Red Zone Usage Premium", [("red_zone_looks", ">=", 25)],                            EffectType.MULTIPLIER, 1.07),

    # Flags
    _rule("Handcuff Flag",          [("position", "==", "RB"), ("carry_share", "<", 0.30)],    EffectType.FLAG, "Handcuff"),
    _rule("Availability Risk Flag", [("games_played", "<", 8)],                                EffectType.FLAG, "Availability Risk"),
]
