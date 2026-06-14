from app.engine.rules import Rule, RuleCondition, RuleEffect, EffectType


# Position-aware age thresholds for the "Over the Hill" rule.
# Players at or above these ages are considered past their production peak.
# DST excluded (no individual age). K threshold is 40 — elite kickers play
# into their late 30s but accuracy typically begins declining around age 40.
OVER_THE_HILL_AGE = {"RB": 28, "WR": 31, "TE": 31, "QB": 36, "K": 40}


BUILTIN_RULES: list[Rule] = [
    Rule(
        name="RB Committee Penalty",
        conditions=[RuleCondition(field="carry_share", operator="<", value=0.50)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.85),
        description="Penalizes RBs in committee backfields (carry share under 50%). -15% to projected score at default weight.",
        positions=["RB"],
    ),
    Rule(
        name="Target Share Premium",
        conditions=[RuleCondition(field="target_share", operator=">=", value=0.25)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.07),
        description="Boosts WR/TE/RB with elite target share (>=25% of team targets). +7% at default weight. Particularly relevant for RBs in PPR formats.",
        positions=["RB", "WR", "TE"],
    ),
    Rule(
        name="Declining Snap%",
        conditions=[RuleCondition(field="snap_pct", operator="<", value=0.55)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
        description="Penalizes players whose offensive snap share dropped under 55%. -10% at default weight.",
        positions=["RB", "WR", "TE"],
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
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.08),
        description="Boosts second-year WR/TE/QB for the expected sophomore leap. +8% at default weight.",
        positions=["WR", "TE", "QB"],
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
        positions=["RB"],
    ),
    Rule(
        name="Availability Risk",
        conditions=[RuleCondition(field="games_played", operator="<", value=8)],
        effect=RuleEffect(type=EffectType.FLAG, value="Availability Risk"),
        description="Flags players with serious availability concerns (under 8 games last season). No score change; informational only.",
    ),
    Rule(
        name="TD Regression",
        conditions=[RuleCondition(field="actual_tds_above_expected", operator=">=", value=3.0)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
        description="Penalizes players who scored 3+ more TDs than their red-zone opportunity implied last year - likely to regress. -10% at default weight.",
    ),
    Rule(
        name="Opportunity Over-Producer",
        conditions=[RuleCondition(field="opportunity_score_z", operator=">=", value=1.5)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.92),
        description=(
            "Penalizes players who scored 1.5+ standard deviations above their "
            "target/carry/red-zone opportunity last season — strong regression "
            "candidate. -8% at default weight."
        ),
    ),
    Rule(
        name="Opportunity Under-Producer",
        conditions=[RuleCondition(field="opportunity_score_z", operator="<=", value=-1.5)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.08),
        description=(
            "Boosts players who scored 1.5+ standard deviations below their "
            "target/carry/red-zone opportunity last season — positive regression "
            "candidate. +8% at default weight."
        ),
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
        description="Penalizes players past their position's typical decline age: RB >=28, WR >=31, TE >=31, QB >=36, K >=40. DST excluded. -15% at default weight.",
        positions=["QB", "RB", "WR", "TE", "K"],
    ),
    Rule(
        name="Projection Unavailable",
        conditions=[RuleCondition(field="projection_unavailable", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.50),
        description="Heavy penalty for players with no current-season projection from any source - data confidence is low. -50% at default weight.",
    ),
    Rule(
        name="370 Touches",
        conditions=[
            RuleCondition(field="position", operator="==", value="RB"),
            RuleCondition(field="prior_touches", operator=">=", value=370),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
        description="Penalizes RBs who absorbed 370+ touches (carries + receptions) last season — historically a leading indicator of decline. -10% at default weight.",
        positions=["RB"],
    ),
    Rule(
        name="Year After the Year After",
        conditions=[
            RuleCondition(field="injured_two_years_ago", operator="==", value=True),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.10),
        description="Boosts skill players returning to full health two years after an injury-shortened season (under 12 games played). Soft-tissue injuries take a full year to fully recover; year two is when players are truly back. +10% at default weight.",
        positions=["QB", "RB", "WR", "TE", "K"],
    ),
    Rule(
        name="Bad Offense",
        conditions=[RuleCondition(field="bad_offense_team", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.93),
        description="Penalizes offensive skill players (QB/RB/WR/TE) on teams ranked in the bottom 8 by 3-year average points scored. Chronic structural issues suppress ceiling. -7% at default weight.",
        positions=["QB", "RB", "WR", "TE"],
    ),
    Rule(
        name="Follow the Money",
        conditions=[RuleCondition(field="above_market_contract", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.05),
        description="Boosts QB/RB/WR/TE players paid above-market contracts (cap hit > 1.5x position median). Coaches prioritize touches/snaps for big-money players to justify the investment. +5% at default weight.",
        positions=["QB", "RB", "WR", "TE"],
    ),
    Rule(
        name="Favorites",
        conditions=[RuleCondition(field="is_favorite", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.05),
        description=(
            "Boosts players you've marked as favorites — either directly by player "
            "or by team. +5% at default weight. This is a personalization layer, "
            "not a statistical claim."
        ),
    ),
    Rule(
        name="Dome Kicker",
        conditions=[RuleCondition(field="plays_in_dome", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.04),
        description=(
            "Boosts kickers whose home venue is a dome or retractable-roof stadium "
            "(DET, MIN, NO, LV, DAL, HOU, IND, ARI, ATL, LAR, LAC). "
            "Controlled environment eliminates wind/cold penalties. "
            "Signal is modest across sources; +4% at default weight."
        ),
        positions=["K"],
    ),
    Rule(
        name="Mile High Kicker",
        conditions=[RuleCondition(field="is_denver_kicker", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.05),
        description=(
            "Boosts the Denver Broncos kicker for the structural altitude advantage "
            "at ~5,280 ft (~5 yards of extra range per Burke/Advanced Football Analytics). "
            "8 home games at elevation per season; visiting kickers only benefit "
            "for one game so no season-long boost warranted for them. +5% at default weight."
        ),
        positions=["K"],
    ),
]
