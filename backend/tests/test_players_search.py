"""Tests for GET /api/players?q=<name>.

Auth-gated. Returns matching players (id, name, position, team), capped
at 25 results.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.player import Player


async def _seed_players(test_db: AsyncSession):
    players = [
        Player(id="1", name="Saquon Barkley", position="RB", team="PHI"),
        Player(id="2", name="Christian McCaffrey", position="RB", team="SF"),
        Player(id="3", name="Justin Jefferson", position="WR", team="MIN"),
        Player(id="4", name="Jefferson Davis", position="WR", team="HOU"),
        Player(id="5", name="JaMarr Chase", position="WR", team="CIN"),
    ]
    for p in players:
        test_db.add(p)
    await test_db.commit()


async def _signup_and_login(async_client) -> None:
    await async_client.post("/api/auth/signup", json={
        "email": "search@example.com", "password": "password-long-enough",
    })


@pytest.mark.asyncio
async def test_search_requires_auth(async_client):
    r = await async_client.get("/api/players?q=jeff")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_search_basic_match(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=jefferson")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Justin Jefferson" in names
    assert "Jefferson Davis" in names
    assert "Saquon Barkley" not in names


@pytest.mark.asyncio
async def test_search_case_insensitive(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=BARKLEY")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Saquon Barkley" in names


@pytest.mark.asyncio
async def test_search_returns_required_fields(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=jefferson")
    items = r.json()
    assert items, "expected at least one match"
    first = items[0]
    assert set(first.keys()) >= {"id", "name", "position", "team"}


@pytest.mark.asyncio
async def test_search_empty_q_returns_400(async_client, test_db):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=")
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_search_caps_results_at_25(async_client, test_db):
    """Seed 30 players with similar names, expect at most 25 returned."""
    for i in range(30):
        test_db.add(Player(id=f"p{i}", name=f"Test Player {i}", position="WR", team="KC"))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=Test")
    assert r.status_code == 200
    assert len(r.json()) <= 25
