"""Endpoint tests for GET /favorites and PUT /favorites — CRUD layer only.

Auto-enable-rule-on-first-add behavior is covered separately in
test_favorites_auto_enable.py.
"""
import pytest
from httpx import AsyncClient


async def _signup_and_login(async_client: AsyncClient, email: str = "fav@example.com") -> None:
    """Helper: signup + login via cookie. async_client persists the auth
    cookie via its cookie jar."""
    await async_client.post("/api/auth/signup", json={
        "email": email, "password": "password-long-enough",
    })


@pytest.mark.asyncio
async def test_get_favorites_returns_empty_for_new_user(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/favorites")
    assert r.status_code == 200
    body = r.json()
    assert body == {"favorite_player_ids": [], "favorite_teams": []}


@pytest.mark.asyncio
async def test_get_favorites_requires_auth(async_client: AsyncClient):
    r = await async_client.get("/api/favorites")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_put_favorites_persists(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    }
    r = await async_client.get("/api/favorites")
    assert r.json() == {
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    }


@pytest.mark.asyncio
async def test_put_favorites_replaces_existing(async_client: AsyncClient, test_db):
    """Subsequent PUT fully replaces — not a merge."""
    await _signup_and_login(async_client)
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": ["KC"],
    })
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["9999"], "favorite_teams": ["BUF"],
    })
    assert r.status_code == 200
    assert r.json() == {"favorite_player_ids": ["9999"], "favorite_teams": ["BUF"]}


@pytest.mark.asyncio
async def test_put_favorites_rejects_over_player_cap(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    too_many = [str(i) for i in range(21)]
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": too_many, "favorite_teams": [],
    })
    assert r.status_code == 409
    assert "20" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_over_team_cap(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    too_many = ["KC", "BUF", "NYJ", "PHI", "DAL"]  # 5 teams
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": too_many,
    })
    assert r.status_code == 409
    assert "4" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_unknown_team(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["XYZ"],
    })
    assert r.status_code == 422
    assert "XYZ" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_whitespace_player_id(async_client: AsyncClient, test_db):
    """Class 2 guard: whitespace-only strings pass min_length but mean nothing."""
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["   "], "favorite_teams": [],
    })
    assert r.status_code == 422
    assert "blank" in r.json()["detail"].lower() or "empty" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_favorites_deduplicates(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "4046", "7564"],
        "favorite_teams": ["KC", "KC"],
    })
    assert r.status_code == 200
    assert r.json() == {"favorite_player_ids": ["4046", "7564"], "favorite_teams": ["KC"]}


@pytest.mark.asyncio
async def test_put_favorites_requires_auth(async_client: AsyncClient):
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 401
