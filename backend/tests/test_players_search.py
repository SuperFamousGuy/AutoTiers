"""Tests for GET /api/players/search?q=<name>.

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
    r = await async_client.get("/api/players/search?q=jeff")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_search_basic_match(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/search?q=jefferson")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Justin Jefferson" in names
    assert "Jefferson Davis" in names
    assert "Saquon Barkley" not in names


@pytest.mark.asyncio
async def test_search_case_insensitive(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/search?q=BARKLEY")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Saquon Barkley" in names


@pytest.mark.asyncio
async def test_search_returns_required_fields(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/search?q=jefferson")
    items = r.json()
    assert items, "expected at least one match"
    first = items[0]
    assert set(first.keys()) >= {"id", "name", "position", "team"}


@pytest.mark.asyncio
async def test_search_empty_q_returns_400(async_client, test_db):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/search?q=")
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_search_caps_results_at_25(async_client, test_db):
    """Seed 30 players with similar names, expect at most 25 returned."""
    for i in range(30):
        test_db.add(Player(id=f"p{i}", name=f"Test Player {i}", position="WR", team="KC"))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/search?q=Test")
    assert r.status_code == 200
    assert len(r.json()) <= 25


# ── /batch tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_requires_auth(async_client):
    r = await async_client.get("/api/players/batch?ids=1,2")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_batch_returns_players_with_espn_id(async_client, test_db):
    test_db.add(Player(id="b1", name="Batch Player One", position="QB", team="KC", espn_id="99001"))
    test_db.add(Player(id="b2", name="Batch Player Two", position="WR", team="BUF", espn_id=None))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/batch?ids=b1,b2")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    by_id = {p["id"]: p for p in items}
    assert by_id["b1"]["espn_id"] == "99001"
    assert by_id["b2"]["espn_id"] is None
    # espn_id field must be present on all items
    for item in items:
        assert "espn_id" in item


@pytest.mark.asyncio
async def test_batch_preserves_request_order(async_client, test_db):
    test_db.add(Player(id="ord1", name="Order One", position="RB", team="SF"))
    test_db.add(Player(id="ord2", name="Order Two", position="TE", team="NO"))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/batch?ids=ord2,ord1")
    assert r.status_code == 200
    items = r.json()
    assert items[0]["id"] == "ord2"
    assert items[1]["id"] == "ord1"


@pytest.mark.asyncio
async def test_batch_empty_ids_returns_422(async_client):
    """Empty string violates min_length=1."""
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/batch?ids=")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_batch_too_many_ids_returns_400(async_client):
    await _signup_and_login(async_client)
    many_ids = ",".join(str(i) for i in range(21))
    r = await async_client.get(f"/api/players/batch?ids={many_ids}")
    assert r.status_code == 400
    assert r.json()["detail"] == "Too many IDs (max 20)."


@pytest.mark.asyncio
async def test_batch_unknown_ids_silently_omitted(async_client, test_db):
    test_db.add(Player(id="known1", name="Known Player", position="WR", team="PHI"))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/batch?ids=known1,unknown999")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == "known1"


@pytest.mark.asyncio
async def test_batch_all_unknown_returns_empty(async_client):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/batch?ids=ghost1,ghost2")
    assert r.status_code == 200
    assert r.json() == []


# ── espn_id in /search results ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_includes_espn_id_field(async_client, test_db):
    """Existing search endpoint must include espn_id (may be null)."""
    test_db.add(Player(id="s_espn", name="ESPN Player", position="WR", team="MIN", espn_id="12345"))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players/search?q=ESPN")
    assert r.status_code == 200
    items = r.json()
    assert items, "expected at least one match"
    assert items[0]["espn_id"] == "12345"
