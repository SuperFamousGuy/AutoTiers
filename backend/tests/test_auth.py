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


# ---------------------------------------------------------------------------
# Issue #692 — Bound password field lengths (Argon2 amplification guard)
# ---------------------------------------------------------------------------
# MAX_PASSWORD_LENGTH is 128. Anything longer must be rejected with 422 BEFORE
# Starlette buffers/parses a huge body and before Argon2 preprocesses it — on
# the unauthenticated signup/login paths this is a cheap CPU/memory DoS vector.


@pytest.mark.asyncio
async def test_signup_rejects_password_over_max_length(async_client):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "a" * 129,  # one over the 128 cap
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_signup_accepts_password_at_max_length(async_client):
    """A password at exactly the cap length still signs up successfully."""
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "a" * 128,  # exactly the cap
    })
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_login_rejects_password_over_max_length(async_client):
    """Over-cap password is rejected at validation (422) before any hashing,
    regardless of whether the account exists."""
    r = await async_client.post("/api/auth/login", json={
        "email": "ghost@example.com",
        "password": "a" * 129,
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_login_accepts_password_at_max_length(async_client):
    """A password at exactly the cap length still logs in successfully."""
    max_password = "a" * 128
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": max_password,
    })
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": max_password,
    })
    assert r.status_code == 200
    assert "autotiers_session" in r.cookies


@pytest.mark.asyncio
async def test_signup_with_anonymous_state_creates_first_profile(async_client, test_db):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
        "initial_settings": {"scoring_format": "ppr", "league_size": 12},
        "initial_rules": {"RB": [{"name": "RB Committee Penalty", "enabled": True, "weight": 1.0}]},
    })
    assert r.status_code == 201

    profiles = (await test_db.scalars(select(Profile))).all()
    assert len(profiles) == 1
    assert profiles[0].name == "My setup"
    assert profiles[0].settings_json["scoring_format"] == "ppr"
    assert profiles[0].rules_json == {
        "RB": [{"name": "RB Committee Penalty", "enabled": True, "weight": 1.0}]
    }

    user = (await test_db.scalars(select(User))).one()
    assert user.last_active_profile_id == profiles[0].id


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    assert r.status_code == 200
    assert "autotiers_session" in r.cookies


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "wrong",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_unknown_email(async_client):
    r = await async_client.post("/api/auth/login", json={
        "email": "ghost@example.com",
        "password": "anything",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limit_triggers_after_5_fails(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()

    from app.auth.rate_limit import login_rate_limiter
    login_rate_limiter._attempts.clear()

    for _ in range(5):
        r = await async_client.post("/api/auth/login", json={
            "email": "alice@example.com",
            "password": "bad",
        })
        assert r.status_code == 401

    r = await async_client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_logout_clears_cookie(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    r = await async_client.post("/api/auth/logout")
    assert r.status_code == 204
    assert "autotiers_session" not in async_client.cookies


@pytest.mark.asyncio
async def test_me_returns_401_when_anonymous(async_client):
    async_client.cookies.clear()
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_and_profiles_when_authenticated(async_client):
    signup = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
        "initial_settings": {"scoring_format": "ppr", "league_size": 12},
        "initial_rules": {},
    })
    assert signup.status_code == 201

    r = await async_client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["name"] == "My setup"


def test_userout_yahoo_fantasy_connected_true():
    from app.schemas.auth import UserOut
    from unittest.mock import MagicMock
    import uuid
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.yahoo_subject = "sub123"
    user.yahoo_access_token = "enc_token"
    user.google_subject = None
    user.last_active_profile_id = None
    out = UserOut.model_validate(user)
    assert out.yahoo_fantasy_connected is True


def test_userout_yahoo_fantasy_connected_false():
    from app.schemas.auth import UserOut
    from unittest.mock import MagicMock
    import uuid
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.yahoo_subject = None
    user.yahoo_access_token = None
    user.google_subject = None
    user.last_active_profile_id = None
    out = UserOut.model_validate(user)
    assert out.yahoo_fantasy_connected is False
