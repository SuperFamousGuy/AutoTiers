"""Request/response shapes for /api/profiles."""
import uuid
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.schemas.linked_league import LinkedLeagueOut


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]
    # The frontend stores PATCH/POST responses straight into the in-memory
    # profiles array (App.tsx `setProfiles(profiles.map(...))`). If we omit
    # linked_league here, every autosave silently strips the link from state
    # until the next /me — exactly the symptom users reported.
    linked_league: Optional[LinkedLeagueOut] = None

    model_config = {"from_attributes": True}


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    settings_json: Optional[dict[str, Any]] = None
    rules_json: Optional[list[dict[str, Any]]] = None


class ProfilesListResponse(BaseModel):
    profiles: list[ProfileOut]
    active_profile_id: Optional[uuid.UUID]
