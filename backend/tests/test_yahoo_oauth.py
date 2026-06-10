import pytest
import respx
import httpx
from httpx import Response
from unittest.mock import patch, AsyncMock
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_identity, refresh_access_token


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(state="random123")
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "state=random123" in url
    assert "scope=openid+email" in url or "scope=openid%20email" in url


def test_build_authorize_url_identity_scope():
    url = build_authorize_url("state123")
    assert "fspt-r" not in url
    assert "openid" in url
    assert "email" in url


def test_build_authorize_url_fantasy_scope():
    url = build_authorize_url("state123", fantasy=True)
    assert "fspt-r" in url
    assert "openid" in url


@pytest.mark.asyncio
async def test_exchange_code_returns_tuple():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "acc123", "refresh_token": "ref456"})
        )
        access, refresh = await exchange_code("mycode")
    assert access == "acc123"
    assert refresh == "ref456"


@pytest.mark.asyncio
async def test_exchange_code_no_refresh_token():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "acc123"})
        )
        access, refresh = await exchange_code("mycode")
    assert access == "acc123"
    assert refresh is None


@pytest.mark.asyncio
async def test_refresh_access_token():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "new_acc"})
        )
        new_token = await refresh_access_token("old_refresh")
    assert new_token == "new_acc"


@pytest.mark.asyncio
async def test_exchange_code_returns_access_token():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(return_value=Response(
            200, json={"access_token": "the-access-token", "token_type": "bearer", "expires_in": 3600}
        ))
        access, _ = await exchange_code("the-code")
    assert access == "the-access-token"


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
    # No intent cookie unless explicitly requested.
    assert "autotiers_oauth_intent" not in r.cookies


@pytest.mark.asyncio
async def test_authorize_with_intent_link_sets_intent_cookie(async_client):
    r = await async_client.get("/api/auth/yahoo/authorize?intent=link", follow_redirects=False)
    assert r.status_code == 307
    assert r.cookies.get("autotiers_oauth_intent") == "link"


@pytest.mark.asyncio
async def test_callback_with_link_intent_but_no_session_redirects_with_error(async_client, test_db):
    """If the linking flow was initiated but the session cookie didn't survive
    the round-trip, the callback must NOT silently sign the user in as a new
    account — it should redirect with a clear linking_error so the user
    knows their existing account is intact."""
    import respx
    from httpx import Response
    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    async_client.cookies.set("autotiers_oauth_intent", "link")
    # Brand-new yahoo subject — without the intent guard we'd create a phantom
    # user here and orphan the original account.
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={"sub": "y-brand-new-sub"}),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error=session_lost" in r.headers["location"]
    # No new user should have been created.
    from app.models import User
    from sqlalchemy import select as sql_select
    users = (await test_db.scalars(sql_select(User).where(User.yahoo_subject == "y-brand-new-sub"))).all()
    assert users == []


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
            return_value=Response(200, json={
                "sub": "yahoo-user-xyz", "email": "newuser@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1
    assert users[0].yahoo_subject == "yahoo-user-xyz"
    assert users[0].email == "newuser@example.com"
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


@pytest.mark.asyncio
async def test_callback_auto_links_when_email_matches_existing_user(async_client, test_db):
    """Existing email/password user; Yahoo returns same verified email -> attach subject, sign in."""
    from app.auth.hashing import hash_password
    existing = User(email="u@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(existing)
    await test_db.commit()
    await test_db.refresh(existing)

    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "yahoo-new-sub", "email": "u@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "autotiers_session" in r.cookies
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1  # no duplicate
    await test_db.refresh(users[0])
    assert users[0].yahoo_subject == "yahoo-new-sub"


@pytest.mark.asyncio
async def test_callback_does_not_auto_link_when_email_not_verified(async_client, test_db):
    """Email match but email_verified=False -> create new user, do not attach."""
    from app.auth.hashing import hash_password
    existing = User(email="u@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(existing)
    await test_db.commit()

    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "yahoo-new-sub", "email": "u@example.com", "email_verified": False,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 2  # new user created — no auto-link
    original = next(u for u in users if u.email == "u@example.com")
    new_user = next(u for u in users if u.email is None)
    assert original.yahoo_subject is None  # existing user untouched
    assert new_user.yahoo_subject == "yahoo-new-sub"


async def _login_as(async_client, test_db, email="owner@example.com"):
    """Helper: create an email/password user and obtain an auth cookie."""
    from app.auth.hashing import hash_password
    u = User(email=email, password_hash=hash_password("password-long-enough"))
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    r = await async_client.post(
        "/api/auth/login",
        json={"email": email, "password": "password-long-enough"},
    )
    assert r.status_code == 200
    return u


@pytest.mark.asyncio
async def test_callback_links_subject_to_current_user_when_authenticated(async_client, test_db):
    u = await _login_as(async_client, test_db)
    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "y-link-sub", "email": "owner@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error" not in r.headers["location"]
    await test_db.refresh(u)
    assert u.yahoo_subject == "y-link-sub"
    # Only one user — no duplicate created.
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_callback_links_no_op_when_already_linked_to_self(async_client, test_db):
    u = await _login_as(async_client, test_db)
    u.yahoo_subject = "y-link-sub"
    await test_db.commit()
    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "y-link-sub", "email": "owner@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error" not in r.headers["location"]


@pytest.mark.asyncio
async def test_callback_redirects_with_linking_error_when_subject_on_other_user(async_client, test_db):
    # Other user already owns the subject.
    other = User(yahoo_subject="y-link-sub")
    test_db.add(other)
    await test_db.commit()
    # Logged-in user tries to claim it.
    u = await _login_as(async_client, test_db)
    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "y-link-sub", "email": "owner@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error=already_linked_elsewhere" in r.headers["location"]
    await test_db.refresh(u)
    assert u.yahoo_subject is None  # unchanged


@pytest.mark.asyncio
async def test_callback_backfills_email_when_linking_and_user_has_none(async_client, test_db):
    """Google-only user (no email) links Yahoo -> email gets backfilled if verified."""
    u = User(google_subject="g-existing")
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    # Manually issue a JWT for this user — they have no password to log in with.
    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    async_client.cookies.set(JWT_COOKIE_NAME, encode_jwt(u.id))

    state = "abc123"
    async_client.cookies.set("autotiers_oauth_state", state)
    with respx.mock() as router:
        router.post("https://api.login.yahoo.com/oauth2/get_token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://api.login.yahoo.com/openid/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "y-new", "email": "backfilled@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/yahoo/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    await test_db.refresh(u)
    assert u.yahoo_subject == "y-new"
    assert u.email == "backfilled@example.com"


@pytest.mark.asyncio
async def test_yahoo_authorize_fantasy_intent_adds_fspt_scope(async_client):
    """GET /api/auth/yahoo/authorize?intent=yahoo_fantasy redirects with fspt-r scope."""
    resp = await async_client.get(
        "/api/auth/yahoo/authorize",
        params={"intent": "yahoo_fantasy"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "fspt-r" in location


@pytest.mark.asyncio
async def test_yahoo_callback_fantasy_stores_tokens(async_client, test_db):
    """Callback with yahoo_fantasy intent stores encrypted tokens on user."""
    from app.models import User
    from app.auth.jwt import encode_jwt
    from app.security.fernet import decrypt

    user = User(yahoo_subject="sub_xyz", email="tok@example.com")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    state = "teststate999"
    jwt = encode_jwt(user.id)

    with (
        patch("app.api.auth.exchange_code", new_callable=AsyncMock,
              return_value=("acc_tok", "ref_tok")),
        patch("app.api.auth.fetch_identity", new_callable=AsyncMock,
              return_value=("sub_xyz", "tok@example.com", True)),
    ):
        resp = await async_client.get(
            "/api/auth/yahoo/callback",
            params={"code": "authcode", "state": state},
            cookies={
                "autotiers_oauth_state": state,
                "autotiers_session": jwt,
                "autotiers_oauth_intent": "yahoo_fantasy",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 302
    await test_db.refresh(user)
    assert user.yahoo_access_token is not None
    assert user.yahoo_refresh_token is not None
    # Tokens must be encrypted (not the raw values)
    assert decrypt(user.yahoo_access_token) == "acc_tok"
    assert decrypt(user.yahoo_refresh_token) == "ref_tok"
