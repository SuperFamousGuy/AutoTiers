import pytest
from sqlalchemy import select
from app.models import User, Profile


@pytest.mark.asyncio
async def test_signup_creates_user(async_client):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    assert "autotiers_session" in r.cookies


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_email(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    r2 = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "different password!",
    })
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_signup_rejects_short_password(async_client):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "short",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_signup_with_anonymous_state_creates_first_profile(async_client, test_db):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
        "initial_settings": {"scoring_format": "ppr", "league_size": 12},
        "initial_rules": [{"name": "RB Committee Penalty", "enabled": True, "weight": 1.0}],
    })
    assert r.status_code == 201

    profiles = (await test_db.scalars(select(Profile))).all()
    assert len(profiles) == 1
    assert profiles[0].name == "My setup"
    assert profiles[0].settings_json["scoring_format"] == "ppr"

    user = (await test_db.scalars(select(User))).one()
    assert user.last_active_profile_id == profiles[0].id
