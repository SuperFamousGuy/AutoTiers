import pytest
from sqlalchemy import select
from app.models import User
from app.auth.hashing import hash_password


async def _login(async_client, email="u@example.com", password="password-long-enough"):
    r = await async_client.post(
        "/api/auth/login", json={"email": email, "password": password},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_unlink_google_success_when_password_remains(async_client, test_db):
    u = User(
        email="u@example.com",
        password_hash=hash_password("password-long-enough"),
        google_subject="g-sub",
    )
    test_db.add(u)
    await test_db.commit()
    await _login(async_client)

    r = await async_client.delete("/api/auth/google/link")
    assert r.status_code == 204

    await test_db.refresh(u)
    assert u.google_subject is None


@pytest.mark.asyncio
async def test_unlink_yahoo_success_when_other_provider_remains(async_client, test_db):
    u = User(
        email="u@example.com",
        password_hash=hash_password("password-long-enough"),
        yahoo_subject="y-sub",
        google_subject="g-sub",
    )
    test_db.add(u)
    await test_db.commit()
    await _login(async_client)

    r = await async_client.delete("/api/auth/yahoo/link")
    assert r.status_code == 204

    await test_db.refresh(u)
    assert u.yahoo_subject is None
    assert u.google_subject == "g-sub"


@pytest.mark.asyncio
async def test_unlink_rejected_when_last_method(async_client, test_db):
    """User has only google_subject — unlinking it would lock them out."""
    u = User(email="u@example.com", google_subject="g-sub")
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)

    # Log in via direct cookie (no password to log in with).
    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    async_client.cookies.set(JWT_COOKIE_NAME, encode_jwt(u.id))

    r = await async_client.delete("/api/auth/google/link")
    assert r.status_code == 400
    assert "last sign-in method" in r.json()["detail"].lower()

    await test_db.refresh(u)
    assert u.google_subject == "g-sub"  # unchanged


@pytest.mark.asyncio
async def test_unlink_requires_authentication(async_client):
    r = await async_client.delete("/api/auth/google/link")
    assert r.status_code == 401
    r = await async_client.delete("/api/auth/yahoo/link")
    assert r.status_code == 401
