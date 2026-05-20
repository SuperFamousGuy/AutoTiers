from fastapi import APIRouter
from app.schemas.rules import RuleSchema, RuleConditionSchema, RuleEffectSchema
from app.engine.builtin_rules import BUILTIN_RULES

router = APIRouter()

_CATEGORIES = {
    "RB Age": "Age/Longevity",
    "WR Age": "Age/Longevity",
    "Dynasty Youth": "Age/Longevity",
    "RB Committee": "Usage",
    "Target Share": "Usage",
    "Red Zone": "Usage",
    "Declining Snap": "Usage",
    "New Team": "Situation",
    "New Head Coach": "Situation",
    "Sophomore Leap": "Situation",
    "Contract Year": "Situation",
    "Injury History": "Regression",
    "Handcuff": "Flag",
    "Availability Risk": "Flag",
}


def _categorize(name: str) -> str:
    for prefix, cat in _CATEGORIES.items():
        if name.startswith(prefix):
            return cat
    return "Other"


@router.get("/rules", response_model=list[RuleSchema])
async def list_rules() -> list[RuleSchema]:
    return [
        RuleSchema(
            name=rule.name,
            conditions=[
                RuleConditionSchema(field=c.field, operator=c.operator, value=c.value)
                for c in rule.conditions
            ],
            effect=RuleEffectSchema(type=rule.effect.type, value=rule.effect.value),
            enabled=rule.enabled,
            weight=rule.weight,
            is_builtin=True,
            category=_categorize(rule.name),
        )
        for rule in BUILTIN_RULES
    ]
