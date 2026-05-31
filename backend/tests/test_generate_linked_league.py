import pytest
from sqlalchemy import select
from app.models import Player


async def _seed_two_players(test_db):
    """Minimal player seeding for keeper/adp tests. Adjust constructor args
    if Player's actual signature differs."""
    p1 = Player(id="p1", name="Justin Jefferson", position="WR", team="MIN")
    p2 = Player(id="p2", name="Christian McCaffrey", position="RB", team="SF")
    test_db.add_all([p1, p2])
    await test_db.commit()
    return p1, p2


def _base_body() -> dict:
    return {
        "scoring_format": "ppr",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.30,
        "weight_espn": 0.0,
        "weight_consensus": 0.70,
        "draft_rounds": 15,
        "rules": [],
    }


@pytest.mark.asyncio
async def test_generate_excludes_keepers_from_response(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "keepers": ["Justin Jefferson"]}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["players"]]
    assert "Justin Jefferson" not in names
    assert "Christian McCaffrey" in names


@pytest.mark.asyncio
async def test_generate_surfaces_league_adp_when_provided(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "league_adp": {"Justin Jefferson": 1.0, "Christian McCaffrey": 2.0}}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200
    players = r.json()["players"]
    jj = next(p for p in players if p["name"] == "Justin Jefferson")
    cmc = next(p for p in players if p["name"] == "Christian McCaffrey")
    assert jj["league_adp"] == 1.0
    assert cmc["league_adp"] == 2.0


@pytest.mark.asyncio
async def test_generate_without_linked_league_fields_works_unchanged(async_client, test_db):
    await _seed_two_players(test_db)
    r = await async_client.post("/api/generate", json=_base_body())
    assert r.status_code == 200
    for p in r.json()["players"]:
        # Field is present and null for every player when no league_adp was sent.
        assert p["league_adp"] is None
