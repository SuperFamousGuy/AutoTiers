from typing import Literal
from pydantic import BaseModel, model_validator
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


class RuleOverrideSchema(BaseModel):
    """Minimal per-position rule override sent by the frontend in generate requests.

    The frontend sends only the rules that differ from built-in defaults,
    keyed by position in the GenerateRequest.rules dict. The backend applies
    these overrides on top of BUILTIN_RULES for each player's position.
    """
    name: str
    enabled: bool
    weight: float = 1.0
