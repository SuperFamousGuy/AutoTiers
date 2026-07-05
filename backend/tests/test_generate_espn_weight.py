"""End-to-end regression test for issue #502.

`GenerateRequest.weight_espn` is a real, validated field that participates in
the ``weights_sum_to_one`` validator, so a caller can allocate weight to it and
pass validation. Before the fix, ``POST /generate`` hardcoded
``espn_projection=None`` in its ``blend_scores`` call, so an "espn" Projection
row in the DB never reached the blend and ``weight_espn`` silently had zero
effect on the score — its budget was absorbed by the prior_year/consensus ratio
with no error.

These tests drive the *full* HTTP path and assert that an "espn" projection
persisted in the DB actually participates in the blend when ``weight_espn > 0``,
and that shifting weight onto ESPN visibly moves ``projected_score_raw``.

The seeded player carries two projection sources that disagree sharply:

    espn        = 300.0
    fantasypros = 100.0
    avg (consensus) = mean(300, 100) = 200.0

With no prior-year stat, the prior-year term is absent from the blend, so the
math reduces to a two-source weighted average:

    weight_espn=0.0, weight_consensus=1.0  -> 200.0            (ESPN excluded)
    weight_espn=0.5, weight_consensus=0.5  -> 0.5*300 + 0.5*200 = 250.0

Before the fix both requests returned 200.0 (ESPN inert); after it they diverge.
"""
import pytest
from app.models.player import Player
from app.models.projection import Projection


ESPN_PTS = 300.0
FP_PTS = 100.0
CONSENSUS = (ESPN_PTS + FP_PTS) / 2  # _avg_projection averages every source == 200.0


async def _seed_player_with_espn_and_consensus(test_db) -> str:
    """Seed a single WR with a divergent espn + fantasypros projection.

    No PlayerStat is seeded, so ``prior_year_actual`` is None and the prior-year
    term never enters the blend — isolating the ESPN-vs-consensus split as the
    only thing that moves ``projected_score_raw``.
    """
    pid = "wr_espn"
    test_db.add(Player(id=pid, name="Divergent Receiver", position="WR", team="AAA", age=26, years_exp=4))
    test_db.add(Projection(player_id=pid, source="espn", scoring_format="standard", projected_points=ESPN_PTS))
    test_db.add(Projection(player_id=pid, source="fantasypros", scoring_format="standard", projected_points=FP_PTS))
    await test_db.commit()
    return pid


def _body(weight_espn: float, weight_consensus: float) -> dict:
    return {
        "scoring_format": "standard",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4,
        "weight_prior_year": 0.0,
        "weight_espn": weight_espn,
        "weight_consensus": weight_consensus,
        "draft_rounds": 15,
        "rules": {},
    }


def _find(resp_json: dict, pid: str) -> dict:
    return next(p for p in resp_json["players"] if p["player_id"] == pid)


@pytest.mark.asyncio
async def test_espn_projection_participates_in_blend(async_client, test_db):
    """An "espn" DB row reaches blend_scores when weight_espn > 0 (#502).

    With weight_espn=0.0 the blend is the pure consensus (200.0); with
    weight_espn=0.5 the ESPN projection (300.0) pulls the raw score up to 250.0.
    Before the fix, espn_projection=None was hardcoded, so both requests
    returned 200.0 and this test would fail on the second assertion.
    """
    pid = await _seed_player_with_espn_and_consensus(test_db)

    r_no_espn = await async_client.post("/api/generate", json=_body(weight_espn=0.0, weight_consensus=1.0))
    assert r_no_espn.status_code == 200, r_no_espn.text
    no_espn = _find(r_no_espn.json(), pid)

    r_with_espn = await async_client.post("/api/generate", json=_body(weight_espn=0.5, weight_consensus=0.5))
    assert r_with_espn.status_code == 200, r_with_espn.text
    with_espn = _find(r_with_espn.json(), pid)

    # Both responses surface the ESPN projection value unchanged.
    assert no_espn["espn_projection"] == pytest.approx(ESPN_PTS)
    assert with_espn["espn_projection"] == pytest.approx(ESPN_PTS)

    # weight_espn=0.0 -> consensus only.
    assert no_espn["projected_score_raw"] == pytest.approx(CONSENSUS)

    # weight_espn=0.5 -> ESPN (300) and consensus (200) blended 50/50 == 250.
    expected_blend = 0.5 * ESPN_PTS + 0.5 * CONSENSUS
    assert with_espn["projected_score_raw"] == pytest.approx(expected_blend)

    # The regression guard: allocating weight to ESPN must move the score.
    assert with_espn["projected_score_raw"] > no_espn["projected_score_raw"]


@pytest.mark.asyncio
async def test_weight_espn_is_not_inert(async_client, test_db):
    """Two requests that differ *only* in the espn/consensus split must diverge.

    This is the precise property the issue calls out: a validated, API-accepted
    field must not have zero effect on the score. Before the fix these two
    requests returned identical ``projected_score_raw``.
    """
    pid = await _seed_player_with_espn_and_consensus(test_db)

    r_a = await async_client.post("/api/generate", json=_body(weight_espn=0.2, weight_consensus=0.8))
    r_b = await async_client.post("/api/generate", json=_body(weight_espn=0.8, weight_consensus=0.2))
    assert r_a.status_code == 200, r_a.text
    assert r_b.status_code == 200, r_b.text

    a = _find(r_a.json(), pid)["projected_score_raw"]
    b = _find(r_b.json(), pid)["projected_score_raw"]

    # ESPN (300) > consensus (200): the heavier ESPN weight yields a higher blend.
    assert b > a
    assert a == pytest.approx(0.2 * ESPN_PTS + 0.8 * CONSENSUS)
    assert b == pytest.approx(0.8 * ESPN_PTS + 0.2 * CONSENSUS)
