"""Pydantic shapes for the linked-league API.

Note: credentials_encrypted is intentionally NOT exposed — it never crosses the wire.
"""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class LinkedLeagueOut(BaseModel):
    profile_id: uuid.UUID
    provider: str  # "sleeper" | "espn"
    league_id: str
    league_metadata_json: dict[str, Any]
    keepers_json: list[dict[str, Any]]
    adp_json: Optional[dict[str, float]]
    last_synced_at: datetime

    model_config = {"from_attributes": True}
