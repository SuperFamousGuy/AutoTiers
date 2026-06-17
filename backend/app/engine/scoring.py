from dataclasses import dataclass
from enum import Enum
from typing import Optional


# Discount ramp threshold (NOT the NFL schedule length, which is ~15-17 games for
# a healthy starter). This is the games_played value at which the prior-year term
# reaches its full configured weight: weight scales by clamp(games_played / 14).
# Set below a typical full schedule on purpose so near-full seasons still get full
# weight. Below it, last season's point TOTAL under-represents the player's true
# per-season value (the missing games are zeros baked into the total), so the
# prior-year term is down-weighted toward zero as games_played falls to 0.
# Calibrated so an injury-shortened McCaffrey-type season (~4 games) lands within
# ~1 tier of his projection-only score, while healthy 15-17 game seasons and
# rookies (no prior) are completely unaffected. See blend_scores().
FULL_SEASON_GAMES = 14


class ScoringFormat(str, Enum):
    STANDARD = "standard"
    HALF_PPR = "half_ppr"
    PPR = "ppr"


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
    # RESERVED: not yet scored — first-down data not available in PlayerStats
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


def _score_receiving(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Receiving points EXCLUDING TDs (yards + reception bonus + 100yd bonus)."""
    if settings.scoring_format == ScoringFormat.PPR:
        rec_pts = 1.0
    elif settings.scoring_format == ScoringFormat.HALF_PPR:
        rec_pts = 0.5
    else:
        rec_pts = 0.0
    pts = stats.receptions * rec_pts + stats.rec_yards * 0.1
    if settings.bonus_100yd_receiving and stats.rec_yards >= 100:
        pts += 3.0
    return pts


def _score_rushing(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Rushing points EXCLUDING TDs (yards + 100yd bonus)."""
    pts = stats.rush_yards * 0.1
    if settings.bonus_100yd_rushing and stats.rush_yards >= 100:
        pts += 3.0
    return pts


def _score_tds_only(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Total TD points (rushing + receiving). Passing TDs excluded — those are QB-only."""
    return (stats.rec_tds + stats.rush_tds) * 6.0


def _score_passing(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Passing points (QB-only). Includes pass yards, pass TDs, INTs."""
    return (
        stats.pass_yards * 0.04
        + stats.pass_tds * settings.qb_td_points
        - stats.interceptions * 2.0
    )


def calculate_fantasy_points(stats: PlayerStats, settings: LeagueSettings, position: str = "") -> float:
    """Total fantasy points across all categories. Behavior unchanged — this is now a sum of the component helpers."""
    pts = (
        _score_passing(stats, settings)
        + _score_rushing(stats, settings)
        + _score_tds_only(stats, settings)
        + _score_receiving(stats, settings)
    )
    return round(pts, 2)


def blend_scores(
    prior_year_actual: Optional[float],
    espn_projection: Optional[float],
    consensus_projection: Optional[float],
    settings: LeagueSettings,
    prior_year_games: Optional[int] = None,
    full_season_games: int = FULL_SEASON_GAMES,
) -> float:
    """Weighted blend of available projection sources with renormalization.

    Computes a weighted average over the *active* sources — those that are
    both non-None and have a weight strictly greater than zero. Missing sources
    have their weight redistributed proportionally across the sources that are
    present, preserving the relative importance ratios of the active sources.

    When all sources are present and active weights sum to exactly 1.0,
    the output is identical to a raw weighted sum — renormalization is a no-op.
    (The schema allows weights to sum within ±0.01 of 1.0; in that case the
    renormalized result will differ slightly from a raw weighted sum.)

    When a source is absent, its weight is not silently lost; the active sources
    share the full weight budget. A player missing one source is scored at the
    same scale as a fully-covered player — the "Projection Unavailable" builtin
    rule (builtin_rules.py) is the appropriate mechanism for expressing
    data-confidence uncertainty, as it is explicit and configurable.

    Edge cases:
    - All sources None or all weights zero: returns 0.0.
    - weight=0.0 for a source: that source is excluded from the active set even
      if its value is present (user explicitly disabled it).
    - value=0.0 is NOT treated as missing — a player who scored zero is distinct
      from one with no stats on record.

    Games-played discount on the prior-year term:
    - ``prior_year_games`` is the number of games behind ``prior_year_actual``.
      When provided and below ``full_season_games``, the prior-year weight is
      scaled by ``clamp(prior_year_games / full_season_games, 0, 1)`` BEFORE the
      active-set selection and renormalization. This corrects injury-shortened
      seasons whose point TOTAL understates true value (the missing games are
      zeros baked into the total) without pro-rating, which would inject
      small-sample per-game noise and double-count against the already
      injury-aware consensus projection.
    - ``prior_year_games=None`` (default) means "no games information" and applies
      NO discount — behaviour is identical to before this parameter existed. This
      keeps the function backward compatible for callers that do not pass games.
    - A scale of 0 (zero games) drops prior-year from the active set entirely; the
      blend converges to projection-only, exactly when the prior is least reliable.
    - Rookies have ``prior_year_actual=None`` and are unaffected regardless of games.
    """
    active: list[tuple[float, float]] = []
    if prior_year_games is None:
        prior_year_scale = 1.0
    elif full_season_games <= 0:
        prior_year_scale = 1.0
    else:
        prior_year_scale = min(1.0, max(0.0, prior_year_games / full_season_games))
    prior_year_weight = settings.weight_prior_year * prior_year_scale
    if prior_year_actual is not None and prior_year_weight > 0:
        active.append((prior_year_actual, prior_year_weight))
    if espn_projection is not None and settings.weight_espn > 0:
        active.append((espn_projection, settings.weight_espn))
    if consensus_projection is not None and settings.weight_consensus > 0:
        active.append((consensus_projection, settings.weight_consensus))

    total_weight = sum(w for _, w in active)
    if total_weight == 0.0:
        return 0.0
    return round(sum(v * w / total_weight for v, w in active), 2)
