"""Opportunity-score (xFP) regression math.

Implements the spec at docs/superpowers/specs/2026-06-02-opportunity-score-regression-rule-design.md.

This module is pure math — no DB access, no FastAPI dependency, no async.
Callers (currently app.api.generate) pass in iterables of stat-like objects
that have the standard PlayerStat attribute names (targets, receptions,
rec_yards, rec_tds, rush_att, rush_yards, rush_tds, red_zone_looks,
games_played, position).
"""
from dataclasses import dataclass, field
from statistics import stdev
from typing import Optional, Protocol

from app.engine.scoring import (
    LeagueSettings,
    PlayerStats,
    _score_receiving,
    _score_rushing,
    _score_tds_only,
)


# Position-aware minimum total opportunity to be eligible for the rule.
# Players with fewer targets+carries+rz_looks than this are excluded
# (they're not in the regression distribution at all).
_MIN_OPPORTUNITY_BY_POSITION = {
    "WR": 50,
    "RB": 50,
    "TE": 20,
    "QB": 50,  # QBs can have rush opportunity; targets/rec_tds are usually 0
}

# Minimum games_played to contribute to league averages OR have z computed.
# Below this, the season is too injury-truncated to be a clean signal.
_MIN_GAMES_PLAYED = 8

# Positions for which we compute opportunity-score regression. K and DST
# excluded — they don't have target/carry/rz_look inputs.
_REGRESSION_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


class _StatLike(Protocol):
    """The attribute surface compute_* needs. Both ORM PlayerStat and test stubs match."""
    position: str
    targets: int
    receptions: int
    rec_yards: float
    rec_tds: int
    rush_att: int
    rush_yards: float
    rush_tds: int
    red_zone_looks: int
    games_played: int
    pass_att: int
    pass_yards: float
    pass_tds: int
    interceptions: int
    # fumbles_lost / two_pt_conversions are intentionally NOT part of the
    # required surface: the xFP math never reads them, and _to_player_stats
    # pulls them via getattr() so older stat stubs that predate these
    # attributes still satisfy the Protocol.


@dataclass(frozen=True)
class LeagueAverages:
    """Per-position averages of fantasy points per opportunity unit."""
    pts_per_target: dict[str, float] = field(default_factory=dict)
    pts_per_carry: dict[str, float] = field(default_factory=dict)
    pts_per_rz_look: dict[str, float] = field(default_factory=dict)


def _to_player_stats(s: _StatLike) -> PlayerStats:
    """Adapt a stat-like object to the scoring engine's PlayerStats dataclass."""
    return PlayerStats(
        targets=s.targets or 0,
        receptions=s.receptions or 0,
        rec_yards=s.rec_yards or 0.0,
        rec_tds=s.rec_tds or 0,
        rush_att=s.rush_att or 0,
        rush_yards=s.rush_yards or 0.0,
        rush_tds=s.rush_tds or 0,
        pass_att=s.pass_att or 0,
        pass_yards=s.pass_yards or 0.0,
        pass_tds=s.pass_tds or 0,
        interceptions=s.interceptions or 0,
        games_played=s.games_played or 1,
        # #663: carried through so PlayerStats is fully populated. Inert for the
        # xFP math itself (opportunity regression scores receiving/rushing/TDs
        # only, never turnovers), but keeps the adapter faithful to the source
        # object. getattr guards test stubs that predate these attributes.
        fumbles_lost=getattr(s, "fumbles_lost", 0) or 0,
        two_pt_conversions=getattr(s, "two_pt_conversions", 0) or 0,
        # #771: carried through for faithfulness. Inert for the xFP math (the
        # opportunity regression never reads first downs), but keeps the adapter
        # a complete copy of the source object. getattr guards test stubs that
        # predate these attributes.
        first_down_rush=getattr(s, "first_down_rush", 0) or 0,
        first_down_rec=getattr(s, "first_down_rec", 0) or 0,
    )


def compute_league_averages(
    stats: list[_StatLike], settings: LeagueSettings
) -> LeagueAverages:
    """Compute per-position league averages of pts/target, pts/carry, pts/rz_look.

    Only stats with games_played >= _MIN_GAMES_PLAYED contribute. Positions
    with zero denominator for a metric get 0.0 (the metric won't fire for
    that position; xFP will skip it).
    """
    targets_sum: dict[str, int] = {}
    rec_pts_sum: dict[str, float] = {}
    carries_sum: dict[str, int] = {}
    rush_pts_sum: dict[str, float] = {}
    rz_looks_sum: dict[str, int] = {}
    td_pts_sum: dict[str, float] = {}

    for s in stats:
        if (s.games_played or 0) < _MIN_GAMES_PLAYED:
            continue
        if s.position not in _REGRESSION_POSITIONS:
            continue
        ps = _to_player_stats(s)
        pos = s.position
        targets_sum[pos] = targets_sum.get(pos, 0) + ps.targets
        rec_pts_sum[pos] = rec_pts_sum.get(pos, 0.0) + _score_receiving(ps, settings, pos)
        carries_sum[pos] = carries_sum.get(pos, 0) + ps.rush_att
        rush_pts_sum[pos] = rush_pts_sum.get(pos, 0.0) + _score_rushing(ps, settings)
        rz_looks_sum[pos] = rz_looks_sum.get(pos, 0) + (s.red_zone_looks or 0)
        td_pts_sum[pos] = td_pts_sum.get(pos, 0.0) + _score_tds_only(ps, settings)

    def _safe_div(num: float, den: float) -> float:
        return num / den if den > 0 else 0.0

    return LeagueAverages(
        pts_per_target={pos: _safe_div(rec_pts_sum.get(pos, 0.0), targets_sum.get(pos, 0)) for pos in targets_sum},
        pts_per_carry={pos: _safe_div(rush_pts_sum.get(pos, 0.0), carries_sum.get(pos, 0)) for pos in carries_sum},
        pts_per_rz_look={pos: _safe_div(td_pts_sum.get(pos, 0.0), rz_looks_sum.get(pos, 0)) for pos in rz_looks_sum},
    )


def compute_xfp(stat: _StatLike, averages: LeagueAverages) -> Optional[float]:
    """Opportunity-implied fantasy points for one player.

    Returns None for positions we don't model (K, DST) or when no league
    averages exist for the player's position.
    """
    pos = stat.position
    if pos not in _REGRESSION_POSITIONS:
        return None
    pt = averages.pts_per_target.get(pos)
    pc = averages.pts_per_carry.get(pos)
    pr = averages.pts_per_rz_look.get(pos)
    if pt is None and pc is None and pr is None:
        return None
    targets = stat.targets or 0
    carries = stat.rush_att or 0
    rz = stat.red_zone_looks or 0
    return (
        targets * (pt or 0.0)
        + carries * (pc or 0.0)
        + rz * (pr or 0.0)
    )


def compute_per_position_sigmas(gaps_by_position: dict[str, list[float]]) -> dict[str, float]:
    """Sample standard deviation (ddof=1) of FP − xFP gaps, per position.

    Positions with fewer than 2 gap samples are omitted — sample stdev is
    undefined on a single point.
    """
    out: dict[str, float] = {}
    for pos, gaps in gaps_by_position.items():
        if len(gaps) >= 2:
            out[pos] = stdev(gaps)
    return out


def compute_opportunity_score_z(
    stat: _StatLike,
    averages: LeagueAverages,
    sigmas: dict[str, float],
    settings: LeagueSettings,
) -> Optional[float]:
    """Z-score of this player's (actual FP − xFP) gap against position σ_gap.

    Returns None when any of:
    - position is not in _REGRESSION_POSITIONS (K, DST)
    - games_played < _MIN_GAMES_PLAYED (small-sample)
    - total opportunity (targets + carries + rz_looks) below the position threshold
    - no σ for the position (too few players to estimate)
    - xFP cannot be computed (no averages for position)
    """
    pos = stat.position
    if pos not in _REGRESSION_POSITIONS:
        return None
    if (stat.games_played or 0) < _MIN_GAMES_PLAYED:
        return None
    opportunity = (stat.targets or 0) + (stat.rush_att or 0) + (stat.red_zone_looks or 0)
    if opportunity < _MIN_OPPORTUNITY_BY_POSITION.get(pos, 50):
        return None
    sigma = sigmas.get(pos)
    if sigma is None or sigma == 0:
        return None
    xfp = compute_xfp(stat, averages)
    if xfp is None:
        return None
    ps = _to_player_stats(stat)
    fp = (
        _score_receiving(ps, settings, pos)
        + _score_rushing(ps, settings)
        + _score_tds_only(ps, settings)
        # Passing intentionally excluded: xFP doesn't model passing
        # opportunity (we'd need pass_att, pass_attempts under pressure,
        # etc.). Keeping FP comparable means dropping passing here too.
    )
    return (fp - xfp) / sigma
