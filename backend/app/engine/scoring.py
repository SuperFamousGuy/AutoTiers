from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ScoringFormat(str, Enum):
    STANDARD = "standard"
    HALF_PPR = "half_ppr"
    PPR = "ppr"
    TE_PREMIUM = "te_premium"


class LeagueType(str, Enum):
    STANDARD = "standard"
    DYNASTY = "dynasty"
    KEEPER = "keeper"


@dataclass
class LeagueSettings:
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_td_points: float
    bonus_100yd_rushing: bool
    bonus_100yd_receiving: bool
    bonus_first_downs: bool
    weight_prior_year: float
    weight_espn: float
    weight_consensus: float


@dataclass
class PlayerStats:
    targets: int
    receptions: int
    rec_yards: float
    rec_tds: int
    rush_att: int
    rush_yards: float
    rush_tds: int
    pass_att: int
    pass_yards: float
    pass_tds: int
    interceptions: int
    games_played: int


def calculate_fantasy_points(stats: PlayerStats, settings: LeagueSettings, position: str = "") -> float:
    pts = 0.0

    # Passing
    pts += stats.pass_yards * 0.04
    pts += stats.pass_tds * settings.qb_td_points
    pts -= stats.interceptions * 2.0

    # Rushing
    pts += stats.rush_yards * 0.1
    pts += stats.rush_tds * 6.0
    if settings.bonus_100yd_rushing and stats.rush_yards >= 100:
        pts += 3.0

    # Receiving — reception points depend on format and position
    if settings.scoring_format == ScoringFormat.PPR:
        rec_pts = 1.0
    elif settings.scoring_format == ScoringFormat.HALF_PPR:
        rec_pts = 0.5
    elif settings.scoring_format == ScoringFormat.TE_PREMIUM:
        rec_pts = 1.5 if position == "TE" else 1.0
    else:
        rec_pts = 0.0

    pts += stats.receptions * rec_pts
    pts += stats.rec_yards * 0.1
    pts += stats.rec_tds * 6.0
    if settings.bonus_100yd_receiving and stats.rec_yards >= 100:
        pts += 3.0

    return round(pts, 2)


def blend_scores(
    prior_year_actual: Optional[float],
    espn_projection: Optional[float],
    consensus_projection: Optional[float],
    settings: LeagueSettings,
) -> float:
    sources = [
        (prior_year_actual, settings.weight_prior_year),
        (espn_projection, settings.weight_espn),
        (consensus_projection, settings.weight_consensus),
    ]
    available = [(score, weight) for score, weight in sources if score is not None]
    if not available:
        return 0.0
    total_weight = sum(w for _, w in available)
    return round(sum(score * (weight / total_weight) for score, weight in available), 2)
