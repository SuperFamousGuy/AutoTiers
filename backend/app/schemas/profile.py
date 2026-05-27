"""Request/response shapes for /api/profiles."""
import uuid
from typing import Optional, Any
from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]

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
