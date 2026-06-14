from typing import Literal
from pydantic import BaseModel, field_validator, model_validator
from app.engine.rules import EffectType

VALID_OPERATORS = Literal[">", ">=", "<", "<=", "==", "!="]


class RuleConditionSchema(BaseModel):
    field: str
    operator: VALID_OPERATORS
    value: float | int | str | bool


class RuleEffectSchema(BaseModel):
    type: EffectType
    value: float | str

    @model_validator(mode="after")
    def validate_value_type(self) -> "RuleEffectSchema":
        if self.type in (EffectType.MULTIPLIER, EffectType.FLAT_BONUS, EffectType.FLAT_PENALTY):
            if not isinstance(self.value, (int, float)):
                raise ValueError(f"{self.type} effect requires a numeric value, got {type(self.value).__name__}")
        elif self.type == EffectType.FLAG:
            if not isinstance(self.value, str):
                raise ValueError("FLAG effect requires a string value")
        return self


_WEIGHT_BOUNDS_HELP = (
    "Rule weight must be between 0.0 and 2.0. "
    "Weights above 2.0 can invert penalty-rule multipliers (e.g. Projection "
    "Unavailable at weight > 2.0 drives the multiplier to zero or negative)."
)


class RuleSchema(BaseModel):
    name: str
    conditions: list[RuleConditionSchema]
    effect: RuleEffectSchema
    enabled: bool = False
    weight: float = 1.0
    is_builtin: bool = False
    category: str = "Custom"
    description: str = ""
    positions: list[str] | None = None  # None (or []) = apply to all positions

    @field_validator("weight")
    @classmethod
    def weight_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError(_WEIGHT_BOUNDS_HELP)
        return v


class RuleOverrideSchema(BaseModel):
    """Minimal per-position rule override sent by the frontend in generate requests.

    The frontend sends only the rules that differ from built-in defaults,
    keyed by position in the GenerateRequest.rules dict. The backend applies
    these overrides on top of BUILTIN_RULES for each player's position.
    """
    name: str
    enabled: bool
    weight: float = 1.0

    @field_validator("weight")
    @classmethod
    def weight_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError(_WEIGHT_BOUNDS_HELP)
        return v
