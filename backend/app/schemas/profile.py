"""Request/response shapes for /api/profiles."""
import json
import uuid
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.linked_league import LinkedLeagueOut

# Autosave POSTs/PATCHes settings_json and rules_json on every settings tweak,
# so an unbounded payload is a repeated write-amplification vector, not a
# one-off. Cap the serialized size of each JSON blob before it reaches Postgres.
# 64KB is far above any legitimate profile (real payloads are a few KB) while
# still rejecting megabyte-scale or deeply-nested abuse.
_MAX_JSON_BYTES = 64 * 1024


def _reject_oversized_json(value: Optional[dict], field_name: str) -> Optional[dict]:
    """Raise if `value` serializes to more than _MAX_JSON_BYTES of JSON.

    Measures the UTF-8 byte length of the JSON serialization as a conservative
    proxy for payload size / write amplification. It is not the exact on-disk
    size — Postgres stores JSONB in a binary format whose size differs from the
    UTF-8 length of the JSON text — but it reliably bounds the amount we accept
    and write on each autosave. Returns the value unchanged when within the cap
    (or None, for the optional fields on ProfileUpdate).
    """
    if value is None:
        return value
    size = len(json.dumps(value).encode("utf-8"))
    if size > _MAX_JSON_BYTES:
        raise ValueError(
            f"{field_name} is too large ({size} bytes); "
            f"maximum is {_MAX_JSON_BYTES} bytes."
        )
    return value


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
                return {**values, "rules_json": {}}
            else:
                # Do not mutate the ORM instance (object.__setattr__ bypasses
                # SQLAlchemy instrumentation but still affects the Python object,
                # which can cause surprising behaviour if the same instance is
                # accessed again later in the same request). Instead, extract all
                # field values into a plain dict and reset rules_json there.
                out = {field: getattr(values, field, None) for field in cls.model_fields}
                out["rules_json"] = {}
                return out
        return values


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    settings_json: dict[str, Any]
    rules_json: dict[str, list[dict[str, Any]]]

    @field_validator("settings_json", "rules_json")
    @classmethod
    def _bound_json_size(cls, value: dict, info) -> dict:
        return _reject_oversized_json(value, info.field_name)


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    settings_json: Optional[dict[str, Any]] = None
    rules_json: Optional[dict[str, list[dict[str, Any]]]] = None

    @field_validator("settings_json", "rules_json")
    @classmethod
    def _bound_json_size(cls, value: Optional[dict], info) -> Optional[dict]:
        return _reject_oversized_json(value, info.field_name)


class ProfilesListResponse(BaseModel):
    profiles: list[ProfileOut]
    active_profile_id: Optional[uuid.UUID]
