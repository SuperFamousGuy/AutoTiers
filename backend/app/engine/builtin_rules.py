from typing import Optional

from app.engine.rules import Rule, RuleCondition, RuleEffect, EffectType


# Position-aware age thresholds for the "Over the Hill" rule.
# Players at or above these ages are considered past their production peak.
# DST excluded (no individual age). K threshold is 40 — elite kickers play
# into their late 30s but accuracy typically begins declining around age 40.
# QB is intentionally ABSENT from this dict: its cliff is not a single age but
# is conditioned on prior-season rushing volume — see over_the_hill_age().
OVER_THE_HILL_AGE = {"RB": 28, "WR": 31, "TE": 31, "K": 40}

# QB aging is bimodal (#576). Dual-threat/rushing QBs lean on a rushing floor
# that erodes as mid-20s lower-body explosiveness fades, so they decline early
# (sell window 27-28; rushing falls off after ~29). Pocket passers ride arm
# talent and a supporting cast and sustain elite production much later
# (Stafford top-3 at 37, Rodgers mid-30s, Brady at 44). We therefore split the
# QB cliff on prior-season rush attempts instead of applying a flat age 36.
#
# Thresholds locked by the mathematician against nfl_data_py rushing-attempt
# curves (Vick/Wilson/Newton decline onset for mobile; Stafford/Rodgers/Brady
# longevity for pocket):
#   - 60 rush attempts (~3.5/game) is where rushing stops being incidental
#     scramble yardage and becomes a real, legs-dependent fantasy floor.
#   - Mobile QBs go over the hill at 31 (one year ahead of the observed 32
#     Wilson/Newton cliff, matching Vick's earlier onset).
#   - Pocket passers go over the hill at 38 (past the old flat 36, matching the
#     Stafford/Rodgers/Brady evidence).
QB_MOBILE_RUSH_ATT_THRESHOLD = 60
OVER_THE_HILL_AGE_QB_MOBILE = 31
OVER_THE_HILL_AGE_QB_POCKET = 38


def over_the_hill_age(position: str, prior_rush_att: Optional[int]) -> Optional[int]:
    """Age at/above which a player at ``position`` is 'over the hill'.

    Returns ``None`` for positions with no cliff (e.g. DST, or an unknown
    position). QB is rushing-volume-conditioned: a QB whose prior-season rush
    attempts reach ``QB_MOBILE_RUSH_ATT_THRESHOLD`` is treated as a dual-threat
    and gets the earlier mobile cliff; everyone else — including a QB with no
    prior stat row (``prior_rush_att is None``) or a recorded zero — is treated
    as a pocket passer and gets the later cliff. Treating unknown rushing volume
    as pocket is the conservative failure mode: we would rather under-penalize an
    unknown-mobility QB than false-positive an aging pocket passer.
    """
    if position == "QB":
        if prior_rush_att is not None and prior_rush_att >= QB_MOBILE_RUSH_ATT_THRESHOLD:
            return OVER_THE_HILL_AGE_QB_MOBILE
        return OVER_THE_HILL_AGE_QB_POCKET
    return OVER_THE_HILL_AGE.get(position)


def compute_is_over_the_hill(
    position: str, age: Optional[int], prior_rush_att: Optional[int] = None
) -> Optional[bool]:
    """Whether a player is past their position's decline age.

    Returns ``None`` (rule skipped) when age is unknown or the position has no
    cliff; otherwise ``age >= threshold`` where the threshold comes from
    :func:`over_the_hill_age`.
    """
    if age is None:
        return None
    threshold = over_the_hill_age(position, prior_rush_att)
    if threshold is None:
        return None
    return age >= threshold


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
        description="Boosts second-year WR/QB for the expected sophomore leap. +8% at default weight.",
        positions=["WR", "QB"],
    ),
    Rule(
        name="TE Year-3 Leap",
        conditions=[RuleCondition(field="years_exp", operator="==", value=2)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.10),
        description=(
            "Boosts all third-year TEs for the expected breakout (not draft-capital "
            "gated). Unlike WRs (whose breakout peaks in Year 2), TE breakout is a "
            "Year-3 phenomenon. Supporting evidence subset: first-time-TE1 rates for "
            "TEs drafted in the first two rounds jump from ~11% (Year 1) to ~17% "
            "(Year 2) to ~38% (Year 3) per Footballguys hit-rate data. +10% at "
            "default weight."
        ),
        positions=["TE"],
    ),
    # Rookie RBs are the one position where draft capital is the dominant public
    # predictor of Year-1 fantasy hit rate (2026 rookie-class analysis converges:
    # FantasyPros, RotoBaller, Fantasy Life). Gated to first-year backs drafted in
    # the first two rounds. UDFA / day-3 backs (draft_round None or >2) do NOT
    # fire — a None draft_round is a non-match under the engine's
    # "unknown field = no match" convention (_evaluate), locked by a unit test.
    # Magnitude mirrors "Sophomore Leap" (+8%). See the autotiers-ff-knowledge
    # "Draft Capital Is the Dominant Predictor of Rookie RB Hit Rate" entry.
    Rule(
        name="Rookie RB Draft Capital",
        conditions=[
            RuleCondition(field="position", operator="==", value="RB"),
            RuleCondition(field="years_exp", operator="==", value=0),
            RuleCondition(field="draft_round", operator="<=", value=2),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.08),
        description=(
            "Boosts rookie RBs (years_exp==0) drafted in the first two rounds — "
            "draft capital is the most predictive public signal for rookie RB "
            "hit rate. UDFA / day-3 backs (draft_round None or >2) do not fire. "
            "+8% at default weight."
        ),
        positions=["RB"],
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
        description="Penalizes players past their position's typical decline age: RB >=28, WR >=31, TE >=31, K >=40. QB depends on rushing volume — dual-threat QBs (60+ prior-season rush attempts) >=31, pocket passers >=38. DST excluded. -15% at default weight.",
        positions=["QB", "RB", "WR", "TE", "K"],
    ),
    Rule(
        name="Projection Unavailable",
        conditions=[RuleCondition(field="projection_unavailable", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.50),
        description="Heavy penalty for players with no current-season projection from any source - data confidence is low. -50% at default weight.",
    ),
    # The high-volume RB "curse" is age-conditioned, not flat: recent workload
    # studies (Fantasy Football For Winners 2025, Fantasy Life 2025) show RBs
    # first absorbing a 400+ touch load at ages 21–26 decline ~24% in next-year
    # PPG on average, vs ~37% at age 27+. So we split the old flat 0.90 rule into
    # two mutually-exclusive age bands sharing the same prior_touches>=370 gate.
    # Coefficients (0.87 young / 0.75 veteran) are dampened from the raw study
    # deltas — the base projection already prices in some regression, so passing
    # the raw decline through would double-count. See issue #498 and the
    # autotiers-ff-knowledge "370 Touches" entry.
    #
    # NOTE: an RB whose `age` is unknown (None) fires NEITHER band — `_evaluate`
    # treats a None field as a non-match. This is intentional: a 370+ touch
    # workhorse essentially always has a known age, and defaulting a missing-age
    # player into a penalty band would be guessing. Locked by a unit test.
    Rule(
        name="370 Touches (Young RB)",
        conditions=[
            RuleCondition(field="position", operator="==", value="RB"),
            RuleCondition(field="prior_touches", operator=">=", value=370),
            RuleCondition(field="age", operator="<=", value=26),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.87),
        description=(
            "Penalizes younger RBs (age <=26) who absorbed 370+ touches "
            "(carries + receptions) last season — a leading indicator of "
            "decline. The workhorse curse is age-conditioned: young backs "
            "recover better, so this band is milder than the veteran band. "
            "-13% at default weight."
        ),
        positions=["RB"],
    ),
    Rule(
        name="370 Touches (Veteran RB)",
        conditions=[
            RuleCondition(field="position", operator="==", value="RB"),
            RuleCondition(field="prior_touches", operator=">=", value=370),
            RuleCondition(field="age", operator=">=", value=27),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.75),
        description=(
            "Penalizes veteran RBs (age >=27) who absorbed 370+ touches "
            "(carries + receptions) last season — the workhorse curse is "
            "steepest for older backs (~37% avg next-year decline vs ~24% for "
            "younger). -25% at default weight. Calibrated to co-fire with "
            "'Over the Hill' for RBs age >=28 (combined ~-36%); that "
            "compounding is intentional, not a bug."
        ),
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
    Rule(
        name="Cold-Weather Kicker",
        conditions=[RuleCondition(field="cold_weather_kicker", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.96),
        description=(
            "Penalizes kickers on consistently cold outdoor home venues where Nov–Jan "
            "game-time temperatures and wind regularly impair field goal accuracy "
            "(Burke/Advanced Football Analytics 2012: 30°F cold ≈ 5 yd distance penalty; "
            "PFF: 20+ mph wind reduces kicker output from 8.3 to 7.7 fpg). "
            "Teams: GB, BUF, NE, CHI, CLE, PIT, CIN, KC. "
            "Excludes domes and DEN (altitude bonus modeled separately). "
            "-4% at default weight."
        ),
        positions=["K"],
    ),
]
