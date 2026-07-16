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
async def test_put_favorites_rejects_oversized_player_list(async_client: AsyncClient, test_db):
    """A list far above the cap is rejected at the schema boundary (422),
    before the dedup/blank-scan loop runs — not the domain-specific 409."""
    await _signup_and_login(async_client)
    huge = [str(i) for i in range(100_000)]
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": huge, "favorite_teams": [],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_team_list(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    huge = ["KC"] * 100_000
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": huge,
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_player_id_string(async_client: AsyncClient, test_db):
    """A single ~1 MB player-id string is rejected at validation (422), not 200."""
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["A" * 1_000_000], "favorite_teams": [],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_team_string(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["A" * 1_000_000],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_modestly_over_cap_still_returns_domain_409(async_client: AsyncClient, test_db):
    """A request only modestly over _PLAYER_CAP passes the schema bound and
    still reaches the domain-specific 409 with its 'too many' copy."""
    await _signup_and_login(async_client)
    modestly_over = [str(i) for i in range(25)]  # over the 20 cap, under the 200 schema bound
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": modestly_over, "favorite_teams": [],
    })
    assert r.status_code == 409, r.text
    assert "20" in r.json()["detail"]


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
