"""Request/response shapes for /api/favorites."""
from pydantic import BaseModel, Field, field_validator

# The domain caps (_PLAYER_CAP=20, _TEAM_CAP=4) and the "too many favorites"
# 409 copy live in app/api/favorites_api.py so error responses stay
# domain-specific (Class 1: misleading error copy avoidance). Those checks run
# only AFTER Pydantic parses the whole list and _validate_and_normalize
# iterates every element (blank scan) and builds a dedup set. On this
# authenticated endpoint that leaves a DoS window: a caller can POST millions
# of ids (or a single multi-MB string) and force all that per-item work before
# the 409. Bound both collections here — length and per-item size — so an
# oversized payload is rejected during validation, before any per-item work,
# the same reasoning that capped generate.py's payloads in #673.
#
# The list bounds are a small multiple of the domain caps so a request that is
# only modestly over the cap still reaches the domain-specific 409 (with its
# "Too many favorite players/teams" copy) rather than a generic 422. The
# per-item bounds are far above any legitimate value — Sleeper player ids are a
# handful of digits and team abbreviations are 2-3 chars — so they only ever
# reject abusive payloads.
_MAX_PLAYER_IDS = 200
_MAX_PLAYER_ID_LEN = 100
_MAX_TEAMS = 40
_MAX_TEAM_LEN = 100


class FavoritesUpdate(BaseModel):
    """PUT /favorites request body.

    Caps and team-validity are enforced in the API handler, not here, so
    error responses are domain-specific (Class 1: misleading error copy
    avoidance).
    """
    favorite_player_ids: list[str] = Field(default_factory=list)
    favorite_teams: list[str] = Field(default_factory=list)

    # Both bounding validators run in mode="before" so the length checks
    # execute on the raw payload *before* Pydantic parses/coerces every element.
    # That ordering is the whole point: an oversized payload must be rejected
    # without first doing the per-item work (str coercion, blank scan, dedup
    # set) it is trying to trigger. Each validator type-guards the raw value and
    # passes anything unexpected through untouched so Pydantic still produces
    # its normal type-error for malformed input.
    @field_validator("favorite_player_ids", mode="before")
    @classmethod
    def bound_player_ids(cls, v):
        if isinstance(v, list):
            if len(v) > _MAX_PLAYER_IDS:
                raise ValueError(
                    f"favorite_player_ids has too many entries ({len(v)}); "
                    f"maximum is {_MAX_PLAYER_IDS}."
                )
            for pid in v:
                if isinstance(pid, str) and len(pid) > _MAX_PLAYER_ID_LEN:
                    raise ValueError(
                        f"a favorite player id is too long ({len(pid)} chars); "
                        f"maximum is {_MAX_PLAYER_ID_LEN}."
                    )
        return v

    @field_validator("favorite_teams", mode="before")
    @classmethod
    def bound_teams(cls, v):
        if isinstance(v, list):
            if len(v) > _MAX_TEAMS:
                raise ValueError(
                    f"favorite_teams has too many entries ({len(v)}); "
                    f"maximum is {_MAX_TEAMS}."
                )
            for t in v:
                if isinstance(t, str) and len(t) > _MAX_TEAM_LEN:
                    raise ValueError(
                        f"a favorite team is too long ({len(t)} chars); "
                        f"maximum is {_MAX_TEAM_LEN}."
                    )
        return v


class FavoritesOut(BaseModel):
    """GET /favorites response body."""
    favorite_player_ids: list[str]
    favorite_teams: list[str]

    model_config = {"from_attributes": True}
