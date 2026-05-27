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


@pytest.mark.asyncio
async def test_patch_profile_updates_fields(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Original",
        "settings_json": {"league_size": 10},
        "rules_json": [],
    })
    pid = create.json()["id"]

    r = await async_client.patch(f"/api/profiles/{pid}", json={
        "name": "Renamed",
        "settings_json": {"league_size": 14},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["settings_json"]["league_size"] == 14
    assert body["rules_json"] == []


@pytest.mark.asyncio
async def test_patch_profile_403_when_other_user(async_client):
    await _signup(async_client, "alice@x.com")
    create = await async_client.post("/api/profiles", json={
        "name": "Alice's profile", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    await async_client.post("/api/auth/logout")
    await _signup(async_client, "bob@x.com")
    r = await async_client.patch(f"/api/profiles/{pid}", json={"name": "Hijack"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_profile_removes_row(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Doomed", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    r = await async_client.delete(f"/api/profiles/{pid}")
    assert r.status_code == 204

    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"] == []


@pytest.mark.asyncio
async def test_delete_profile_403_when_other_user(async_client):
    await _signup(async_client, "alice@x.com")
    create = await async_client.post("/api/profiles", json={
        "name": "Alice's", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    await async_client.post("/api/auth/logout")
    await _signup(async_client, "bob@x.com")
    r = await async_client.delete(f"/api/profiles/{pid}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_activate_sets_last_active_profile_id(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "First", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    r = await async_client.post(f"/api/profiles/{pid}/activate")
    assert r.status_code == 204

    listing = await async_client.get("/api/profiles")
    assert listing.json()["active_profile_id"] == pid


# ---------- 404 paths (unknown UUID against empty DB) ----------

import uuid as _uuid

_FAKE_ID = str(_uuid.uuid4())


@pytest.mark.asyncio
async def test_patch_unknown_profile_returns_404(async_client):
    await _signup(async_client)
    r = await async_client.patch(f"/api/profiles/{_FAKE_ID}", json={"name": "x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_unknown_profile_returns_404(async_client):
    await _signup(async_client)
    r = await async_client.delete(f"/api/profiles/{_FAKE_ID}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_activate_unknown_profile_returns_404(async_client):
    await _signup(async_client)
    r = await async_client.post(f"/api/profiles/{_FAKE_ID}/activate")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_activate_403_when_other_user(async_client):
    await _signup(async_client, "alice@x.com")
    create = await async_client.post("/api/profiles", json={
        "name": "Alice's", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    await async_client.post("/api/auth/logout")
    await _signup(async_client, "bob@x.com")
    r = await async_client.post(f"/api/profiles/{pid}/activate")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_activate_surfaces_profile_to_top_of_list(async_client):
    """Activating a profile bumps updated_at so the list (ordered by
    updated_at desc) shows it first."""
    await _signup(async_client)
    a = await async_client.post("/api/profiles", json={"name": "A", "settings_json": {}, "rules_json": []})
    b = await async_client.post("/api/profiles", json={"name": "B", "settings_json": {}, "rules_json": []})
    a_id = a.json()["id"]

    # B was created last so it currently sorts first
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"][0]["name"] == "B"

    # Activate A — now A should sort first
    await async_client.post(f"/api/profiles/{a_id}/activate")
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"][0]["id"] == a_id
