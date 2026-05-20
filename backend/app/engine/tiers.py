from dataclasses import dataclass
from typing import Optional
import jenkspy


POSITION_MAX_TIERS = {"QB": 3, "RB": 5, "WR": 5, "TE": 3, "K": 2, "DST": 3}


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


def _jenks_interior_breaks(scores: list[float], max_classes: int) -> list[float]:
    unique = sorted(set(scores), reverse=True)
    n_classes = min(max_classes, len(unique))
    if n_classes < 2:
        return []
    breaks = jenkspy.jenks_breaks(scores, n_classes=n_classes)
    return list(breaks[1:-1])  # drop min and max; keep interior breakpoints only


def _assign_tier_from_breaks(score: float, breaks: list[float], descending_scores: bool = True) -> int:
    tier = 1
    for bp in sorted(breaks, reverse=descending_scores):
        if score < bp:
            tier += 1
    return tier


def _cluster_position(players: list[TieredPlayer], position: str) -> None:
    max_tiers = POSITION_MAX_TIERS.get(position, 3)
    scores = [p.adjusted_score for p in players]
    breaks = _jenks_interior_breaks(scores, max_tiers)
    for p in players:
        tier_num = _assign_tier_from_breaks(p.adjusted_score, breaks)
        p.positional_tier = f"{position}{tier_num}"


def assign_tiers(all_players: list[TieredPlayer]) -> list[TieredPlayer]:
    if not all_players:
        return []

    # Step 1: positional clustering
    by_position: dict[str, list[TieredPlayer]] = {}
    for p in all_players:
        by_position.setdefault(p.position, []).append(p)
    for position, group in by_position.items():
        _cluster_position(group, position)

    # Step 2: overall ranking by adjusted score
    ranked = sorted(all_players, key=lambda p: p.adjusted_score, reverse=True)
    for rank, player in enumerate(ranked, start=1):
        player.overall_rank = rank

    # Step 3: overall tier clustering
    all_scores = [p.adjusted_score for p in ranked]
    overall_breaks = _jenks_interior_breaks(all_scores, max_classes=10)
    for p in ranked:
        p.overall_tier = _assign_tier_from_breaks(p.adjusted_score, overall_breaks)

    return ranked
