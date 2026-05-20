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
    enabled: bool = True
    weight: float = 1.0
    is_builtin: bool = False
    category: str = "Custom"
