import logging

import pytest
from app.engine import tiers as tiers_module
from app.engine.tiers import (
    TieredPlayer,
    assign_tiers,
    _jenks_interior_breaks,
    _quantile_breaks,
    _compute_overall_breaks,
    _qb_replacement_multiplier,
    _QB_SUPERFLEX_MULTIPLIER,
    _REPLACEMENT_MULTIPLIERS,
)


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
    # Need enough players for Jenks to stabilize breaks (>3 unique values helps).
    # 5 WRs in tier 1, 2 in tier 2: scores give clear gap for Jenks to find.
    players = [
        _player("a", "WR", 350.0),
        _player("b", "WR", 348.0),
        _player("d", "WR", 346.0),
        _player("e", "WR", 344.0),
        _player("f", "WR", 342.0),
        _player("c", "WR", 150.0),
        _player("g", "WR", 148.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    # a-f are tightly clustered near top (vbd ~200-190), c-g near bottom (vbd ~0).
    # Jenks should find a break separating top cluster from bottom cluster.
    # Within each cluster, similar scores should share a tier.
    assert by_id["a"].positional_tier == by_id["b"].positional_tier, (
        "Top-cluster players should share a tier"
    )
    # At least one high-score player should be in a different tier than low-score player.
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

    In a 12-team league with the recalibrated QB multiplier 0.67 (#310), the QB
    replacement rank is round(12 * 0.67) = 8, i.e. QB8 (1-indexed → list index 7).
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
    # QB8 (index 7) score = 400 - 7*10 = 330 → replacement (mult 0.67, #310).
    # Top QB VBD = 400 - 330 = 70. QB8 itself has VBD 0; QB9 (index 8) = -10.
    qb1 = next(p for p in ranked if p.player_id == "qb_0")
    qb8 = next(p for p in ranked if p.player_id == "qb_7")
    qb9 = next(p for p in ranked if p.player_id == "qb_8")
    assert qb1.vbd_score == 70.0
    assert qb8.vbd_score == 0.0
    assert qb9.vbd_score == -10.0
    assert qb1.position_replacement == 330.0


def test_qb_replacement_scales_with_qb_starters():
    """QB replacement rank deepens for superflex / 2-QB leagues (#319).

    start-1 (standard) anchors at the position's base QB multiplier; superflex
    (qb_starters=2) anchors at the deeper ``_QB_SUPERFLEX_MULTIPLIER``, while
    start-1 stays exactly where it was. Expected replacement scores are derived
    from those constants so the test keeps validating the *scaling* behaviour
    regardless of how either QB multiplier is calibrated.
    """
    LEAGUE, TOP, STEP = 12, 400.0, 10.0
    pool = [_player(f"qb_{i}", "QB", TOP - i * STEP) for i in range(24)]

    def expected_replacement(mult: float) -> float:
        # Mirrors compute_vbd_scores: replacement rank = round(league_size * mult).
        idx = max(1, round(LEAGUE * mult)) - 1
        return round(TOP - idx * STEP, 2)

    start1_repl = expected_replacement(_REPLACEMENT_MULTIPLIERS["QB"])
    superflex_repl = expected_replacement(_QB_SUPERFLEX_MULTIPLIER)

    # Standard start-1 (default) — anchors at the base QB multiplier.
    standard = assign_tiers([_player(p.player_id, "QB", p.adjusted_score) for p in pool], league_size=LEAGUE)
    s_qb1 = next(p for p in standard if p.player_id == "qb_0")
    assert s_qb1.position_replacement == start1_repl
    assert s_qb1.vbd_score == round(TOP - start1_repl, 2)

    # Explicit qb_starters=1 must match the default exactly.
    start1 = assign_tiers(
        [_player(p.player_id, "QB", p.adjusted_score) for p in pool],
        league_size=LEAGUE,
        qb_starters=1,
    )
    e_qb1 = next(p for p in start1 if p.player_id == "qb_0")
    assert e_qb1.position_replacement == s_qb1.position_replacement
    assert e_qb1.vbd_score == s_qb1.vbd_score

    # Superflex start-2 — replacement moves to the deeper anchor, VBD rises.
    superflex = assign_tiers(
        [_player(p.player_id, "QB", p.adjusted_score) for p in pool],
        league_size=LEAGUE,
        qb_starters=2,
    )
    sf_qb1 = next(p for p in superflex if p.player_id == "qb_0")
    assert sf_qb1.position_replacement == superflex_repl
    assert sf_qb1.vbd_score == round(TOP - superflex_repl, 2)
    # Superflex deepens the baseline → strictly higher VBD than start-1.
    assert sf_qb1.vbd_score > s_qb1.vbd_score


def test_qb_starters_only_affects_qb_replacement():
    """qb_starters must not change the replacement level of non-QB positions."""
    def pool():
        players = [_player(f"qb_{i}", "QB", 400.0 - i * 10) for i in range(24)]
        players += [_player(f"rb_{i}", "RB", 300.0 - i * 5) for i in range(40)]
        return players

    standard = {p.player_id: p for p in assign_tiers(pool(), league_size=12, qb_starters=1)}
    superflex = {p.player_id: p for p in assign_tiers(pool(), league_size=12, qb_starters=2)}

    # RB replacement (rank 30 = round(12 * 2.5)) is identical across formats.
    assert standard["rb_0"].position_replacement == superflex["rb_0"].position_replacement
    # QB replacement changed.
    assert standard["qb_0"].position_replacement != superflex["qb_0"].position_replacement


def test_qb_replacement_multiplier_helper():
    """start-1 reads the base QB multiplier; start-2+ uses the superflex anchor."""
    assert _qb_replacement_multiplier(1) == _REPLACEMENT_MULTIPLIERS["QB"]
    assert _qb_replacement_multiplier(2) == _QB_SUPERFLEX_MULTIPLIER
    # Defensive: any deeper start count still resolves to the superflex anchor.
    assert _qb_replacement_multiplier(3) == _QB_SUPERFLEX_MULTIPLIER


def test_vbd_ranking_top_rb_beats_top_qb():
    """Classic VBD: top RB with high VBD beats top QB with higher raw adjusted_score."""
    players: list[TieredPlayer] = []
    # 13 QBs: 400 → 280. Replacement (QB8 in 12-team, mult 0.67) = rank 8 = 330. Top QB VBD = 70.
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


class TestReplacementPoolDecoupling:
    """Issue #540: VBD replacement level must anchor on the full player pool,
    not on a display set that has been trimmed below the replacement rank."""

    def test_replacement_pool_anchors_on_full_pool_not_display_set(self):
        # 40 RBs, scores 300, 299, ... 261. RB replacement rank in a 12-team
        # league is round(12 * 2.5) = 30 -> the 30th-best RB (index 29) = 271.
        full = [_player(f"rb_{i}", "RB", 300.0 - i) for i in range(40)]
        # Display set is trimmed to the top 24 RBs (below the rank-30 anchor).
        display = full[:24]

        ranked = assign_tiers(display, league_size=12, replacement_pool=full)

        by_id = {p.player_id: p for p in ranked}
        # Only the 24 display players are returned/tiered.
        assert len(ranked) == 24
        # Replacement is the true 30th-best RB (271.0), NOT the worst survivor
        # of the trimmed display set (rb_23 = 277.0).
        assert by_id["rb_0"].position_replacement == 271.0
        assert by_id["rb_0"].vbd_score == round(300.0 - 271.0, 2)

    def test_replacement_pool_none_matches_computing_on_display_set(self):
        # With no replacement_pool, behaviour is unchanged: replacement is drawn
        # from the (small) set passed in — here the worst of the 24 present.
        full = [_player(f"rb_{i}", "RB", 300.0 - i) for i in range(40)]
        display = [_player(f"rb_{i}", "RB", 300.0 - i) for i in range(24)]

        ranked = assign_tiers(display, league_size=12)

        by_id = {p.player_id: p for p in ranked}
        # rank 30 clamps to len-1 = index 23 = 277.0 (the worst present).
        assert by_id["rb_0"].position_replacement == 277.0

    def test_replacement_pool_superset_leaves_display_ranking_intact(self):
        # The extra pool-only players must not appear in the ranked output.
        full = [_player(f"rb_{i}", "RB", 300.0 - i) for i in range(40)]
        display = full[:24]
        ranked = assign_tiers(display, league_size=12, replacement_pool=full)
        returned_ids = {p.player_id for p in ranked}
        assert returned_ids == {f"rb_{i}" for i in range(24)}
        # overall_rank is sequential over the display set only.
        assert sorted(p.overall_rank for p in ranked) == list(range(1, 25))

    def test_replacement_pool_missing_display_object_fails_fast(self):
        # If the pool does not contain the same TieredPlayer objects as the
        # display set, VBD is never written onto the display players and the
        # tiers would be silently wrong. assign_tiers must fail loudly instead.
        full = [_player(f"rb_{i}", "RB", 300.0 - i) for i in range(40)]
        # Same player_ids but distinct objects (copies), so identity differs.
        display = [_player(f"rb_{i}", "RB", 300.0 - i) for i in range(24)]

        with pytest.raises(ValueError, match="same TieredPlayer objects"):
            assign_tiers(display, league_size=12, replacement_pool=full)


def _kicker(pid: str, score: float, adp: float) -> TieredPlayer:
    return TieredPlayer(
        player_id=pid, name=f"K {pid}", position="K", team="X", age=27,
        adjusted_score=score, projected_score_raw=score, prior_year_actual=None,
        adp_standard=adp, adp_ppr=adp, adp_dynasty=adp,
        flags=[], rules_applied=[],
        overall_rank=0, overall_tier=0, positional_tier="",
    )


def test_quantile_fallback_when_jenks_finds_no_breaks():
    """Tight clusters with little variance still produce multiple tiers via quantile fallback."""
    # 14 kickers with very tightly clustered scores (within 10 points).
    # Jenks may or may not find breaks here; even if it doesn't, quantile fallback should.
    players = [_kicker(f"k_{i}", 130.0 - i * 0.7, float(i + 200)) for i in range(14)]
    ranked = assign_tiers(players, league_size=12, tiebreak_adp_attr="adp_ppr")
    positional_tiers = {p.positional_tier for p in ranked}
    # Expect at least 2 distinct K tiers (K1, K2) — POSITION_MAX_TIERS["K"] = 2
    assert len(positional_tiers) >= 2, (
        f"Expected K to have multiple tiers; got only {positional_tiers}"
    )


def test_quantile_fallback_handles_pure_ties():
    """If all scores are identical, fallback gracefully degrades to single tier."""
    players = [_kicker(f"k_{i}", 100.0, float(i + 200)) for i in range(14)]
    # Shouldn't crash; all players end up in tier 1 (no breaks possible).
    ranked = assign_tiers(players, league_size=12, tiebreak_adp_attr="adp_ppr")
    positional_tiers = {p.positional_tier for p in ranked}
    assert positional_tiers == {"K1"}


def test_cluster_position_with_two_value_clusters():
    """When players cluster into two distinct score groups (like K with rookies
    vs veterans), tier assignment should produce 2 tiers, not 1."""
    # 5 players at score 5.62 and 19 at 0.0 — mimics the K case
    players = []
    for i in range(5):
        players.append(TieredPlayer(
            player_id=f"k_top_{i}", name=f"KT{i}", position="K", team="X", age=27,
            adjusted_score=5.62, projected_score_raw=5.62,
            prior_year_actual=None,
            adp_standard=float(i + 200), adp_ppr=float(i + 200), adp_dynasty=float(i + 200),
            flags=[], rules_applied=[],
            overall_rank=0, overall_tier=0, positional_tier="",
        ))
    for i in range(19):
        players.append(TieredPlayer(
            player_id=f"k_bot_{i}", name=f"KB{i}", position="K", team="X", age=27,
            adjusted_score=0.0, projected_score_raw=0.0,
            prior_year_actual=None,
            adp_standard=float(i + 300), adp_ppr=float(i + 300), adp_dynasty=float(i + 300),
            flags=[], rules_applied=[],
            overall_rank=0, overall_tier=0, positional_tier="",
        ))
    ranked = assign_tiers(players, league_size=12, tiebreak_adp_attr="adp_ppr")
    tiers = {p.positional_tier for p in ranked}
    assert len(tiers) >= 2, f"Expected 2+ K tiers, got {tiers}"
    # Top group should be K1, bottom group K2
    top_player = next(p for p in ranked if p.player_id == "k_top_0")
    bot_player = next(p for p in ranked if p.player_id == "k_bot_0")
    assert top_player.positional_tier == "K1"
    assert bot_player.positional_tier == "K2"


# ---------------------------------------------------------------------------
# New tests for customizable overall_tier_count (Math spec §8 + INV-1..INV-6)
# ---------------------------------------------------------------------------

def _make_pool(n: int, position: str = "WR", score_start: float = 400.0, step: float = 5.0) -> list[TieredPlayer]:
    """Return n players from the same position with linearly declining scores."""
    return [_player(f"{position.lower()}_{i}", position, score_start - i * step) for i in range(n)]


def _large_pool() -> list[TieredPlayer]:
    """~270 players across WR/RB/QB/TE/K/DST — representative of a full draft pool.

    Uses slightly irrational step sizes (e.g. 3.71, 3.83) so VBD scores after
    replacement subtraction are almost entirely unique, giving the quantile
    algorithm real unique break points to work with.
    """
    players: list[TieredPlayer] = []
    # 90 WRs — step 3.71 to avoid integer-aligned collisions with RBs
    for i in range(90):
        players.append(_player(f"wr_{i}", "WR", round(400.0 - i * 3.71, 2)))
    # 90 RBs — step 3.83 (different from WRs)
    for i in range(90):
        players.append(_player(f"rb_{i}", "RB", round(390.0 - i * 3.83, 2)))
    # 32 QBs
    for i in range(32):
        players.append(_player(f"qb_{i}", "QB", round(370.0 - i * 7.13, 2)))
    # 32 TEs
    for i in range(32):
        players.append(_player(f"te_{i}", "TE", round(250.0 - i * 5.17, 2)))
    # 20 Ks
    for i in range(20):
        players.append(_player(f"k_{i}", "K", round(130.0 - i * 0.71, 2)))
    # 20 DSTs
    for i in range(20):
        players.append(_player(f"dst_{i}", "DST", round(140.0 - i * 1.03, 2)))
    return players


class TestOverallTierCountParam:
    """Math spec §8 implementation checklist: INV-1 through INV-6."""

    # INV-4: count=1 puts all players in overall_tier=1
    def test_overall_tier_count_one_puts_all_in_tier_1(self):
        players = _make_pool(20)
        result = assign_tiers(players, league_size=12, overall_tier_count=1)
        assert all(p.overall_tier == 1 for p in result), (
            "All players should be in tier 1 when overall_tier_count=1"
        )

    # INV-5: count > player pool degrades gracefully (no tier > len(players))
    def test_overall_tier_count_exceeds_player_pool(self):
        players = _make_pool(5)
        result = assign_tiers(players, league_size=12, overall_tier_count=50)
        max_tier = max(p.overall_tier for p in result)
        assert max_tier <= 5, (
            f"Max tier ({max_tier}) must not exceed player count (5)"
        )
        assert all(p.overall_tier >= 1 for p in result)

    # High tier count uses quantile path (count=15 > N*=11); all tiers 1..15 populated
    def test_overall_tier_count_high_uses_quantile_path(self):
        players = _large_pool()
        result = assign_tiers(players, league_size=12, overall_tier_count=15)
        tiers_present = {p.overall_tier for p in result}
        # All 15 tiers must be populated with no gaps. Asserting the exact set
        # 1..15 (not just max >= 10) catches a regression where overall_tier_count
        # is ignored and the count silently falls back to the old hardcoded 10.
        assert tiers_present == set(range(1, 16)), (
            f"Expected tiers 1..15 all populated, got: {sorted(tiers_present)}"
        )

    # Low tier count uses Jenks path (count=5 <= N*=11); clear score gap creates tier gap
    def test_overall_tier_count_low_uses_jenks_path(self):
        # 40 WRs: top 10 score 400-370 (cluster), bottom 30 score 200-140 (cluster)
        players = []
        for i in range(10):
            players.append(_player(f"wr_top_{i}", "WR", 400.0 - i * 3.0))
        for i in range(30):
            players.append(_player(f"wr_bot_{i}", "WR", 200.0 - i * 2.0))
        result = assign_tiers(players, league_size=12, overall_tier_count=5)
        by_id = {p.player_id: p for p in result}
        # Top WR should be in a strictly better (lower number) tier than the bottom WR
        assert by_id["wr_top_0"].overall_tier < by_id["wr_bot_29"].overall_tier, (
            "Top cluster should have a strictly better (lower) overall tier"
        )
        # All tiers must be >= 1
        assert all(p.overall_tier >= 1 for p in result)

    # INV-1: Tier numbers are 1..overall_tier_count (no 0, no count+1)
    def test_overall_tier_numbers_within_bounds(self):
        players = _large_pool()
        count = 15
        result = assign_tiers(players, league_size=12, overall_tier_count=count)
        for p in result:
            assert 1 <= p.overall_tier <= count, (
                f"Player {p.player_id} has overall_tier={p.overall_tier}, "
                f"expected 1..{count}"
            )

    # INV-2: Tier numbers are monotonic with VBD (higher VBD => equal or better tier)
    def test_overall_tier_numbers_monotonic_with_vbd(self):
        players = _large_pool()
        result = assign_tiers(players, league_size=12, overall_tier_count=10)
        sorted_by_vbd = sorted(result, key=lambda p: p.vbd_score, reverse=True)
        for a, b in zip(sorted_by_vbd, sorted_by_vbd[1:]):
            if a.vbd_score > b.vbd_score:
                assert a.overall_tier <= b.overall_tier, (
                    f"Monotonicity violated: player with higher VBD "
                    f"({a.vbd_score}) has worse tier ({a.overall_tier}) "
                    f"than player with lower VBD ({b.vbd_score}) tier ({b.overall_tier})"
                )

    # INV-6: Default backward compatibility — no overall_tier_count arg = same as count=10
    def test_backward_compat_default_matches_old_hardcoded_10(self):
        players = _large_pool()
        # Build two independent copies since assign_tiers mutates in place
        import copy
        pool_a = copy.deepcopy(players)
        pool_b = copy.deepcopy(players)
        result_default = assign_tiers(pool_a, league_size=12)
        result_explicit = assign_tiers(pool_b, league_size=12, overall_tier_count=10)
        tiers_default = {p.player_id: p.overall_tier for p in result_default}
        tiers_explicit = {p.player_id: p.overall_tier for p in result_explicit}
        assert tiers_default == tiers_explicit, (
            "Default overall_tier_count=10 must produce identical output to explicit 10"
        )


class TestQuantileBreaksDeduplicate:
    """Math spec §3: _quantile_breaks dedup fix — no overflow when n_classes > len(players)."""

    def test_no_overflow_when_classes_exceed_players(self):
        # 5 players with distinct scores, n_classes=20 → would overflow without dedup
        scores = [10.0, 8.0, 6.0, 4.0, 2.0]
        breaks = _quantile_breaks(scores, n_classes=20)
        # With dedup, we get at most 4 breaks (len - 1)
        assert len(breaks) <= 4, f"Expected <= 4 breaks, got {len(breaks)}: {breaks}"
        # All break values must be unique
        assert len(breaks) == len(set(breaks)), "Duplicate break values found"

    def test_five_players_twenty_classes_tier_count(self):
        # Per math spec example: 5 players, n_classes=20 should produce tiers 1..5 (not 1,3,5,7,9)
        players = [_player(f"p{i}", "WR", float(10 - i * 2)) for i in range(5)]
        result = assign_tiers(players, league_size=12, overall_tier_count=20)
        tiers_present = {p.overall_tier for p in result}
        # With 5 strictly-decreasing distinct scores, dedup must yield exactly
        # tiers 1..5 (one per player). Asserting the full set rather than
        # max_tier <= 5 catches over-collapsing where dedup drops real breaks.
        assert tiers_present == {1, 2, 3, 4, 5}, (
            f"Expected tiers 1..5 (one per player), got: {sorted(tiers_present)}"
        )

    def test_dedup_identical_to_normal_when_classes_within_bounds(self):
        # With 270 players and 15 classes, dedup should not change anything
        scores = [float(270 - i) for i in range(270)]
        breaks_15 = _quantile_breaks(scores, n_classes=15)
        assert len(breaks_15) == 14, f"Expected 14 breaks, got {len(breaks_15)}"
        assert len(set(breaks_15)) == 14, "Unexpected duplicates in normal case"

    def test_empty_scores_returns_empty(self):
        assert _quantile_breaks([], n_classes=5) == []

    def test_single_score_returns_empty(self):
        assert _quantile_breaks([5.0], n_classes=5) == []

    def test_n_classes_one_returns_empty(self):
        assert _quantile_breaks([5.0, 3.0], n_classes=1) == []


class TestComputeOverallBreaks:
    """Unit tests for the _compute_overall_breaks dispatcher."""

    def test_count_one_returns_no_breaks(self):
        scores = [10.0, 8.0, 6.0, 4.0, 2.0]
        breaks = _compute_overall_breaks(scores, overall_tier_count=1)
        assert breaks == []

    def test_count_below_threshold_uses_jenks(self):
        # Branch-sincerity proof: this fixture has only two unique values
        # (100.0 x20, 10.0 x20). Every quantile boundary lands on a tie and is
        # skipped, so _quantile_breaks returns [] here (asserted below). Jenks,
        # by contrast, finds the single meaningful gap between the clusters.
        # Therefore a NON-EMPTY result from the dispatcher proves it routed to
        # Jenks — if it had wrongly used quantile (the count>threshold branch),
        # breaks would be empty and this test would fail.
        scores = [100.0] * 20 + [10.0] * 20
        assert _quantile_breaks(scores, 5) == [], (
            "Fixture invariant: quantile must return [] so a non-empty dispatch "
            "result can only come from the Jenks branch"
        )
        breaks = _compute_overall_breaks(scores, overall_tier_count=5)
        assert len(breaks) >= 1

    def test_count_above_threshold_uses_quantile(self):
        # count=15 > 11: should use quantile, producing breaks at even intervals
        scores = [float(100 - i) for i in range(100)]
        breaks = _compute_overall_breaks(scores, overall_tier_count=15)
        assert len(breaks) == 14

    def test_count_exceeds_player_pool_clamps(self):
        # 5 players, count=50: clamped to 5
        scores = [10.0, 8.0, 6.0, 4.0, 2.0]
        breaks = _compute_overall_breaks(scores, overall_tier_count=50)
        assert len(breaks) <= 4

    def test_all_identical_scores_returns_empty(self):
        scores = [5.0] * 30
        breaks = _compute_overall_breaks(scores, overall_tier_count=10)
        assert breaks == []


# ---------------------------------------------------------------------------
# #310 regression: QB VBD recalibration (mult 1.0 -> 0.67, replacement QB8).
# Seeds a realistic 24-QB pool from scripts.seed_dev plus the elite skill
# players, runs the real assign_tiers, and locks the post-fix overall ordering.
# This test FAILS if _REPLACEMENT_MULTIPLIERS["QB"] reverts to 1.0 (the old
# behaviour put two QBs ahead of the consensus #1 WR).
# ---------------------------------------------------------------------------


def _seed_tiered_players():
    """Build TieredPlayers from the dev seed (24 QBs + elite RB/WR), using the
    PPR espn projection as adjusted_score (the seed's controlled, smooth ladder)."""
    from scripts.seed_dev import PLAYERS

    out: list[TieredPlayer] = []
    for p in PLAYERS:
        espn = p["projections"]["ppr"][0]
        out.append(TieredPlayer(
            player_id=p["id"], name=p["name"], position=p["position"], team=p["team"],
            age=p["age"], adjusted_score=espn, projected_score_raw=espn,
            prior_year_actual=None, adp_standard=None, adp_ppr=p["adp"]["ppr"],
            adp_dynasty=None, flags=[], rules_applied=[],
            overall_rank=0, overall_tier=0, positional_tier="",
        ))
    return out


def _recalibration_fixture():
    """Controlled board for the QB-recalibration ordering gate.

    Builds from the dev seed but DROPS the generated RB/WR depth players
    (``*_depth_*``), leaving the 24-QB ladder and the hand-tuned elite skill
    players. The QB8 replacement baseline (rank-8 = 308) is what this test
    pins, so the QB pool must stay intact; the RB/WR depth is irrelevant to the
    recalibration and actively harmful here. Issue #318 expanded that depth,
    which correctly interleaves realistic skill players between the elite WR and
    the deflated QBs — true on the live board, but it would mask this gate.
    Decoupling keeps the exact top-3 assertion meaningful regardless of how deep
    the dev seed's RB/WR pools grow.
    """
    return [p for p in _seed_tiered_players() if "_depth_" not in p.player_id]


def test_seed_has_24_qbs_for_real_replacement_baseline():
    """Guard the Phase-1 fixture: the recalibration test is only meaningful if the
    seed carries a full QB pool. Fewer than 24 QBs degenerates the QB8 baseline."""
    players = _seed_tiered_players()
    qbs = [p for p in players if p.position == "QB"]
    assert len(qbs) >= 24, (
        f"Seed must carry >= 24 QBs so QB8 replacement is a real player; got {len(qbs)}"
    )


def test_310_qb_recalibration_locks_overall_ordering():
    """With mult=0.67 the QB8 baseline deflates elite-QB VBD enough that the
    consensus #1 WR (Ja'Marr Chase) ranks above every QB, and the top two QBs
    (Lamar, Allen) sit immediately below him in that exact order.

    Asserts the EXACT top-3 ids (not a bound): under the old mult=1.0 the order
    was Lamar, Allen, Chase — so this assertion is false unless the recalibration
    is in effect. Sincerity gate per bug-class #7.

    Uses ``_recalibration_fixture`` (seed minus RB/WR depth) so the gate stays
    pinned to the QB8 baseline and is unaffected by the dev seed's realistic
    skill-position depth (#318).
    """
    ranked = assign_tiers(_recalibration_fixture(), league_size=12, tiebreak_adp_attr="adp_ppr")
    by_rank = {p.overall_rank: p for p in ranked}

    # Exact top-3 ordering after the fix.
    assert by_rank[1].player_id == "wr_chase", f"#1 should be Chase, got {by_rank[1].name}"
    assert by_rank[2].player_id == "qb_jackson", f"#2 should be Lamar, got {by_rank[2].name}"
    assert by_rank[3].player_id == "qb_allen", f"#3 should be Allen, got {by_rank[3].name}"

    chase = next(p for p in ranked if p.player_id == "wr_chase")
    allen = next(p for p in ranked if p.player_id == "qb_allen")
    lamar = next(p for p in ranked if p.player_id == "qb_jackson")

    # The core invariant the recalibration buys: no QB out-ranks the elite WR.
    assert allen.overall_rank > chase.overall_rank, (
        "Allen must rank below Chase (elite WR) after QB recalibration"
    )
    assert lamar.overall_rank > chase.overall_rank, (
        "Lamar must rank below Chase (elite WR) after QB recalibration"
    )

    # The QB8 replacement baseline must be a real player (285.0 = Dak Prescott,
    # QB12 by projection but QB8 == rank-8 in the seed ladder is 308.0). Assert
    # the elite QBs' VBD reflects the QB8 (rank-8) baseline, not the degenerate
    # 2-QB fallback that would put replacement at the worst QB.
    # Seed QB ladder rank 8 (index 7) = 308.0 -> Lamar VBD = 400 - 308 = 92.
    assert lamar.vbd_score == 92.0, f"Lamar VBD should be 92.0 (QB8 baseline 308), got {lamar.vbd_score}"
    assert allen.vbd_score == 77.0, f"Allen VBD should be 77.0 (QB8 baseline 308), got {allen.vbd_score}"


class TestJenksInteriorBreaksFailureHandling:
    """The Jenks except was over-broad (`except (ValueError, Exception)`), so a
    NaN score, a None, or a jenkspy API break all silently collapsed into a
    single tier with no diagnostic trail (issue #505). These tests lock in the
    narrowed behaviour: ValueError is caught + logged as a real failure, the
    expected all-identical path stays quiet, and non-ValueError failures
    propagate loudly instead of being absorbed.
    """

    def test_all_identical_scores_stay_quiet(self, caplog):
        """All-identical scores are the legitimate single-tier path: no interior
        break, no warning (debug at most)."""
        with caplog.at_level(logging.DEBUG, logger="app.engine.tiers"):
            breaks = _jenks_interior_breaks([5.0, 5.0, 5.0, 5.0], max_classes=3)
        assert breaks == []
        # Never a warning for the expected path.
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_nan_score_is_caught_and_logged_as_warning(self, caplog):
        """A NaN leaking in from a bad projection makes jenkspy raise ValueError.
        We catch it, fall back to no interior breaks, and log a warning naming
        the context and score stats so the regression surfaces in logs."""
        nan = float("nan")
        scores = [10.0, 8.0, nan, 4.0, 2.0]
        with caplog.at_level(logging.WARNING, logger="app.engine.tiers"):
            breaks = _jenks_interior_breaks(scores, max_classes=3, context="WR positional")
        assert breaks == []
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        assert "jenks_breaks failed" in msg
        assert "WR positional" in msg  # context is named
        assert "5 scores" in msg       # score count reported

    def test_inf_score_excluded_from_reported_finite_stats(self, caplog):
        """A +inf score (like NaN) makes jenkspy raise ValueError. The warning's
        min/max are reported over *finite* scores only, so ±inf must not leak
        into the reported range (#680). The old `s == s` filter dropped NaN but
        let ±inf through and skewed the max."""
        scores = [10.0, 8.0, float("inf"), 4.0, 2.0]
        with caplog.at_level(logging.WARNING, logger="app.engine.tiers"):
            breaks = _jenks_interior_breaks(scores, max_classes=3, context="RB positional")
        assert breaks == []
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        # Finite stats: min over the finite subset (2.0), max over it (10.0).
        assert "min=2.0" in msg
        assert "max=10.0" in msg
        # The infinity must never appear in the reported range.
        assert "inf" not in msg

    def test_neg_inf_score_excluded_from_reported_finite_stats(self, caplog):
        """Symmetric to +inf: a -inf score is dropped from the finite min/max so
        it can't drag the reported minimum to -inf (#680)."""
        scores = [10.0, 8.0, float("-inf"), 4.0, 2.0]
        with caplog.at_level(logging.WARNING, logger="app.engine.tiers"):
            breaks = _jenks_interior_breaks(scores, max_classes=3, context="RB positional")
        assert breaks == []
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        assert "min=2.0" in msg
        assert "max=10.0" in msg
        assert "inf" not in msg

    def test_all_non_finite_scores_report_na(self, caplog):
        """When every non-identical score is non-finite there is nothing finite
        to report, so min/max fall back to "n/a" rather than raising on an empty
        sequence (#680)."""
        scores = [float("inf"), float("nan"), float("-inf")]
        with caplog.at_level(logging.WARNING, logger="app.engine.tiers"):
            breaks = _jenks_interior_breaks(scores, max_classes=3, context="overall")
        assert breaks == []
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        assert "min=n/a max=n/a" in msg

    def test_non_valueerror_propagates(self, monkeypatch):
        """A TypeError (e.g. a None score, or a future jenkspy API break) must NOT
        be silently absorbed — it propagates so a genuine bug is loud."""

        def boom(*args, **kwargs):
            raise TypeError("simulated jenkspy API break")

        monkeypatch.setattr(tiers_module.jenkspy, "jenks_breaks", boom)
        with pytest.raises(TypeError, match="simulated jenkspy API break"):
            _jenks_interior_breaks([10.0, 8.0, 6.0, 4.0], max_classes=3)

    def test_memoryerror_propagates(self, monkeypatch):
        """MemoryError is not a tiering-quality signal — it must propagate, not
        degrade silently into a single tier."""

        def boom(*args, **kwargs):
            raise MemoryError()

        monkeypatch.setattr(tiers_module.jenkspy, "jenks_breaks", boom)
        with pytest.raises(MemoryError):
            _jenks_interior_breaks([10.0, 8.0, 6.0, 4.0], max_classes=3)

    def test_valueerror_still_falls_back_to_quantile_end_to_end(self, caplog):
        """Even when jenkspy raises ValueError on a real player set, assign_tiers
        must still return tiered players (via the quantile fallback), not crash."""
        players = [_player(str(i), "WR", float(100 - i)) for i in range(12)]

        def raise_ve(*args, **kwargs):
            raise ValueError("simulated insufficient variance")

        # Force the ValueError path across all Jenks calls.
        import unittest.mock as mock
        with mock.patch.object(tiers_module.jenkspy, "jenks_breaks", side_effect=raise_ve):
            with caplog.at_level(logging.WARNING, logger="app.engine.tiers"):
                ranked = assign_tiers(players, league_size=12)
        # Players still get tiers from the quantile fallback.
        assert all(p.positional_tier.startswith("WR") for p in ranked)
        assert all(p.overall_tier >= 1 for p in ranked)
        # And the failure was surfaced, not swallowed.
        assert [r for r in caplog.records if r.levelno >= logging.WARNING]

