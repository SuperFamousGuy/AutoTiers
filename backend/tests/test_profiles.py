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
        "rules_json": {"RB": [{"name": "X", "enabled": True, "weight": 1.0}]},
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "PPR 12-team"


def _oversized_settings() -> dict:
    """A settings_json blob that serializes to well over the 64KB cap."""
    return {"junk": "x" * (128 * 1024)}


@pytest.mark.asyncio
async def test_create_profile_rejects_oversized_settings_json(async_client):
    await _signup(async_client)
    r = await async_client.post("/api/profiles", json={
        "name": "Huge",
        "settings_json": _oversized_settings(),
        "rules_json": {},
    })
    assert r.status_code == 422
    assert "too large" in str(r.json()["detail"]).lower()
    # Nothing was persisted.
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"] == []


@pytest.mark.asyncio
async def test_create_profile_rejects_oversized_rules_json(async_client):
    await _signup(async_client)
    r = await async_client.post("/api/profiles", json={
        "name": "Huge rules",
        "settings_json": {},
        "rules_json": {"RB": [{"name": "x" * (128 * 1024), "enabled": True}]},
    })
    assert r.status_code == 422
    assert "too large" in str(r.json()["detail"]).lower()
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"] == []


@pytest.mark.asyncio
async def test_patch_profile_rejects_oversized_settings_json(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Original",
        "settings_json": {"league_size": 10},
        "rules_json": {},
    })
    assert create.status_code == 201
    pid = create.json()["id"]

    r = await async_client.patch(f"/api/profiles/{pid}", json={
        "settings_json": _oversized_settings(),
    })
    assert r.status_code == 422
    assert "too large" in str(r.json()["detail"]).lower()
    # The stored row is unchanged — original settings intact.
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"][0]["settings_json"] == {"league_size": 10}


@pytest.mark.asyncio
async def test_create_profile_rejects_whitespace_only_name(async_client):
    await _signup(async_client)
    r = await async_client.post("/api/profiles", json={
        "name": "  ",
        "settings_json": {},
        "rules_json": {},
    })
    assert r.status_code == 422
    assert "blank" in r.json()["detail"].lower()
    # Nothing was persisted.
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"] == []


@pytest.mark.asyncio
async def test_create_profile_trims_surrounding_whitespace(async_client):
    await _signup(async_client)
    r = await async_client.post("/api/profiles", json={
        "name": "  Trimmed  ",
        "settings_json": {},
        "rules_json": {},
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Trimmed"


@pytest.mark.asyncio
async def test_create_profile_rejects_when_at_cap(async_client):
    await _signup(async_client)
    for i in range(5):
        r = await async_client.post("/api/profiles", json={
            "name": f"Slot {i}",
            "settings_json": {},
            "rules_json": {},
        })
        assert r.status_code == 201
    r = await async_client.post("/api/profiles", json={
        "name": "Sixth",
        "settings_json": {},
        "rules_json": {},
    })
    assert r.status_code == 409
    assert "limit" in r.json()["detail"].lower() or "max" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_profile_rejects_duplicate_name(async_client):
    await _signup(async_client)
    first = await async_client.post("/api/profiles", json={
        "name": "My League", "settings_json": {}, "rules_json": {},
    })
    assert first.status_code == 201

    # Duplicate name — including the strip() normalization of a trailing space.
    r = await async_client.post("/api/profiles", json={
        "name": "My League ", "settings_json": {}, "rules_json": {},
    })
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "already have a profile" in detail.lower()
    # The 409 names the conflicting profile, and uses the trimmed name — not
    # the raw trailing-whitespace input the client sent.
    assert "'My League'" in detail
    assert "'My League '" not in detail

    # No extra row was persisted.
    listing = await async_client.get("/api/profiles")
    assert len(listing.json()["profiles"]) == 1


@pytest.mark.asyncio
async def test_patch_profile_rejects_duplicate_name(async_client):
    await _signup(async_client)
    a = await async_client.post("/api/profiles", json={
        "name": "Alpha", "settings_json": {}, "rules_json": {},
    })
    b = await async_client.post("/api/profiles", json={
        "name": "Beta", "settings_json": {}, "rules_json": {},
    })
    b_id = b.json()["id"]

    # Rename Beta -> Alpha collides.
    r = await async_client.patch(f"/api/profiles/{b_id}", json={"name": "Alpha"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "already have a profile" in detail.lower()
    # The 409 names the conflicting profile so the message is actionable.
    assert "'Alpha'" in detail

    # Beta is unchanged; still two distinctly-named profiles.
    listing = await async_client.get("/api/profiles")
    names = sorted(p["name"] for p in listing.json()["profiles"])
    assert names == ["Alpha", "Beta"]


@pytest.mark.asyncio
async def test_patch_profile_allows_renaming_to_same_name(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Keep Me", "settings_json": {}, "rules_json": {},
    })
    pid = create.json()["id"]

    # No-op rename to its own current name must not self-collide.
    r = await async_client.patch(f"/api/profiles/{pid}", json={"name": "Keep Me"})
    assert r.status_code == 200
    assert r.json()["name"] == "Keep Me"


async def _always_free(*args, **kwargs):
    """Stand-in for _name_taken that reports every name free — used to simulate
    the TOCTOU race where the pre-check passes but the DB constraint fires."""
    return False


@pytest.mark.asyncio
async def test_create_profile_race_falls_back_to_db_constraint(async_client, monkeypatch):
    from app.api import profiles_api
    await _signup(async_client)
    first = await async_client.post("/api/profiles", json={
        "name": "Racy", "settings_json": {}, "rules_json": {},
    })
    assert first.status_code == 201

    # Pre-check reports the name free even though the row exists, so the
    # unique constraint is the guard that must convert IntegrityError -> 409.
    monkeypatch.setattr(profiles_api, "_name_taken", _always_free)
    r = await async_client.post("/api/profiles", json={
        "name": "Racy", "settings_json": {}, "rules_json": {},
    })
    assert r.status_code == 409
    assert "already have a profile" in r.json()["detail"].lower()

    # Rollback means no orphan row survived the failed commit.
    listing = await async_client.get("/api/profiles")
    assert len(listing.json()["profiles"]) == 1


@pytest.mark.asyncio
async def test_patch_profile_race_falls_back_to_db_constraint(async_client, monkeypatch):
    from app.api import profiles_api
    await _signup(async_client)
    await async_client.post("/api/profiles", json={
        "name": "Aaa", "settings_json": {}, "rules_json": {},
    })
    b = await async_client.post("/api/profiles", json={
        "name": "Bbb", "settings_json": {}, "rules_json": {},
    })
    b_id = b.json()["id"]

    monkeypatch.setattr(profiles_api, "_name_taken", _always_free)
    r = await async_client.patch(f"/api/profiles/{b_id}", json={"name": "Aaa"})
    assert r.status_code == 409
    assert "already have a profile" in r.json()["detail"].lower()

    # Both rows intact after the rolled-back rename.
    listing = await async_client.get("/api/profiles")
    names = sorted(p["name"] for p in listing.json()["profiles"])
    assert names == ["Aaa", "Bbb"]


@pytest.mark.asyncio
async def test_duplicate_name_allowed_across_different_users(async_client):
    # Two users may each own a profile named the same thing.
    await _signup(async_client, "alice@x.com")
    a = await async_client.post("/api/profiles", json={
        "name": "My League", "settings_json": {}, "rules_json": {},
    })
    assert a.status_code == 201

    await async_client.post("/api/auth/logout")
    await _signup(async_client, "bob@x.com")
    b = await async_client.post("/api/profiles", json={
        "name": "My League", "settings_json": {}, "rules_json": {},
    })
    assert b.status_code == 201


@pytest.mark.asyncio
async def test_patch_profile_updates_fields(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Original",
        "settings_json": {"league_size": 10},
        "rules_json": {},
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
    assert body["rules_json"] == {}


@pytest.mark.asyncio
async def test_patch_profile_rejects_whitespace_only_name(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Original",
        "settings_json": {},
        "rules_json": {},
    })
    pid = create.json()["id"]

    r = await async_client.patch(f"/api/profiles/{pid}", json={"name": " "})
    assert r.status_code == 422
    assert "blank" in r.json()["detail"].lower()

    # The stored row is unchanged — name still "Original".
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"][0]["name"] == "Original"


@pytest.mark.asyncio
async def test_patch_profile_trims_surrounding_whitespace(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Original", "settings_json": {}, "rules_json": {},
    })
    pid = create.json()["id"]

    r = await async_client.patch(f"/api/profiles/{pid}", json={"name": "  Renamed  "})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_patch_profile_403_when_other_user(async_client):
    await _signup(async_client, "alice@x.com")
    create = await async_client.post("/api/profiles", json={
        "name": "Alice's profile", "settings_json": {}, "rules_json": {},
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
        "name": "Doomed", "settings_json": {}, "rules_json": {},
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
        "name": "Alice's", "settings_json": {}, "rules_json": {},
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
        "name": "First", "settings_json": {}, "rules_json": {},
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
        "name": "Alice's", "settings_json": {}, "rules_json": {},
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
    a = await async_client.post("/api/profiles", json={"name": "A", "settings_json": {}, "rules_json": {}})
    b = await async_client.post("/api/profiles", json={"name": "B", "settings_json": {}, "rules_json": {}})
    a_id = a.json()["id"]

    # B was created last so it currently sorts first
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"][0]["name"] == "B"

    # Activate A — now A should sort first
    await async_client.post(f"/api/profiles/{a_id}/activate")
    listing = await async_client.get("/api/profiles")
    assert listing.json()["profiles"][0]["id"] == a_id
