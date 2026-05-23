import pytest
from app.engine.tiers import TieredPlayer, assign_tiers


def _player(pid: str, position: str, score: float, **kwargs) -> TieredPlayer:
    return TieredPlayer(
        player_id=pid, name=f"Player {pid}", position=position,
        team="NE", age=25, adjusted_score=score,
        projected_score_raw=score, prior_year_actual=score,
        adp_standard=None, adp_ppr=None, adp_dynasty=None,
        flags=[], rules_applied=[],
        overall_rank=0, overall_tier=0, positional_tier="",
        **kwargs,
    )


def test_overall_rank_is_sequential_from_one():
    players = [_player(str(i), "RB", float(100 - i)) for i in range(10)]
    result = assign_tiers(players)
    ranks = sorted(p.overall_rank for p in result)
    assert ranks == list(range(1, 11))


def test_highest_vbd_gets_rank_one():
    """Ranking is by VBD (points above position replacement), not raw score.

    Seeded so each position has enough players for a real replacement-level
    baseline, and the top WR has the largest VBD margin.
    """
    players: list[TieredPlayer] = []
    # WRs: top scores 350 down; replacement (rank 30 for 12-team) ~50 → top VBD = 300
    for i in range(31):
        players.append(_player(f"wr_{i}", "WR", 350.0 - i * 10))
    # RBs: top 300 down; replacement (rank 30) ~5 → top VBD = 295
    for i in range(31):
        players.append(_player(f"rb_{i}", "RB", 300.0 - i * 10))
    # QBs: top 380 down; replacement (rank 12 for 12-team) = 270 → top VBD = 110
    for i in range(13):
        players.append(_player(f"qb_{i}", "QB", 380.0 - i * 10))
    result = assign_tiers(players, league_size=12)
    by_rank = {p.overall_rank: p for p in result}
    # Highest VBD is wr_0; second-highest is rb_0; qb_0 is well behind.
    assert by_rank[1].player_id == "wr_0"
    assert by_rank[2].player_id == "rb_0"
    qb0_rank = next(p.overall_rank for p in result if p.player_id == "qb_0")
    assert qb0_rank > 2


def test_positional_tier_label_uses_correct_position_prefix():
    players = [
        _player("wr1", "WR", 350.0),
        _player("wr2", "WR", 200.0),
        _player("rb1", "RB", 300.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    assert by_id["wr1"].positional_tier.startswith("WR")
    assert by_id["rb1"].positional_tier.startswith("RB")


def test_players_with_similar_scores_share_positional_tier():
    players = [
        _player("a", "WR", 350.0),
        _player("b", "WR", 348.0),
        _player("c", "WR", 150.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    # a and b are close, c is far away — a and b should share a tier
    assert by_id["a"].positional_tier == by_id["b"].positional_tier
    assert by_id["a"].positional_tier != by_id["c"].positional_tier


def test_clear_score_gap_creates_different_overall_tiers():
    # Enough players per position for VBD to produce a real spread.
    players: list[TieredPlayer] = []
    # 31 WRs: 400 → 100 (10pt steps). Replacement at rank 30 = 400 - 290 = 110.
    # Top WR VBD = 290; mid-pack WR VBD ~150; bottom WR VBD = 0.
    for i in range(31):
        players.append(_player(f"wr_{i}", "WR", 400.0 - i * 10))
    # 31 RBs: 395 → 95. Top RB VBD = 290; bottom RB VBD = 0.
    for i in range(31):
        players.append(_player(f"rb_{i}", "RB", 395.0 - i * 10))
    result = assign_tiers(players, league_size=12)
    by_id = {p.player_id: p for p in result}
    # Top WR and top RB share the top tier (similar high VBD).
    assert by_id["wr_0"].overall_tier == by_id["rb_0"].overall_tier
    # Worst-ranked players have much lower VBD → strictly lower tier number group
    assert by_id["wr_0"].overall_tier < by_id["wr_30"].overall_tier


def test_single_player_per_position_gets_tier_one():
    players = [_player("q1", "QB", 350.0)]
    result = assign_tiers(players)
    assert result[0].positional_tier == "QB1"


def test_empty_input_returns_empty():
    result = assign_tiers([])
    assert result == []


def test_vbd_subtracts_position_replacement():
    """Each player's vbd_score equals adjusted_score minus the position's replacement level.

    In a 12-team league, the QB replacement is QB12 (1-indexed → list index 11).
    """
    # 13 QBs with adjusted_score 400, 390, ... 280.
    players = [
        TieredPlayer(
            player_id=f"qb_{i}", name=f"QB{i}", position="QB", team="X", age=27,
            adjusted_score=400.0 - i * 10,
            projected_score_raw=400.0 - i * 10,
            prior_year_actual=None,
            adp_standard=float(i + 1), adp_ppr=float(i + 1), adp_dynasty=float(i + 1),
            flags=[], rules_applied=[],
            overall_rank=0, overall_tier=0, positional_tier="",
        )
        for i in range(13)
    ]
    ranked = assign_tiers(players, league_size=12, tiebreak_adp_attr="adp_ppr")
    # QB12 (index 11) score = 290 → replacement. Top QB VBD = 400 - 290 = 110.
    qb1 = next(p for p in ranked if p.player_id == "qb_0")
    qb12 = next(p for p in ranked if p.player_id == "qb_11")
    qb13 = next(p for p in ranked if p.player_id == "qb_12")
    assert qb1.vbd_score == 110.0
    assert qb12.vbd_score == 0.0
    assert qb13.vbd_score == -10.0
    assert qb1.position_replacement == 290.0


def test_vbd_ranking_top_rb_beats_top_qb():
    """Classic VBD: top RB with high VBD beats top QB with higher raw adjusted_score."""
    players: list[TieredPlayer] = []
    # 13 QBs: 400 → 280. Replacement (QB12 in 12-team) = QB at rank 12 = 290. Top QB VBD = 110.
    for i in range(13):
        players.append(TieredPlayer(
            player_id=f"qb_{i}", name=f"QB{i}", position="QB", team="X", age=27,
            adjusted_score=400.0 - i * 10, projected_score_raw=400.0 - i * 10,
            prior_year_actual=None,
            adp_standard=float(i + 1), adp_ppr=float(i + 1), adp_dynasty=None,
            flags=[], rules_applied=[],
            overall_rank=0, overall_tier=0, positional_tier="",
        ))
    # 31 RBs: 300 → 75. Replacement (RB30 in 12-team = round(12*2.5)=30) ~= 300 - 29*7.5 = 82.5. Top RB VBD ≈ 217.5.
    for i in range(31):
        players.append(TieredPlayer(
            player_id=f"rb_{i}", name=f"RB{i}", position="RB", team="X", age=27,
            adjusted_score=300.0 - i * 7.5, projected_score_raw=300.0 - i * 7.5,
            prior_year_actual=None,
            adp_standard=float(i + 1), adp_ppr=float(i + 1), adp_dynasty=None,
            flags=[], rules_applied=[],
            overall_rank=0, overall_tier=0, positional_tier="",
        ))
    ranked = assign_tiers(players, league_size=12, tiebreak_adp_attr="adp_ppr")
    top = ranked[0]
    # Top RB VBD should beat top QB VBD even though top QB has higher raw adjusted_score.
    assert top.player_id == "rb_0", f"Expected top RB at #1, got {top.player_id}"
