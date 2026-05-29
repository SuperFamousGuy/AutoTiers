import pytest
import respx
from httpx import Response
from app.auth.google import build_authorize_url, exchange_code, fetch_identity


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(state="random123")
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "state=random123" in url
    assert "scope=openid+email" in url or "scope=openid%20email" in url


@pytest.mark.asyncio
async def test_exchange_code_returns_access_token():
    with respx.mock(base_url="https://oauth2.googleapis.com") as router:
        router.post("/token").mock(return_value=Response(
            200, json={"access_token": "the-access-token", "token_type": "bearer", "expires_in": 3600}
        ))
        token = await exchange_code("the-code")
    assert token == "the-access-token"


@pytest.mark.asyncio
async def test_exchange_code_raises_on_error():
    with respx.mock(base_url="https://oauth2.googleapis.com") as router:
        router.post("/token").mock(return_value=Response(400, json={"error": "invalid_grant"}))
        with pytest.raises(Exception):
            await exchange_code("bad-code")


@pytest.mark.asyncio
async def test_fetch_identity_returns_subject_email_and_verified():
    with respx.mock(base_url="https://openidconnect.googleapis.com") as router:
        router.get("/v1/userinfo").mock(return_value=Response(
            200, json={"sub": "google-user-abc", "email": "u@example.com", "email_verified": True}
        ))
        identity = await fetch_identity("access-token")
    assert identity == ("google-user-abc", "u@example.com", True)


@pytest.mark.asyncio
async def test_fetch_identity_handles_missing_email_fields():
    with respx.mock(base_url="https://openidconnect.googleapis.com") as router:
        router.get("/v1/userinfo").mock(return_value=Response(
            200, json={"sub": "google-user-abc"}
        ))
        identity = await fetch_identity("access-token")
    assert identity == ("google-user-abc", None, False)


from sqlalchemy import select
from app.models import User


@pytest.mark.asyncio
async def test_authorize_redirects_to_google_with_state_cookie(async_client):
    r = await async_client.get("/api/auth/google/authorize", follow_redirects=False)
    assert r.status_code == 307
    location = r.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "state=" in location
    assert "autotiers_google_oauth_state" in r.cookies


@pytest.mark.asyncio
async def test_callback_rejects_missing_state_cookie(async_client):
    r = await async_client.get(
        "/api/auth/google/callback?code=the-code&state=random123",
        follow_redirects=False,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_callback_rejects_mismatched_state(async_client):
    async_client.cookies.set("autotiers_google_oauth_state", "stored-value")
    r = await async_client.get(
        "/api/auth/google/callback?code=the-code&state=different-value",
        follow_redirects=False,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_callback_creates_new_user_on_first_login(async_client, test_db):
    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "google-user-xyz", "email": "newuser@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1
    assert users[0].google_subject == "google-user-xyz"
    assert users[0].email == "newuser@example.com"
    assert "autotiers_session" in r.cookies

    # Also assert /me exposes google_subject
    me = await async_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["google_subject"] == "google-user-xyz"


@pytest.mark.asyncio
async def test_callback_finds_existing_user_on_repeat_login(async_client, test_db):
    existing = User(google_subject="google-user-xyz")
    test_db.add(existing)
    await test_db.commit()

    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={"sub": "google-user-xyz"}),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1  # no duplicate


@pytest.mark.asyncio
async def test_callback_auto_links_when_email_matches_existing_user(async_client, test_db):
    """Existing email/password user; Google returns same verified email -> attach subject, sign in."""
    from app.auth.hashing import hash_password
    existing = User(email="u@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(existing)
    await test_db.commit()
    await test_db.refresh(existing)

    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "google-new-sub", "email": "u@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1  # no duplicate
    await test_db.refresh(users[0])
    assert users[0].google_subject == "google-new-sub"


@pytest.mark.asyncio
async def test_callback_does_not_auto_link_when_email_not_verified(async_client, test_db):
    """Email match but email_verified=False -> create new user, do not attach."""
    from app.auth.hashing import hash_password
    existing = User(email="u@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(existing)
    await test_db.commit()

    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "google-new-sub", "email": "u@example.com", "email_verified": False,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 2  # new user created — no auto-link
