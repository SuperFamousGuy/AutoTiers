import pytest


async def _signup(async_client, email: str = "a@b.com") -> None:
    r = await async_client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery"})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_profiles_returns_401_when_anonymous(async_client):
    async_client.cookies.clear()
    r = await async_client.get("/api/profiles")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_profiles_returns_empty_when_authenticated_with_no_profiles(async_client):
    await _signup(async_client)
    r = await async_client.get("/api/profiles")
    assert r.status_code == 200
    body = r.json()
    assert body["profiles"] == []
    assert body["active_profile_id"] is None


@pytest.mark.asyncio
async def test_create_profile_persists_and_returns(async_client):
    await _signup(async_client)
    r = await async_client.post("/api/profiles", json={
        "name": "PPR 12-team",
        "settings_json": {"scoring_format": "ppr", "league_size": 12},
        "rules_json": [{"name": "X", "enabled": True, "weight": 1.0}],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "PPR 12-team"


@pytest.mark.asyncio
async def test_create_profile_rejects_when_at_cap(async_client):
    await _signup(async_client)
    for i in range(5):
        r = await async_client.post("/api/profiles", json={
            "name": f"Slot {i}",
            "settings_json": {},
            "rules_json": [],
        })
        assert r.status_code == 201
    r = await async_client.post("/api/profiles", json={
        "name": "Sixth",
        "settings_json": {},
        "rules_json": [],
    })
    assert r.status_code == 409
    assert "limit" in r.json()["detail"].lower() or "max" in r.json()["detail"].lower()
