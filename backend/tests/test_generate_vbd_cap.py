"""Issue #540: VBD replacement level must be computed against the full player
pool, not the roster-capped display set.

``_cap_and_assign_tiers`` (backend/app/api/generate.py) trims the drafted-caliber
pool down to a display roster via a per-position floor plus an overall-budget
top-up, THEN tiers it. Before the fix it re-derived VBD from that trimmed set, so
whenever the floor alone exceeded the overall cap (short ``draft_rounds``), RB/WR
groups were starved below their 2.5x replacement rank and the replacement
baseline silently inflated.

These tests drive the real cap helper with hand-built pools to prove the
replacement anchor now survives floor/budget starvation.
"""
from app.api.generate import _cap_and_assign_tiers
from app.engine.tiers import TieredPlayer


def _player(pid: str, position: str, score: float) -> TieredPlayer:
    return TieredPlayer(
        player_id=pid, name=f"Player {pid}", position=position,
        team="NE", age=25, adjusted_score=score,
        projected_score_raw=score, prior_year_actual=score,
        adp_standard=None, adp_ppr=None, adp_dynasty=None,
        flags=[], rules_applied=[],
        overall_rank=0, overall_tier=0, positional_tier="",
    )


def _starved_pool() -> list[TieredPlayer]:
    """A pool that forces floor >> cap for league_size=12, draft_rounds=8.

    per_position_min = 24, overall_cap = 96. Six positions each carrying >= 24
    players means the floor (144) alone exceeds the cap, so the budget top-up is
    zero and every position is frozen at exactly its top 24 — RB included, well
    short of the rank-30 replacement anchor.
    """
    players: list[TieredPlayer] = []
    # 40 RBs: scores 300, 299, ... 261. 30th-best (index 29) = 271.0.
    for i in range(40):
        players.append(_player(f"rb_{i}", "RB", 300.0 - i))
    # 24+ of every other position so the per-position floor is fully satisfied
    # and consumes the entire cap on its own.
    for i in range(30):
        players.append(_player(f"wr_{i}", "WR", 280.0 - i))
    for pos, top in (("QB", 250.0), ("TE", 200.0), ("K", 130.0), ("DST", 140.0)):
        for i in range(24):
            players.append(_player(f"{pos.lower()}_{i}", pos, top - i))
    return players


def test_replacement_survives_floor_budget_starvation():
    """league_size=12, draft_rounds=8: floor (144) > cap (96) so the RB group is
    frozen at 24 players, yet the RB replacement must still be the 30th-best RB
    from the FULL pool (271.0), not the 24th-best survivor (277.0)."""
    pool = _starved_pool()
    ranked = _cap_and_assign_tiers(
        pool,
        league_size=12,
        draft_rounds=8,
        tiebreak_adp_attr="adp_ppr",
        overall_tier_count=12,
        qb_starters=1,
    )

    rbs = [p for p in ranked if p.position == "RB"]
    # The display roster is starved below 30 RBs (24 = per_position_min).
    assert len(rbs) == 24, f"expected the cap to starve RBs to 24, got {len(rbs)}"

    top_rb = next(p for p in rbs if p.player_id == "rb_0")
    # True 30th-best RB across the full pool, NOT the worst of the 24 present.
    assert top_rb.position_replacement == 271.0, (
        f"replacement should be the 30th-best RB (271.0) from the full pool, "
        f"got {top_rb.position_replacement}"
    )
    # Worst survivor of the trimmed roster would have been 277.0 — the bug value.
    assert top_rb.position_replacement != 277.0
    assert top_rb.vbd_score == round(300.0 - 271.0, 2)


def test_large_pool_common_case_unaffected():
    """When draft_rounds is generous the 30th-best RB is inside the display set
    anyway, so the fix is a no-op for the common case: replacement is 271.0."""
    pool = _starved_pool()
    ranked = _cap_and_assign_tiers(
        pool,
        league_size=12,
        draft_rounds=15,  # cap 180 > floor 144: budget top-up pulls extra RBs
        tiebreak_adp_attr="adp_ppr",
        overall_tier_count=12,
        qb_starters=1,
    )
    rbs = [p for p in ranked if p.position == "RB"]
    assert len(rbs) >= 30, "generous draft_rounds should keep >= 30 RBs on the board"
    top_rb = next(p for p in rbs if p.player_id == "rb_0")
    assert top_rb.position_replacement == 271.0
