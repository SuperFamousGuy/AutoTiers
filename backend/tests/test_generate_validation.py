"""Payload-size bounds for the unauthenticated /api/generate endpoint (#690).

/api/generate requires no auth, so an anonymous caller can POST arbitrarily
large keepers/league_adp/rules payloads that the engine fully parses and
normalizes before any real work. GenerateRequest now caps each collection and
returns 422 on violation. These tests assert the exact boundary: just-over-cap
is rejected (422), just-under/at-cap is accepted (200).
"""
import pytest
from app.models import Player
from app.schemas.generate import (
    _MAX_KEEPERS,
    _MAX_KEEPER_NAME_LEN,
    _MAX_LEAGUE_ADP_ENTRIES,
    _MAX_LEAGUE_ADP_KEY_LEN,
    _MAX_RULE_POSITIONS,
    _MAX_RULE_OVERRIDES_PER_POSITION,
)
from app.schemas.rules import _MAX_RULE_NAME_LEN


async def _seed_two_players(test_db):
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
        "rules": {},
    }


# ---- keepers ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_keepers_at_cap_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "keepers": [f"Player {i}" for i in range(_MAX_KEEPERS)]}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_keepers_over_cap_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "keepers": [f"Player {i}" for i in range(_MAX_KEEPERS + 1)]}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_keeper_name_at_max_length_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "keepers": ["x" * _MAX_KEEPER_NAME_LEN]}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_keeper_name_over_max_length_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "keepers": ["x" * (_MAX_KEEPER_NAME_LEN + 1)]}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422


# ---- league_adp ------------------------------------------------------------

@pytest.mark.asyncio
async def test_league_adp_at_cap_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    adp = {f"Player {i}": float(i) for i in range(_MAX_LEAGUE_ADP_ENTRIES)}
    body = {**_base_body(), "league_adp": adp}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_league_adp_over_cap_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    adp = {f"Player {i}": float(i) for i in range(_MAX_LEAGUE_ADP_ENTRIES + 1)}
    body = {**_base_body(), "league_adp": adp}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_league_adp_key_at_max_length_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "league_adp": {"x" * _MAX_LEAGUE_ADP_KEY_LEN: 1.0}}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_league_adp_key_over_max_length_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    body = {**_base_body(), "league_adp": {"x" * (_MAX_LEAGUE_ADP_KEY_LEN + 1): 1.0}}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422


# ---- rules -----------------------------------------------------------------

def _override(name: str = "Projection Unavailable") -> dict:
    return {"name": name, "enabled": True, "weight": 1.0}


@pytest.mark.asyncio
async def test_rules_positions_at_cap_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    rules = {f"POS{i}": [_override()] for i in range(_MAX_RULE_POSITIONS)}
    body = {**_base_body(), "rules": rules}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_rules_positions_over_cap_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    rules = {f"POS{i}": [_override()] for i in range(_MAX_RULE_POSITIONS + 1)}
    body = {**_base_body(), "rules": rules}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rules_overrides_per_position_at_cap_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    rules = {"WR": [_override() for _ in range(_MAX_RULE_OVERRIDES_PER_POSITION)]}
    body = {**_base_body(), "rules": rules}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_rules_overrides_per_position_over_cap_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    rules = {"WR": [_override() for _ in range(_MAX_RULE_OVERRIDES_PER_POSITION + 1)]}
    body = {**_base_body(), "rules": rules}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rule_override_name_at_max_length_accepted(async_client, test_db):
    await _seed_two_players(test_db)
    rules = {"WR": [_override(name="x" * _MAX_RULE_NAME_LEN)]}
    body = {**_base_body(), "rules": rules}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_rule_override_name_over_max_length_rejected(async_client, test_db):
    await _seed_two_players(test_db)
    rules = {"WR": [_override(name="x" * (_MAX_RULE_NAME_LEN + 1))]}
    body = {**_base_body(), "rules": rules}
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 422
