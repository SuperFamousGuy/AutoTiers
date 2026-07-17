from typing import Optional
from fastapi import APIRouter, Depends
from app.schemas.rules import RuleSchema, RuleConditionSchema, RuleEffectSchema
from app.engine.builtin_rules import BUILTIN_RULES
from app.models import User
from app.auth.dependencies import _get_current_user_impl

router = APIRouter()

_CATEGORIES = {
    "Over the Hill": "Age/Longevity",
    "RB Committee": "Usage",
    "Target Share": "Usage",
    "Declining Snap": "Usage",
    "New Team": "Situation",
    "New Head Coach": "Situation",
    "Sophomore Leap": "Situation",
    "TE Year-3 Leap": "Situation",
    "Rookie RB Draft Capital": "Situation",
    "Contract Year": "Situation",
    "Bad Offense": "Situation",
    "Follow the Money": "Situation",
    "Injury History": "Regression",
    "TD Regression": "Regression",
    "Opportunity": "Regression",
    "Red Zone": "Regression",
    "Projection Unavailable": "Regression",
    "370 Touches": "Regression",
    "Year After": "Regression",
    "Handcuff": "Flag",
    "Availability Risk": "Flag",
    "Favorites": "Personal",
    "Dome Kicker": "Situation",
    "Mile High Kicker": "Situation",
    "Cold-Weather Kicker": "Situation",
}


def _categorize(name: str) -> str:
    for prefix, cat in _CATEGORIES.items():
        if name.startswith(prefix):
            return cat
    return "Other"


@router.get("/rules", response_model=list[RuleSchema])
async def list_rules(
    current_user: Optional[User] = Depends(_get_current_user_impl),
) -> list[RuleSchema]:
    out: list[RuleSchema] = []
    for rule in BUILTIN_RULES:
        if rule.name == "Favorites" and current_user is None:
            continue
        out.append(RuleSchema(
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
            description=rule.description,
            positions=rule.positions,
        ))
    return out
