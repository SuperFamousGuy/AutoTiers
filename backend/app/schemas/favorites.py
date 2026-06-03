"""Request/response shapes for /api/favorites."""
from pydantic import BaseModel, Field


class FavoritesUpdate(BaseModel):
    """PUT /favorites request body.

    Caps and team-validity are enforced in the API handler, not here, so
    error responses are domain-specific (Class 1: misleading error copy
    avoidance).
    """
    favorite_player_ids: list[str] = Field(default_factory=list)
    favorite_teams: list[str] = Field(default_factory=list)


class FavoritesOut(BaseModel):
    """GET /favorites response body."""
    favorite_player_ids: list[str]
    favorite_teams: list[str]

    model_config = {"from_attributes": True}
