"""Regression + feature tests for issue #852.

Two things were wrong before this change:

1. ``TieredPlayer`` / the response model exposed only ``adp_standard``,
   ``adp_ppr`` and ``adp_dynasty`` — a ``half_ppr`` generate (the most common
   format, and FantasyPros' own default) never surfaced its half-PPR ADP to the
   frontend even though ``FantasyProsFetcher`` already ingests it.
2. The overall-rank tiebreaker fell through ``else: "adp_standard"`` for
   ``scoring_format == half_ppr``, so equal-VBD players in a half-PPR draft were
   ordered by *non-PPR* ADP — diverging from the real half-PPR market for
   pass-catching backs and possession receivers.

These tests seed two players deliberately tied on VBD whose standard-ADP order
and half-PPR-ADP order are swapped, then assert the tiebreak follows the ADP
that matches the requested scoring format, and that the half-PPR ADP shows up in
the response.
"""
from datetime import datetime

import pytest

from app.models.adp import ADPData
from app.models.player import Player
from app.models.projection import Projection


CONSENSUS = 120.0

# "alpha" is earlier in standard/PPR ADP; "beta" is earlier in half-PPR ADP.
# The pair is tied on every scoring input, so ADP alone breaks the tie.
_ADP = {
    "alpha": {"standard": 1.0, "half_ppr": 20.0, "ppr": 1.0},
    "beta": {"standard": 20.0, "half_ppr": 1.0, "ppr": 20.0},
}


async def _seed_tied_pair(test_db):
    """Two identical WRs whose only difference is ADP ordering per format."""
    for pid in ("alpha", "beta"):
        test_db.add(Player(id=pid, name=pid.title(), position="WR", team="AAA", age=27, years_exp=5))
        for fmt in ("standard", "half_ppr", "ppr"):
            # Equal projection in every format => equal adjusted_score => equal VBD.
            test_db.add(Projection(player_id=pid, source="fantasypros",
                                   scoring_format=fmt, projected_points=CONSENSUS))
            test_db.add(ADPData(player_id=pid, format=fmt, adp=_ADP[pid][fmt],
                                adp_source="fantasypros",
                                last_updated=datetime.utcnow().date()))
    await test_db.commit()


def _body(scoring_format: str) -> dict:
    return {
        "scoring_format": scoring_format,
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.5,
        "weight_espn": 0.0,
        "weight_consensus": 0.5,
        "rules": {},
    }


def _rank(data: dict, pid: str) -> int:
    return next(p["overall_rank"] for p in data["players"] if p["player_id"] == pid)


def _find(data: dict, pid: str) -> dict:
    return next(p for p in data["players"] if p["player_id"] == pid)


@pytest.mark.asyncio
async def test_half_ppr_tiebreak_uses_half_ppr_adp(async_client, test_db):
    """Acceptance criterion 1: a half_ppr request ranks the tied player with the
    lower half-PPR ADP first — even though standard ADP orders the pair the
    other way."""
    await _seed_tied_pair(test_db)

    resp = await async_client.post("/api/generate", json=_body("half_ppr"))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # beta has the lower half-PPR ADP (1.0 vs 20.0), so it must rank ahead of
    # alpha. Before the fix this used standard ADP and alpha (1.0) won.
    assert _rank(data, "beta") < _rank(data, "alpha"), (
        "half_ppr tiebreak must follow half-PPR ADP, not standard ADP"
    )


@pytest.mark.asyncio
async def test_half_ppr_response_surfaces_adp_half_ppr(async_client, test_db):
    """Acceptance criterion 2: the response carries a populated adp_half_ppr for
    players with FantasyPros half-PPR ADP on file."""
    await _seed_tied_pair(test_db)

    resp = await async_client.post("/api/generate", json=_body("half_ppr"))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    alpha = _find(data, "alpha")
    beta = _find(data, "beta")
    assert alpha["adp_half_ppr"] == 20.0
    assert beta["adp_half_ppr"] == 1.0
    # The other formats stay populated too (not clobbered by the new field).
    assert alpha["adp_standard"] == 1.0
    assert beta["adp_standard"] == 20.0


@pytest.mark.asyncio
async def test_standard_and_ppr_tiebreak_unchanged(async_client, test_db):
    """Acceptance criterion 3: standard and ppr requests still tiebreak on their
    own ADP (alpha wins both), so the half_ppr branch didn't disturb them."""
    await _seed_tied_pair(test_db)

    for fmt in ("standard", "ppr"):
        resp = await async_client.post("/api/generate", json=_body(fmt))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # alpha has the lower standard/ppr ADP (1.0 vs 20.0) => ranks first.
        assert _rank(data, "alpha") < _rank(data, "beta"), (
            f"{fmt} tiebreak regressed: alpha (lower {fmt} ADP) should rank first"
        )
