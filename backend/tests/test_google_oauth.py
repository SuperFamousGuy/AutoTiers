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
    assert "autotiers_session" in r.cookies
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
    original = next(u for u in users if u.email == "u@example.com")
    new_user = next(u for u in users if u.email is None)
    assert original.google_subject is None  # existing user untouched
    assert new_user.google_subject == "google-new-sub"


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
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "g-link-sub", "email": "owner@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error" not in r.headers["location"]
    await test_db.refresh(u)
    assert u.google_subject == "g-link-sub"
    # Only one user — no duplicate created.
    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_callback_links_no_op_when_already_linked_to_self(async_client, test_db):
    u = await _login_as(async_client, test_db)
    u.google_subject = "g-link-sub"
    await test_db.commit()
    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "g-link-sub", "email": "owner@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error" not in r.headers["location"]


@pytest.mark.asyncio
async def test_callback_redirects_with_linking_error_when_subject_on_other_user(async_client, test_db):
    # Other user already owns the subject.
    other = User(google_subject="g-link-sub")
    test_db.add(other)
    await test_db.commit()
    # Logged-in user tries to claim it.
    u = await _login_as(async_client, test_db)
    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "g-link-sub", "email": "owner@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "linking_error=already_linked_elsewhere" in r.headers["location"]
    await test_db.refresh(u)
    assert u.google_subject is None  # unchanged


@pytest.mark.asyncio
async def test_callback_backfills_email_when_linking_and_user_has_none(async_client, test_db):
    """Yahoo-only user (no email) links Google -> email gets backfilled if verified."""
    u = User(yahoo_subject="y-existing")
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    # Manually issue a JWT for this user — they have no password to log in with.
    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    async_client.cookies.set(JWT_COOKIE_NAME, encode_jwt(u.id))

    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "g-new", "email": "backfilled@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302
    await test_db.refresh(u)
    assert u.google_subject == "g-new"
    assert u.email == "backfilled@example.com"


@pytest.mark.asyncio
async def test_callback_seeds_default_profile_on_first_login(async_client, test_db):
    """A brand-new Google user must land with exactly one profile and a
    non-null last_active_profile_id, so autosave has somewhere to persist (#606)."""
    from app.models import Profile
    from app.defaults import DEFAULT_PROFILE_SETTINGS

    state = "abc123"
    async_client.cookies.set("autotiers_google_oauth_state", state)
    with respx.mock() as router:
        router.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(200, json={"access_token": "tok"}),
        )
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=Response(200, json={
                "sub": "google-seed", "email": "seed@example.com", "email_verified": True,
            }),
        )
        r = await async_client.get(
            f"/api/auth/google/callback?code=the-code&state={state}",
            follow_redirects=False,
        )
    assert r.status_code == 302

    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1
    profiles = (await test_db.scalars(select(Profile).where(Profile.user_id == users[0].id))).all()
    assert len(profiles) == 1
    assert profiles[0].name == "My setup"
    assert profiles[0].settings_json == DEFAULT_PROFILE_SETTINGS
    # Half-PPR is the shipped default for new profiles (#688), not standard.
    assert profiles[0].settings_json["scoring_format"] == "half_ppr"
    assert profiles[0].rules_json == {}
    assert users[0].last_active_profile_id == profiles[0].id

    # /me exposes the seeded profile and a non-null active id.
    me = (await async_client.get("/api/auth/me")).json()
    assert len(me["profiles"]) == 1
    assert me["profiles"][0]["name"] == "My setup"
    assert me["user"]["last_active_profile_id"] == str(profiles[0].id)


@pytest.mark.asyncio
async def test_repeat_login_does_not_seed_a_second_profile(async_client, test_db):
    """Only first login seeds a profile; a returning user keeps their single one."""
    from app.models import Profile

    state = "abc123"
    identity = {"sub": "google-repeat", "email": "repeat@example.com", "email_verified": True}

    async def _do_login():
        async_client.cookies.set("autotiers_google_oauth_state", state)
        with respx.mock() as router:
            router.post("https://oauth2.googleapis.com/token").mock(
                return_value=Response(200, json={"access_token": "tok"}),
            )
            router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
                return_value=Response(200, json=identity),
            )
            return await async_client.get(
                f"/api/auth/google/callback?code=the-code&state={state}",
                follow_redirects=False,
            )

    await _do_login()
    # Drop the session cookie the first callback set so the second callback runs
    # the sign-in branch (current_user is None) a real returning user hits — not
    # the link branch. Otherwise this wouldn't guard the sign-in seeding path.
    async_client.cookies.delete("autotiers_session")
    await _do_login()

    users = (await test_db.scalars(select(User))).all()
    assert len(users) == 1
    profiles = (await test_db.scalars(select(Profile).where(Profile.user_id == users[0].id))).all()
    assert len(profiles) == 1  # no duplicate seeded on repeat login


@pytest.mark.asyncio
async def test_me_returns_null_linked_league_when_profile_has_none(async_client, test_db):
    """Profile without a linked league must serialize linked_league=null."""
    from app.auth.hashing import hash_password
    from app.models import User, Profile
    u = User(email="u-linked@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    p = Profile(user_id=u.id, name="P1", settings_json={"scoring_format": "ppr"}, rules_json={})
    test_db.add(p)
    await test_db.commit()

    r = await async_client.post(
        "/api/auth/login", json={"email": "u-linked@example.com", "password": "password-long-enough"},
    )
    assert r.status_code == 200
    me = (await async_client.get("/api/auth/me")).json()
    assert me["profiles"][0]["linked_league"] is None
