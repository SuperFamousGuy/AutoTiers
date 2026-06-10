"""End-to-end test: generate flow respects the opportunity-score rules.

Uses a tiny in-memory DB and a hand-crafted set of players so we can
verify that the over-producer rule fires for a player we know is an
over-producer relative to the others.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.scoring import ScoringFormat, LeagueType
from app.schemas.generate import GenerateRequest
from app.api.generate import _run_generate


@pytest.mark.asyncio
async def test_over_producer_rule_fires_in_generate(test_db: AsyncSession):
    """Two WRs with the same opportunity but very different actual production.

    - Player A: 80 targets, 600 yards, 12 TDs, 10 RZ looks → massively
      over-produced TDs relative to red-zone share → high z → over-producer
      rule should fire.
    - Players B–E: 80 targets, 600 yards, 3–5 TDs → baseline.

    With only two WRs, the σ across the two would be small/degenerate; we
    add a few more middle-of-the-road WRs to anchor the distribution.
    """
    from app.models.player import Player, PlayerStat
    from app.models.projection import Projection

    season = 2025
    players_data = [
        # (player_id, targets, rec, yds, tds, rz_looks)
        ("A_overproducer", 80, 50, 600.0, 12, 10),  # 12 TDs, only 10 RZ looks → high z
        ("B_baseline_1",   80, 50, 600.0, 4,  10),
        ("C_baseline_2",   80, 50, 600.0, 5,  12),
        ("D_baseline_3",   80, 50, 600.0, 3,  10),
        ("E_baseline_4",   80, 50, 600.0, 4,  10),
    ]
    for pid, targets, rec, yds, tds, rz in players_data:
        p = Player(id=pid, name=pid, position="WR", team="ABC", age=26, years_exp=4)
        test_db.add(p)
        test_db.add(PlayerStat(
            player_id=pid, season=season - 1,
            targets=targets, receptions=rec, rec_yards=yds, rec_tds=tds,
            rush_att=0, rush_yards=0.0, rush_tds=0,
            pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
            snaps=900, snap_pct=0.8, carry_share=None, target_share=0.20,
            games_played=16, red_zone_looks=rz,
            actual_tds=tds, expected_tds=float(rz) * 0.4,
        ))
        # Minimal projection so player isn't flagged as "Projection Unavailable"
        test_db.add(Projection(
            player_id=pid, source="fantasypros",
            scoring_format="ppr", projected_points=180.0,
        ))
    await test_db.commit()

    req = GenerateRequest(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        # All players get the same 180-pt FantasyPros projection as their base score.
        # This removes the raw-score gap from differing TDs so that only rule
        # adjustments differentiate the adjusted_scores.
        weight_prior_year=0.0,
        weight_espn=0.0,
        weight_consensus=1.0,
        rules={},
        keepers=[],
    )
    tiered = await _run_generate(req, test_db)

    over = next(t for t in tiered if t.player_id == "A_overproducer")
    baseline = next(t for t in tiered if t.player_id == "B_baseline_1")

    # Over-producer should have had the rule applied — adjusted_score lower
    # than baseline despite identical receiving volume.
    assert "Opportunity Over-Producer" in over.rules_applied
    assert "Opportunity Over-Producer" not in baseline.rules_applied
    assert over.adjusted_score < baseline.adjusted_score
