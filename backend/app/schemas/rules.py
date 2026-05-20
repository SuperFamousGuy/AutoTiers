from pydantic import BaseModel
from app.engine.rules import EffectType


class RuleConditionSchema(BaseModel):
    field: str
    operator: str
    value: float | int | str | bool


class RuleEffectSchema(BaseModel):
    type: EffectType
    value: float | str


class RuleSchema(BaseModel):
    name: str
    conditions: list[RuleConditionSchema]
    effect: RuleEffectSchema
    enabled: bool = True
    weight: float = 1.0
    is_builtin: bool = False
    category: str = "Custom"
