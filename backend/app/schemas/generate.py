from typing import Optional
from pydantic import BaseModel, field_validator
from app.engine.scoring import ScoringFormat, LeagueType
from app.schemas.rules import RuleSchema


class GenerateRequest(BaseModel):
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_td_points: float = 4.0
    bonus_100yd_rushing: bool = False
    bonus_100yd_receiving: bool = False
    bonus_first_downs: bool = False
    weight_prior_year: float = 0.40
    weight_espn: float = 0.30
    weight_consensus: float = 0.30
    rules: list[RuleSchema] = []

    @field_validator("league_size")
    @classmethod
    def valid_league_size(cls, v: int) -> int:
        if v not in {8, 10, 12, 14, 16}:
            raise ValueError("league_size must be one of: 8, 10, 12, 14, 16")
        return v

    @field_validator("weight_consensus")
    @classmethod
    def weights_sum_to_one(cls, weight_consensus: float, info) -> float:
        data = info.data
        total = data.get("weight_prior_year", 0) + data.get("weight_espn", 0) + weight_consensus
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Score weights must sum to 1.0, got {total:.2f}")
        return weight_consensus


class TieredPlayerOut(BaseModel):
    overall_rank: int
    player_id: str
    name: str
    position: str
    team: Optional[str]
    age: Optional[int]
    overall_tier: int
    positional_tier: str
    adjusted_score: float
    projected_score_raw: float
    prior_year_actual: Optional[float]
    adp_standard: Optional[float]
    adp_ppr: Optional[float]
    adp_dynasty: Optional[float]
    flags: list[str]
    rules_applied: list[str]


class GenerateResponse(BaseModel):
    players: list[TieredPlayerOut]
    total: int
    data_as_of: Optional[str] = None
