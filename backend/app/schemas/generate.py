from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.engine.scoring import ScoringFormat, LeagueType, PriorYearRamp, FULL_SEASON_GAMES
from app.engine.rules import EffectType
from app.schemas.rules import RuleOverrideSchema


class GenerateRequest(BaseModel):
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_starters: int = 1  # 1 = standard, 2 = superflex / 2-QB
    # Points awarded per passing TD (#582). Multiplied against stats.pass_tds in
    # scoring.py with no downstream clamp, so it is bounded here like every other
    # scoring knob. 0.0 covers leagues that don't reward passing TDs; standard is
    # 4, TD-heavy formats go up to 6, and 10 caps any realistic custom league.
    qb_td_points: float = Field(4.0, ge=0.0, le=10.0)
    bonus_100yd_rushing: bool = False
    bonus_100yd_receiving: bool = False
    bonus_first_downs: bool = False
    # TE Premium (#525): bonus points per tight-end reception, additive on top of
    # the base PPR/half-PPR reception value. Applies to TEs only in the engine.
    # Default 0.0 = off (backward compatible). Bounded to a realistic [0.0, 2.0]
    # range — Scott Fish Bowl and the common TEP formats sit at 0.5-1.0.
    te_premium_bonus: float = Field(0.0, ge=0.0, le=2.0)
    weight_prior_year: float = Field(0.30, ge=0.0)
    weight_espn: float = Field(0.0, ge=0.0)
    weight_consensus: float = Field(0.70, ge=0.0)
    # Prior-year games-played discount knobs (#315). full_season_games is the
    # games threshold below which last season's point total is treated as
    # injury-discounted; defaults to the engine's FULL_SEASON_GAMES so the
    # schema and scoring stay in lockstep. prior_year_ramp selects the discount
    # curve (linear vs. the more aggressive steep).
    full_season_games: int = Field(FULL_SEASON_GAMES, ge=1, le=17)
    prior_year_ramp: PriorYearRamp = PriorYearRamp.LINEAR
    draft_rounds: int = 15
    rules: dict[str, list[RuleOverrideSchema]] = Field(default_factory=dict)
    keepers: Optional[list[str]] = None
    league_adp: Optional[dict[str, float]] = None

    @field_validator("league_size")
    @classmethod
    def valid_league_size(cls, v: int) -> int:
        if v not in {8, 10, 12, 14, 16}:
            raise ValueError("league_size must be one of: 8, 10, 12, 14, 16")
        return v

    @field_validator("qb_starters")
    @classmethod
    def valid_qb_starters(cls, v: int) -> int:
        if v not in {1, 2}:
            raise ValueError("qb_starters must be 1 (standard) or 2 (superflex / 2-QB)")
        return v

    overall_tier_count: Optional[int] = None  # None -> defaults to league_size in the API layer

    @field_validator("draft_rounds")
    @classmethod
    def valid_draft_rounds(cls, v: int) -> int:
        if not (1 <= v <= 30):
            raise ValueError("draft_rounds must be between 1 and 30")
        return v

    @field_validator("overall_tier_count")
    @classmethod
    def valid_overall_tier_count(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 30):
            raise ValueError("overall_tier_count must be between 1 and 30")
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
    is_favorite_player: Optional[bool] = None
    is_favorite_team: Optional[bool] = None

    model_config = {"from_attributes": True}


class GenerateResponse(BaseModel):
    players: list[TieredPlayerOut]
    total: int
    data_as_of: Optional[str] = None
    # Sources that have been attempted but have never once succeeded
    # (last_attempted set, last_updated still NULL). These are silently absent
    # from data_as_of even though they contribute no data, so they are surfaced
    # here for the frontend to warn on instead of showing a clean banner (#547).
    never_succeeded: list[str] = Field(default_factory=list)
