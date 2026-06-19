"""End-to-end smoke test for per-position rule scoping through POST /generate.

This is the integration counterpart to the unit tests in
``test_per_position_rules_merge.py``. Those exercise ``_build_rules_for_position``
in isolation; this one drives the *full* path through the real HTTP endpoint
with no mocking of ``_build_rules_for_position`` or ``apply_rules``:

    client sends per-position rule override
        → ``_build_rules_for_position`` merges enabled/weight onto BUILTIN_RULES
        → ``apply_rules`` position gate decides per-player firing
        → ``rule_applications`` in the response reflects the result

It uses the ``RB Committee Penalty`` built-in, which is gated to
``positions=["RB"]`` and fires when ``carry_share < 0.50``. Every seeded
player is given a sub-threshold carry share AND the rule is explicitly
enabled under that player's own position key, so the *only* thing that can
stop the rule from firing on a WR/TE/QB is the engine's position gate — which
is exactly the behaviour under test.

Relates to PR #193 (per-position rule scoping); see issue #195.
"""
import pytest
from app.models.player import Player, PlayerStat
from app.models.projection import Projection


RESTRICTED_RULE = "RB Committee Penalty"  # built-in, positions=["RB"], carry_share < 0.50


async def _seed_one_per_position(test_db) -> None:
    """Seed one player at each of RB/WR/TE/QB.

    All four are given carry_share=0.30 (< the 0.50 RB Committee threshold) so
    that the rule's *condition* is satisfied for every player. That isolates
    the position gate as the sole reason the rule should be skipped for the
    non-RB players. Each gets a projection so the base score is well-defined.
    """
    players = [
        ("rb1", "Committee Back", "RB", "AAA"),
        ("wr1", "Slot Receiver", "WR", "BBB"),
        ("te1", "Move Tight End", "TE", "CCC"),
        ("qb1", "Pocket Passer", "QB", "DDD"),
    ]
    for pid, name, pos, team in players:
        test_db.add(Player(id=pid, name=name, position=pos, team=team, age=26, years_exp=4))
        test_db.add(PlayerStat(
            player_id=pid, season=2025,
            targets=60, receptions=40, rec_yards=500.0, rec_tds=3,
            rush_att=40, rush_yards=180.0, rush_tds=1,
            pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
            snaps=900, snap_pct=0.80, carry_share=0.30, target_share=0.18,
            games_played=16, red_zone_looks=8,
        ))
        test_db.add(Projection(
            player_id=pid, source="fantasypros",
            scoring_format="standard", projected_points=180.0,
        ))
    await test_db.commit()


def _body_enabling_restricted_rule_everywhere() -> dict:
    """A /generate request that enables the RB-only rule under every position key.

    Enabling it under WR/TE/QB as well as RB is deliberate: it proves the rule
    is suppressed by the engine's ``positions`` gate, not merely because no
    override happened to be supplied for those positions.
    """
    override = [{"name": RESTRICTED_RULE, "enabled": True, "weight": 1.0}]
    return {
        "scoring_format": "standard",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4,
        "weight_prior_year": 0.0,
        "weight_espn": 0.0,
        "weight_consensus": 1.0,
        "draft_rounds": 15,
        "rules": {"RB": override, "WR": override, "TE": override, "QB": override},
    }


@pytest.mark.asyncio
async def test_position_restricted_rule_fires_only_for_rb_through_generate(async_client, test_db):
    """The RB-only rule appears in rule_applications for the RB and no one else."""
    await _seed_one_per_position(test_db)

    r = await async_client.post("/api/generate", json=_body_enabling_restricted_rule_everywhere())
    assert r.status_code == 200, r.text
    players = {p["position"]: p for p in r.json()["players"]}

    # All four positions made it into the response (per-position floor is generous).
    assert set(players) == {"RB", "WR", "TE", "QB"}

    def applied_names(p):
        return {a["name"] for a in p["rule_applications"]}

    # RB: condition met + enabled + position gate allows it → rule fires.
    assert RESTRICTED_RULE in applied_names(players["RB"])
    assert RESTRICTED_RULE in players["RB"]["rules_applied"]

    # WR/TE/QB: condition met + enabled, but the engine position gate skips it.
    for pos in ("WR", "TE", "QB"):
        assert RESTRICTED_RULE not in applied_names(players[pos]), (
            f"{RESTRICTED_RULE} must not fire for {pos} — it is gated to RB only"
        )
        assert RESTRICTED_RULE not in players[pos]["rules_applied"]


@pytest.mark.asyncio
async def test_position_restricted_rule_actually_lowers_rb_score(async_client, test_db):
    """Belt-and-suspenders: the fired rule visibly changes the RB's adjusted score.

    Confirms the integration path doesn't just *record* the application but
    propagates the penalty (0.85x multiplier) into the scored output, while the
    non-RB players keep their raw score untouched by this rule.
    """
    await _seed_one_per_position(test_db)

    r = await async_client.post("/api/generate", json=_body_enabling_restricted_rule_everywhere())
    assert r.status_code == 200, r.text
    players = {p["position"]: p for p in r.json()["players"]}

    rb = players["RB"]
    # The RB Committee Penalty is a 0.85 multiplier at weight 1.0.
    rb_app = next(a for a in rb["rule_applications"] if a["name"] == RESTRICTED_RULE)
    assert rb_app["delta"] < 0
    assert rb["adjusted_score"] < rb["projected_score_raw"]

    # A non-RB player saw no application of this rule, so its delta from this
    # rule is simply absent — adjusted_score equals the raw projection.
    wr = players["WR"]
    assert all(a["name"] != RESTRICTED_RULE for a in wr["rule_applications"])
    assert wr["adjusted_score"] == wr["projected_score_raw"]
