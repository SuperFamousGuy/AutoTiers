"""Pydantic shapes for the linked-league API.

Note: credentials_encrypted is intentionally NOT exposed — it never crosses the wire.
"""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class LinkedLeagueOut(BaseModel):
    profile_id: uuid.UUID
    provider: str  # "sleeper" | "espn" | "yahoo" | "cbs"
    # league_id and the league-derived fields are None when the user pre-linked
    # a provider account without selecting a league.
    league_id: Optional[str]
    league_metadata_json: Optional[dict[str, Any]]
    keepers_json: Optional[list[dict[str, Any]]]
    adp_json: Optional[dict[str, float]]
    last_synced_at: datetime

    model_config = {"from_attributes": True}
