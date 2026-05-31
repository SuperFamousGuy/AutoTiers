"""Request and response shapes for /api/auth endpoints."""
import uuid
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field
from app.schemas.linked_league import LinkedLeagueOut


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    initial_settings: Optional[dict[str, Any]] = None
    initial_rules: Optional[list[dict[str, Any]]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: Optional[str]
    yahoo_subject: Optional[str]
    google_subject: Optional[str]
    last_active_profile_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserOut
    profiles: list["ProfileOut"]


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]
    linked_league: Optional[LinkedLeagueOut] = None

    model_config = {"from_attributes": True}


MeResponse.model_rebuild()
