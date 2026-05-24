from app.engine.rules import Rule, RuleCondition, RuleEffect, EffectType


# Position-aware age thresholds for the "Over the Hill" rule.
# Players at or above these ages are considered past their production peak.
# K/DST excluded (kickers age weirdly; DST has no age).
OVER_THE_HILL_AGE = {"RB": 28, "WR": 30, "TE": 31, "QB": 36}


BUILTIN_RULES: list[Rule] = [
    Rule(
        name="RB Committee Discount",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.50)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        description="Discounts RBs in committee backfields (carry share under 50%). -15% to projected score at default weight.",
    ),
    Rule(
        name="Target Share Premium",
        conditions=[RuleCondition(field="target_share", operator=">=", value=0.25)],
        effect=RuleEffect(type=EffectType.FLAT_BONUS, value=20.0),
        description="Boosts WR/TE with elite target share (>=25% of team targets). +20 points at default weight.",
    ),
    Rule(
        name="Declining Snap%",
        conditions=[RuleCondition(field="snap_pct", operator="<", value=0.55)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
        description="Penalizes players whose offensive snap share dropped under 55%. -10% at default weight.",
    ),
    Rule(
        name="New Team Penalty",
        conditions=[RuleCondition(field="new_team", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
        description="Penalizes players adjusting to a new team or scheme. -10% at default weight.",
    ),
    Rule(
        name="New Head Coach",
        conditions=[RuleCondition(field="new_coach", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.93),
        description="Penalizes players whose team hired a new head coach (offensive system uncertainty). -7% at default weight.",
    ),
    Rule(
        name="Sophomore Leap",
        conditions=[RuleCondition(field="years_exp", operator="==", value=1)],
        effect=RuleEffect(type=EffectType.FLAT_BONUS, value=15.0),
        description="Boosts second-year skill players for the expected sophomore leap. +15 points at default weight.",
    ),
    Rule(
        name="Contract Year Flag",
        conditions=[RuleCondition(field="years_exp", operator=">", value=3)],
        effect=RuleEffect(type=EffectType.FLAG, value="Contract Year"),
        description="Flags veteran players (>3 years experience) who may be in contract years. No score change; informational only.",
    ),
    Rule(
        name="Injury History",
        conditions=[RuleCondition(field="games_played", operator="<", value=12)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.88),
        description="Penalizes players who missed significant time last season (under 12 games). -12% at default weight.",
    ),
    Rule(
        name="Handcuff RB",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.30)],
        effect=RuleEffect(type=EffectType.FLAG, value="Handcuff"),
        description="Flags low-volume backup RBs (carry share under 30%). No score change; informational only.",
    ),
    Rule(
        name="Availability Risk",
        conditions=[RuleCondition(field="games_played", operator="<", value=8)],
        effect=RuleEffect(type=EffectType.FLAG, value="Availability Risk"),
        description="Flags players with serious availability concerns (under 8 games last season). No score change; informational only.",
    ),
    Rule(
        name="TD Regression (positive)",
        conditions=[RuleCondition(field="actual_tds_above_expected", operator=">=", value=3.0)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
        description="Penalizes players who scored 3+ more TDs than their red-zone opportunity implied last year - likely to regress. -10% at default weight.",
    ),
    Rule(
        name="Red Zone Usage Premium",
        conditions=[RuleCondition(field="red_zone_looks", operator=">=", value=25)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.07),
        description="Boosts players with heavy red-zone usage last season (25+ looks inside the 20). +7% at default weight.",
    ),
    Rule(
        name="Over the Hill",
        conditions=[RuleCondition(field="is_over_the_hill", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        description="Penalizes players past their position's typical decline age: RB >=28, WR >=30, TE >=31, QB >=36. K and DST excluded. -15% at default weight.",
    ),
    Rule(
        name="Projection Unavailable",
        conditions=[RuleCondition(field="projection_unavailable", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.50),
        description="Heavy penalty for players with no current-season projection from any source - data confidence is low. -50% at default weight.",
    ),
]
