import operator as _op
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EffectType(str, Enum):
    MULTIPLIER = "multiplier"
    FLAT_BONUS = "flat_bonus"
    FLAT_PENALTY = "flat_penalty"
    FLAG = "flag"


@dataclass
class RuleCondition:
    field: str
    operator: str  # ">", ">=", "<", "<=", "==", "!="
    value: Any


@dataclass
class RuleEffect:
    type: EffectType
    value: Any  # float for numeric effects, str for FLAG


@dataclass
class Rule:
    name: str
    conditions: list[RuleCondition]
    effect: RuleEffect
    enabled: bool = False
    weight: float = 1.0
    description: str = ""
    positions: list[str] | None = None  # None (or []) = apply to all positions


@dataclass
class PlayerContext:
    player_id: str
    position: str
    age: Optional[int]
    snap_pct: Optional[float]
    carry_share: Optional[float]
    target_share: Optional[float]
    games_played: Optional[int]
    years_exp: int
    adp: Optional[float]
    projected_score: float
    new_team: bool
    new_coach: bool
    actual_tds: Optional[int]
    expected_tds: Optional[float]
    actual_tds_above_expected: Optional[float] = None
    red_zone_looks: Optional[int] = None
    is_over_the_hill: Optional[bool] = None
    projection_unavailable: Optional[bool] = None
    prior_touches: Optional[int] = None
    injured_two_years_ago: Optional[bool] = None
    bad_offense_team: Optional[bool] = None
    above_market_contract: Optional[bool] = None
    opportunity_score_z: Optional[float] = None
    is_favorite: Optional[bool] = None
    plays_in_dome: Optional[bool] = None
    is_denver_kicker: Optional[bool] = None
    cold_weather_kicker: Optional[bool] = None


@dataclass
class RuleApplication:
    name: str
    effect_type: EffectType
    before_score: float
    after_score: float
    delta: float  # after - before; for FLAG type, this is 0.0


@dataclass
class RuleResult:
    adjusted_score: float
    flags: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    applications: list[RuleApplication] = field(default_factory=list)


_OPS = {
    ">": _op.gt, ">=": _op.ge,
    "<": _op.lt, "<=": _op.le,
    "==": _op.eq, "!=": _op.ne,
}


def _evaluate(condition: RuleCondition, ctx: PlayerContext) -> bool:
    val = getattr(ctx, condition.field, None)
    if val is None:
        return False
    op_fn = _OPS.get(condition.operator)
    if op_fn is None:
        return False
    return op_fn(val, condition.value)


def apply_rules(base_score: float, ctx: PlayerContext, rules: list[Rule]) -> RuleResult:
    score = base_score
    flags: list[str] = []
    applied: list[str] = []
    applications: list[RuleApplication] = []

    for rule in rules:
        if not rule.enabled:
            continue
        # Position gate: a non-empty positions list means the rule only fires
        # for players at one of those positions. None and [] both mean "all
        # positions" — the falsy check handles both without special-casing.
        if rule.positions:
            if ctx.position not in rule.positions:
                continue
        if not all(_evaluate(c, ctx) for c in rule.conditions):
            continue

        before = score
        effect = rule.effect
        if effect.type == EffectType.MULTIPLIER:
            distance = float(effect.value) - 1.0
            actual_multiplier = 1.0 + (distance * rule.weight)
            score *= actual_multiplier
        elif effect.type == EffectType.FLAT_BONUS:
            score += float(effect.value) * rule.weight
        elif effect.type == EffectType.FLAT_PENALTY:
            score -= float(effect.value) * rule.weight
        elif effect.type == EffectType.FLAG:
            flags.append(str(effect.value))

        applied.append(rule.name)
        applications.append(RuleApplication(
            name=rule.name,
            effect_type=effect.type,
            before_score=round(before, 2),
            after_score=round(score, 2),
            delta=round(score - before, 2),
        ))

    return RuleResult(
        adjusted_score=round(score, 2),
        flags=flags,
        rules_applied=applied,
        applications=applications,
    )
