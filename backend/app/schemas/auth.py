"""Request and response shapes for /api/auth endpoints."""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, model_validator

# Re-export ProfileOut from profile.py so /me and /profiles share one schema.
# Earlier we had two separate ProfileOut classes — and only the /me copy carried
# linked_league. Every autosave PATCH returned the stripped /profiles copy,
# overwriting the in-memory linked_league. Single source of truth prevents
# that drift from happening again.
from app.schemas.profile import ProfileOut


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    initial_settings: Optional[dict[str, Any]] = None
    initial_rules: Optional[dict[str, list[dict[str, Any]]]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=10)


class UserOut(BaseModel):
    id: uuid.UUID
    email: Optional[str]
    yahoo_subject: Optional[str]
    google_subject: Optional[str]
    last_active_profile_id: Optional[uuid.UUID]
    yahoo_fantasy_connected: bool = False
    has_password: bool = False
    email_verified: bool = False
    password_changed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _compute_derived_fields(cls, data: Any) -> Any:
        if hasattr(data, "yahoo_access_token"):
            return {
                "id": data.id,
                "email": data.email,
                "yahoo_subject": data.yahoo_subject,
                "google_subject": data.google_subject,
                "last_active_profile_id": data.last_active_profile_id,
                "yahoo_fantasy_connected": data.yahoo_access_token is not None,
                "has_password": data.password_hash is not None,
                "email_verified": data.email_verified,
                "password_changed_at": data.password_changed_at,
            }
        return data


class MeResponse(BaseModel):
    user: UserOut
    profiles: list[ProfileOut]


__all__ = [
    "SignupRequest", "LoginRequest", "UserOut", "MeResponse", "ProfileOut",
    "ForgotPasswordRequest", "ResetPasswordRequest", "ChangePasswordRequest",
    "SetPasswordRequest",
]
