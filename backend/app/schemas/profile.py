"""Request/response shapes for /api/profiles."""
import uuid
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator

from app.schemas.linked_league import LinkedLeagueOut


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: dict[str, list[dict[str, Any]]]
    # The frontend stores PATCH/POST responses straight into the in-memory
    # profiles array (App.tsx `setProfiles(profiles.map(...))`). If we omit
    # linked_league here, every autosave silently strips the link from state
    # until the next /me — exactly the symptom users reported.
    linked_league: Optional[LinkedLeagueOut] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def migrate_rules_json(cls, values: Any) -> Any:
        """Convert old list-format rules_json to the new dict format.

        Existing stored profiles have rules_json as a flat list:
          [{ "name": "...", "enabled": true, "weight": 1.0, "positions": [...] }]

        The new format is a position-keyed dict:
          { "QB": [...], "RB": [...] }

        We cannot reliably convert old list overrides to per-position format
        (the semantics differ), so we discard old-format data and return an
        empty dict. Users will see rules at their defaults and can reconfigure
        per position. The first autosave will write the new format.
        """
        rj = values.get("rules_json") if isinstance(values, dict) else getattr(values, "rules_json", None)
        if isinstance(rj, list):
            if isinstance(values, dict):
                values["rules_json"] = {}
            else:
                object.__setattr__(values, "rules_json", {})
        return values


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    settings_json: dict[str, Any]
    rules_json: dict[str, list[dict[str, Any]]]


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    settings_json: Optional[dict[str, Any]] = None
    rules_json: Optional[dict[str, list[dict[str, Any]]]] = None


class ProfilesListResponse(BaseModel):
    profiles: list[ProfileOut]
    active_profile_id: Optional[uuid.UUID]
