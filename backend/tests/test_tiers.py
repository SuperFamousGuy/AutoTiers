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


def test_highest_score_gets_rank_one():
    players = [
        _player("a", "RB", 300.0),
        _player("b", "WR", 350.0),
        _player("c", "QB", 250.0),
    ]
    result = assign_tiers(players)
    by_rank = {p.overall_rank: p for p in result}
    assert by_rank[1].player_id == "b"
    assert by_rank[2].player_id == "a"
    assert by_rank[3].player_id == "c"


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
    players = [
        _player("a", "RB", 400.0),
        _player("b", "WR", 395.0),
        _player("c", "RB", 100.0),
        _player("d", "WR", 95.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    assert by_id["a"].overall_tier == by_id["b"].overall_tier
    assert by_id["a"].overall_tier < by_id["c"].overall_tier


def test_single_player_per_position_gets_tier_one():
    players = [_player("q1", "QB", 350.0)]
    result = assign_tiers(players)
    assert result[0].positional_tier == "QB1"


def test_empty_input_returns_empty():
    result = assign_tiers([])
    assert result == []
