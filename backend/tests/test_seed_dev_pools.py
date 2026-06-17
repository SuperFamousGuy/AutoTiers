"""Guard the dev seed's RB/WR depth.

Issue #318: the dev seed (`backend/scripts/seed_dev.py`) used to hold only the
4 elite RBs and 4 elite WRs. With pools that thin, the VBD replacement rank
(RB30/WR30 at mult 2.5 in a 12-team league) clamps to the worst-of-4, which
inflates skill-position VBD and makes the dev board untrustworthy for
calibration. These tests lock in the expanded, smoothly-declining pools and
prove the replacement baseline now resolves to a real interior player rather
than the worst of the pool.
"""
from __future__ import annotations

import pytest

from app.engine.tiers import (
    TieredPlayer,
    _REPLACEMENT_MULTIPLIERS,
    _compute_vbd,
)
from scripts.seed_dev import PLAYERS

LEAGUE_SIZE = 12
SOURCES = ("ppr", "half_ppr", "standard")


def _pool(position: str) -> list[dict]:
    return [p for p in PLAYERS if p["position"] == position]


@pytest.mark.parametrize("position", ["RB", "WR"])
def test_pool_has_realistic_depth(position):
    """Each skill position carries ~30+ players so VBD has a real baseline."""
    assert len(_pool(position)) >= 30


def test_player_ids_are_unique():
    ids = [p["id"] for p in PLAYERS]
    assert len(ids) == len(set(ids)), "duplicate player ids in seed"


@pytest.mark.parametrize("position", ["RB", "WR"])
@pytest.mark.parametrize("fmt", SOURCES)
def test_projection_decline_is_monotone(position, fmt):
    """Sorted descending, every source's projection is non-increasing.

    Monotone in all three formats and both source feeds (espn, fantasypros) —
    no upward steps anywhere in the pool. (Strict decline through the depth tier
    is asserted separately; the elite tier may carry an occasional tie from the
    hand-tuned real-player values.)
    """
    pool = _pool(position)
    for source_idx in (0, 1):  # (espn, fantasypros)
        values = sorted((p["projections"][fmt][source_idx] for p in pool), reverse=True)
        for hi, lo in zip(values, values[1:]):
            assert hi >= lo, (
                f"{position} {fmt} source#{source_idx} not monotone: {hi} < {lo}"
            )


@pytest.mark.parametrize("position", ["RB", "WR"])
def test_depth_region_is_smooth_and_strictly_declining(position):
    """Below the elite tier the decline is strict with no cliffs.

    The replacement baseline reads from the mid/back of the pool, so the region
    that matters for VBD calibration must be smooth and tie-free. We check
    consecutive gaps among the depth players (PPR <= 240, the generated curve).
    """
    pool = _pool(position)
    depth = sorted(
        (p["projections"]["ppr"][0] for p in pool if p["projections"]["ppr"][0] <= 240.0),
        reverse=True,
    )
    assert len(depth) >= 20, "expected a populated depth tier below the elite players"
    gaps = [hi - lo for hi, lo in zip(depth, depth[1:])]
    assert min(gaps) > 0, f"{position} depth tier has a tie (gap of 0)"
    assert max(gaps) <= 15.0, f"{position} depth has a cliff of {max(gaps)} points"


def _tiered_from_seed() -> list[TieredPlayer]:
    """Build minimal TieredPlayer rows from the seed, scored by avg PPR projection."""
    players: list[TieredPlayer] = []
    for p in PLAYERS:
        espn, fp = p["projections"]["ppr"]
        avg = (espn + fp) / 2
        players.append(
            TieredPlayer(
                player_id=p["id"],
                name=p["name"],
                position=p["position"],
                team=p["team"],
                age=p["age"],
                adjusted_score=avg,
                projected_score_raw=avg,
                prior_year_actual=None,
                adp_standard=p["adp"].get("standard"),
                adp_ppr=p["adp"].get("ppr"),
                adp_dynasty=p["adp"].get("dynasty"),
                flags=[],
                rules_applied=[],
                overall_rank=0,
                overall_tier=0,
                positional_tier="",
            )
        )
    return players


@pytest.mark.parametrize("position", ["RB", "WR"])
def test_replacement_baseline_is_an_interior_player(position):
    """The VBD replacement is a real mid-pack player, not the clamped worst-of-pool.

    Runs the engine's actual `_compute_vbd` over the seed. The acceptance bug
    was that with <30 players the replacement index clamps to the last (worst)
    player; with the expanded pools the replacement rank lands strictly inside
    the pool, above the floor.
    """
    players = _tiered_from_seed()
    _compute_vbd(players, LEAGUE_SIZE)

    group = sorted(
        (p for p in players if p.position == position),
        key=lambda x: x.adjusted_score,
        reverse=True,
    )
    mult = _REPLACEMENT_MULTIPLIERS[position]
    replacement_rank = max(1, round(LEAGUE_SIZE * mult))  # 30 for RB/WR
    idx = min(replacement_rank - 1, len(group) - 1)

    # The pool is deep enough that the replacement rank is NOT clamped to the worst.
    assert idx < len(group) - 1, "pool too thin — replacement clamped to worst player"

    replacement_score = group[idx].adjusted_score
    worst_score = group[-1].adjusted_score
    assert replacement_score > worst_score, "replacement collapsed onto the worst player"

    # Every player's reported position_replacement matches that interior baseline.
    assert group[0].position_replacement == round(replacement_score, 2)
    # Top player has a positive, finite VBD edge over replacement.
    assert group[0].vbd_score > 0
