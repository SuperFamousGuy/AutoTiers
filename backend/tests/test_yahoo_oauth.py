import pytest
import respx
from httpx import Response
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_identity


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(state="random123")
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "state=random123" in url
    assert "scope=openid+email" in url or "scope=openid%20email" in url


@pytest.mark.asyncio
async def test_exchange_code_returns_access_token():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(return_value=Response(
            200, json={"access_token": "the-access-token", "token_type": "bearer", "expires_in": 3600}
        ))
        token = await exchange_code("the-code")
    assert token == "the-access-token"


@pytest.mark.asyncio
async def test_exchange_code_raises_on_error():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(return_value=Response(400, json={"error": "invalid_grant"}))
        with pytest.raises(Exception):
            await exchange_code("bad-code")


@pytest.mark.asyncio
async def test_fetch_identity_returns_subject_email_and_verified():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.get("/openid/v1/userinfo").mock(return_value=Response(
            200, json={"sub": "yahoo-user-abc", "email": "u@example.com", "email_verified": True}
        ))
        identity = await fetch_identity("access-token")
    assert identity == ("yahoo-user-abc", "u@example.com", True)


@pytest.mark.asyncio
async def test_fetch_identity_handles_missing_email_fields():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.get("/openid/v1/userinfo").mock(return_value=Response(
            200, json={"sub": "yahoo-user-abc"}
        ))
        identity = await fetch_identity("access-token")
    assert identity == ("yahoo-user-abc", None, False)


from sqlalchemy import select
from app.models import User


@pytest.mark.asyncio
async def test_authorize_redirects_to_yahoo_with_state_cookie(async_client):
    r = await async_client.get("/api/auth/yahoo/authorize", follow_redirects=False)
    assert r.status_code == 307
    location = r.headers["location"]
    assert location.startswith("https://api.login.yahoo.com/oauth2/request_auth")
    assert "state=" in location
    assert "autotiers_oauth_state" in r.cookies


@pytest.mark.asyncio
async def test_callback_rejects_missing_state_cookie(async_client):
    r = await async_client.get(
        "/api/auth/yahoo/callback?code=the-code&state=random123",
        follow_redirects=False,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_callback_rejects_mismatched_state(async_client):
    async_client.cookies.set("autotiers_oauth_state", "stored-value")
    r = await async_client.get(
        "/api/auth/yahoo/callback?code=the-code&state=different-value",
        follow_redirects=False,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_callback_creates_new_user_on_first_login(async_client, test_db):
    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={"sub": "yahoo-user-xyz"}),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1
    assert users[0].yahoo_subject == "yahoo-user-xyz"
    assert users[0].email is None
    assert "autotiers_session" in r.cookies


@pytest.mark.asyncio
async def test_callback_finds_existing_user_on_repeat_login(async_client, test_db):
    existing = User(yahoo_subject="yahoo-user-xyz")
    test_db.add(existing)
    await test_db.commit()

    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={"sub": "yahoo-user-xyz"}),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1  # no duplicate
