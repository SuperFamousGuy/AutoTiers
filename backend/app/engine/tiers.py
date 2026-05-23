from dataclasses import dataclass, field
from typing import Optional
import jenkspy

from app.engine.rules import RuleApplication


POSITION_MAX_TIERS = {"QB": 3, "RB": 5, "WR": 5, "TE": 3, "K": 2, "DST": 3}

# Position-aware replacement rank multipliers applied to league_size, then
# rounded to the nearest integer. The player at the resulting rank within the
# position is the replacement-level player whose adjusted_score is subtracted
# off when computing VBD.
_REPLACEMENT_MULTIPLIERS = {
    "QB": 1.0,
    "RB": 2.5,
    "WR": 2.5,
    "TE": 1.25,
    "K": 1.0,
    "DST": 1.0,
}


@dataclass
class TieredPlayer:
    player_id: str
    name: str
    position: str
    team: Optional[str]
    age: Optional[int]
    adjusted_score: float
    projected_score_raw: float
    prior_year_actual: Optional[float]
    adp_standard: Optional[float]
    adp_ppr: Optional[float]
    adp_dynasty: Optional[float]
    flags: list[str]
    rules_applied: list[str]
    overall_rank: int
    overall_tier: int
    positional_tier: str
    espn_projection: Optional[float] = None
    fantasypros_projection: Optional[float] = None
    adp_implied: Optional[float] = None
    vbd_score: float = 0.0
    position_replacement: float = 0.0
    rule_applications: list[RuleApplication] = field(default_factory=list)


def _jenks_interior_breaks(scores: list[float], max_classes: int) -> list[float]:
    unique = sorted(set(scores), reverse=True)
    n_classes = min(max_classes, len(unique))
    if n_classes < 2:
        return []
    try:
        breaks = jenkspy.jenks_breaks(scores, n_classes=n_classes)
    except (ValueError, Exception):
        # All scores identical or insufficient variance — single tier
        return []
    return list(breaks[1:-1])  # drop min and max; keep interior breakpoints only


def _assign_tier_from_breaks(score: float, breaks: list[float], descending_scores: bool = True) -> int:
    tier = 1
    for bp in sorted(breaks, reverse=descending_scores):
        if score < bp:
            tier += 1
    return tier


def _cluster_position(players: list[TieredPlayer], position: str, max_tiers: int) -> None:
    scores = [p.vbd_score for p in players]
    breaks = _jenks_interior_breaks(scores, max_tiers)
    for p in players:
        tier_num = _assign_tier_from_breaks(p.vbd_score, breaks)
        p.positional_tier = f"{position}{tier_num}"


def _compute_vbd(all_players: list[TieredPlayer], league_size: int) -> None:
    """Compute ``vbd_score`` and ``position_replacement`` for each player, in place.

    Replacement is the Nth-best player at the position, where N is
    ``round(league_size * multiplier)`` (e.g. QB → league_size, RB/WR →
    league_size * 2.5, TE → league_size * 1.25). If the position has fewer
    than N players, the worst-ranked player is used as replacement.
    """
    by_position: dict[str, list[TieredPlayer]] = {}
    for p in all_players:
        by_position.setdefault(p.position, []).append(p)
    for pos, group in by_position.items():
        if not group:
            continue
        group.sort(key=lambda x: x.adjusted_score, reverse=True)
        mult = _REPLACEMENT_MULTIPLIERS.get(pos, 1.0)
        replacement_rank = max(1, round(league_size * mult))  # 1-indexed
        idx = min(replacement_rank - 1, len(group) - 1)
        replacement_score = group[idx].adjusted_score
        for p in group:
            p.position_replacement = round(replacement_score, 2)
            p.vbd_score = round(p.adjusted_score - replacement_score, 2)


def assign_tiers(
    all_players: list[TieredPlayer],
    league_size: int = 12,
    tiebreak_adp_attr: str = "adp_ppr",
) -> list[TieredPlayer]:
    if not all_players:
        return []

    # Compute VBD first; subsequent ranking and clustering use vbd_score.
    _compute_vbd(all_players, league_size)

    def _max_tiers(position: str) -> int:
        base = POSITION_MAX_TIERS.get(position, 3)
        scaled = max(1, round(base * league_size / 12))
        return min(scaled, base + 2)  # never more than base+2 even for large leagues

    # Step 1: positional clustering by vbd_score
    by_position: dict[str, list[TieredPlayer]] = {}
    for p in all_players:
        by_position.setdefault(p.position, []).append(p)
    for position, group in by_position.items():
        _cluster_position(group, position, _max_tiers(position))

    # Step 2: overall ranking by vbd_score, with format-appropriate ADP as tiebreaker
    ranked = sorted(
        all_players,
        key=lambda p: (-p.vbd_score, getattr(p, tiebreak_adp_attr, None) or 9999),
    )
    for rank, player in enumerate(ranked, start=1):
        player.overall_rank = rank

    # Step 3: overall tier clustering by vbd_score
    all_scores = [p.vbd_score for p in ranked]
    overall_breaks = _jenks_interior_breaks(all_scores, max_classes=10)
    for p in ranked:
        p.overall_tier = _assign_tier_from_breaks(p.vbd_score, overall_breaks)

    return ranked
