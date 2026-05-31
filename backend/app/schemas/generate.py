from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.engine.scoring import ScoringFormat, LeagueType
from app.engine.rules import EffectType
from app.schemas.rules import RuleSchema


class GenerateRequest(BaseModel):
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_td_points: float = 4.0
    bonus_100yd_rushing: bool = False
    bonus_100yd_receiving: bool = False
    bonus_first_downs: bool = False
    weight_prior_year: float = 0.30
    weight_espn: float = 0.0
    weight_consensus: float = 0.70
    draft_rounds: int = 15
    rules: list[RuleSchema] = Field(default_factory=list)
    keepers: Optional[list[str]] = None
    league_adp: Optional[dict[str, float]] = None

    @field_validator("league_size")
    @classmethod
    def valid_league_size(cls, v: int) -> int:
        if v not in {8, 10, 12, 14, 16}:
            raise ValueError("league_size must be one of: 8, 10, 12, 14, 16")
        return v

    @field_validator("draft_rounds")
    @classmethod
    def valid_draft_rounds(cls, v: int) -> int:
        if not (1 <= v <= 30):
            raise ValueError("draft_rounds must be between 1 and 30")
        return v

    @field_validator("weight_consensus")
    @classmethod
    def weights_sum_to_one(cls, weight_consensus: float, info) -> float:
        data = info.data
        total = (
            data.get("weight_prior_year", 0)
            + data.get("weight_espn", 0)
            + weight_consensus
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Score weights must sum to 1.0, got {total:.2f}")
        return weight_consensus


class RuleApplicationOut(BaseModel):
    name: str
    effect_type: EffectType
    before_score: float
    after_score: float
    delta: float


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
    espn_projection: Optional[float]
    fantasypros_projection: Optional[float]
    avg_projection: Optional[float]
    adp_standard: Optional[float]
    adp_ppr: Optional[float]
    adp_dynasty: Optional[float]
    league_adp: Optional[float] = None
    vbd_score: float
    position_replacement: float
    flags: list[str]
    rules_applied: list[str]
    rule_applications: list[RuleApplicationOut]

    model_config = {"from_attributes": True}


class GenerateResponse(BaseModel):
    players: list[TieredPlayerOut]
    total: int
    data_as_of: Optional[str] = None
