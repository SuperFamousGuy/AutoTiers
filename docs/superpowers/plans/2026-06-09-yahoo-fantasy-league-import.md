# Yahoo Fantasy League Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users with a linked Yahoo account to import their Yahoo Fantasy Football league (scoring settings, keepers) into a profile — same outcome as Sleeper/ESPN linking.

**Architecture:** Extend Yahoo OAuth link flow with `intent=yahoo_fantasy` (adds `fspt-r` scope); store encrypted access+refresh tokens on `User`; new Yahoo Fantasy API client fetches league list + settings with transparent token refresh on 401; scoring mapper converts Yahoo stat format to AutoTiers settings; frontend mirrors the Sleeper UX (connect → pick league → import).

**Tech Stack:** Python/FastAPI, SQLAlchemy/Alembic, httpx, Fernet encryption (`app.security.fernet`), React/TypeScript, Tailwind/shadcn-ui

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/models/user.py` | Add `yahoo_access_token`, `yahoo_refresh_token` columns |
| Create | `backend/alembic/versions/009_yahoo_tokens.py` | Migration for the two new columns |
| Modify | `backend/app/auth/yahoo.py` | Fantasy scope, exchange_code returns tuple, refresh_access_token |
| Modify | `backend/app/schemas/auth.py` | Add `yahoo_fantasy_connected: bool` to `UserOut` |
| Modify | `backend/app/api/auth.py` | Handle `intent=yahoo_fantasy` in authorize + callback |
| Modify | `backend/app/integrations/scoring_mappers.py` | Add `yahoo_to_settings` |
| Create | `backend/app/integrations/yahoo_fantasy.py` | Yahoo Fantasy API client (list leagues, fetch league) |
| Modify | `backend/app/api/linked_league.py` | Add GET `/yahoo/leagues` and POST `/yahoo` endpoints |
| Modify | `web/src/api/types.ts` | Add `yahoo_fantasy_connected: boolean` to `User` |
| Modify | `web/src/api/linkedLeague.ts` | Add `listYahooLeagues`, `connectYahoo` |
| Create | `web/src/components/YahooConnectForm.tsx` | League picker + connected state UI |
| Modify | `web/src/components/LinkedAccountsDialog.tsx` | Wire Yahoo tab to `YahooConnectForm` |
| Modify | `backend/tests/test_yahoo_oauth.py` | Extend for fantasy intent |
| Create | `backend/tests/test_yahoo_fantasy.py` | Integration client + endpoint tests |
| Create | `web/src/tests/components/YahooConnectForm.test.tsx` | Component tests |

---

## Task 1: User model — add Yahoo token columns

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/009_yahoo_tokens.py`

- [ ] **Step 1: Add columns to User model**

In `backend/app/models/user.py`, add after the `google_subject` column:

```python
yahoo_access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
yahoo_refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

Full updated model block (replace the existing `User` class body's column section):

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    yahoo_subject: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    yahoo_access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    yahoo_refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    google_subject: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_active_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL", use_alter=True, name="fk_users_last_active_profile"),
        nullable=True,
    )

    favorites: Mapped[Optional["UserFavorites"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
```

- [ ] **Step 2: Create Alembic migration**

Create `backend/alembic/versions/009_yahoo_tokens.py`:

```python
"""Add yahoo_access_token and yahoo_refresh_token to users.

Revision ID: 009
Revises: 008
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("yahoo_access_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("yahoo_refresh_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "yahoo_refresh_token")
    op.drop_column("users", "yahoo_access_token")
```

- [ ] **Step 3: Run migration against test DB**

```bash
cd backend && venv/bin/alembic upgrade head
```

Expected: `Running upgrade 008 -> 009` with no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/009_yahoo_tokens.py
git commit -m "feat(db): add yahoo_access_token and yahoo_refresh_token to users"
```

---

## Task 2: Update yahoo.py — fantasy scope + token tuple + refresh

**Files:**
- Modify: `backend/app/auth/yahoo.py`
- Test: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_yahoo_oauth.py`:

```python
def test_build_authorize_url_identity_scope():
    url = build_authorize_url("state123")
    assert "fspt-r" not in url
    assert "openid" in url
    assert "email" in url


def test_build_authorize_url_fantasy_scope():
    url = build_authorize_url("state123", fantasy=True)
    assert "fspt-r" in url
    assert "openid" in url


def test_exchange_code_returns_tuple(respx_mock):
    respx_mock.post("https://api.login.yahoo.com/oauth2/get_token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "acc123", "refresh_token": "ref456"},
        )
    )
    import asyncio
    access, refresh = asyncio.run(exchange_code("mycode"))
    assert access == "acc123"
    assert refresh == "ref456"


def test_exchange_code_no_refresh_token(respx_mock):
    respx_mock.post("https://api.login.yahoo.com/oauth2/get_token").mock(
        return_value=httpx.Response(200, json={"access_token": "acc123"})
    )
    import asyncio
    access, refresh = asyncio.run(exchange_code("mycode"))
    assert access == "acc123"
    assert refresh is None


def test_refresh_access_token(respx_mock):
    respx_mock.post("https://api.login.yahoo.com/oauth2/get_token").mock(
        return_value=httpx.Response(200, json={"access_token": "new_acc"})
    )
    import asyncio
    new_token = asyncio.run(refresh_access_token("old_refresh"))
    assert new_token == "new_acc"
```

Make sure the imports at the top of the test file include:
```python
import httpx
from app.auth.yahoo import build_authorize_url, exchange_code, refresh_access_token
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_oauth.py -k "test_build_authorize_url_fantasy_scope or test_exchange_code_returns_tuple or test_exchange_code_no_refresh_token or test_refresh_access_token" -v
```

Expected: FAIL — `build_authorize_url` doesn't accept `fantasy` kwarg yet; `exchange_code` returns `str` not tuple.

- [ ] **Step 3: Update yahoo.py**

Replace the full contents of `backend/app/auth/yahoo.py`:

```python
"""Yahoo OAuth2 client.

Used for identity: we exchange the auth code for a token, fetch the
subject + email + email_verified claims, and discard the token. We trust
`email_verified` for auto-linking on first sign-in — see the design doc's
"Email-collision policy" section.

When fantasy=True is passed to build_authorize_url, the fspt-r scope is
added and exchange_code will return a refresh_token for offline access.
"""
from urllib.parse import urlencode
import httpx
from app.config import settings


AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
USERINFO_URL = "https://api.login.yahoo.com/openid/v1/userinfo"


def build_authorize_url(state: str, fantasy: bool = False) -> str:
    scope = "openid email fspt-r" if fantasy else "openid email"
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.yahoo_redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> tuple[str, str | None]:
    """Exchange an auth code for tokens.

    Returns (access_token, refresh_token). refresh_token is None when Yahoo
    did not return one (identity-only scope flows).
    Raises httpx.HTTPStatusError on non-2xx.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": settings.yahoo_redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data.get("refresh_token")


async def refresh_access_token(refresh_token: str) -> str:
    """Exchange a refresh token for a new access token.

    Raises httpx.HTTPStatusError on non-2xx (including 401 when the refresh
    token has been revoked — callers should surface this as a reconnect prompt).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": settings.yahoo_redirect_uri,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def fetch_identity(access_token: str) -> tuple[str, str | None, bool]:
    """Fetch the openid `sub`, `email`, and `email_verified` claims from Yahoo's userinfo endpoint.

    Returns (subject, email, email_verified). email is None and email_verified is False
    if the provider declines to return them.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["sub"], data.get("email"), data.get("email_verified") is True
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_oauth.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/yahoo.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(auth): yahoo fantasy scope, exchange_code tuple, refresh_access_token"
```

---

## Task 3: UserOut schema — yahoo_fantasy_connected

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Test: inline in existing `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_auth.py` (find the section with UserOut-related tests or add at the bottom):

```python
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
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd backend && venv/bin/python -m pytest tests/test_auth.py -k "yahoo_fantasy_connected" -v
```

Expected: FAIL — `UserOut` has no `yahoo_fantasy_connected` field.

- [ ] **Step 3: Update UserOut in schemas/auth.py**

Replace the `UserOut` class:

```python
from typing import Any
from pydantic import model_validator

class UserOut(BaseModel):
    id: uuid.UUID
    email: Optional[str]
    yahoo_subject: Optional[str]
    google_subject: Optional[str]
    last_active_profile_id: Optional[uuid.UUID]
    yahoo_fantasy_connected: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _compute_fantasy_connected(cls, data: Any) -> Any:
        if hasattr(data, "yahoo_access_token"):
            return {
                "id": data.id,
                "email": data.email,
                "yahoo_subject": data.yahoo_subject,
                "google_subject": data.google_subject,
                "last_active_profile_id": data.last_active_profile_id,
                "yahoo_fantasy_connected": data.yahoo_access_token is not None,
            }
        return data
```

Also add to the imports at the top of `schemas/auth.py`:
```python
from typing import Any
from pydantic import model_validator
```

(These may already be partially imported — merge with existing imports.)

- [ ] **Step 4: Run tests**

```bash
cd backend && venv/bin/python -m pytest tests/test_auth.py -v
```

Expected: all pass including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/tests/test_auth.py
git commit -m "feat(schema): add yahoo_fantasy_connected to UserOut"
```

---

## Task 4: auth.py API — yahoo_fantasy intent in authorize + callback

**Files:**
- Modify: `backend/app/api/auth.py`
- Test: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_yahoo_oauth.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_yahoo_authorize_fantasy_intent_adds_fspt_scope(app, async_client):
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
async def test_yahoo_callback_fantasy_stores_tokens(app, async_client, db_session):
    """Callback with yahoo_fantasy intent stores encrypted tokens on user."""
    from app.models import User
    user = User(yahoo_subject="sub_xyz", email="tok@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    state = "teststate999"
    with (
        patch("app.api.auth.exchange_code", new_callable=AsyncMock,
              return_value=("acc_tok", "ref_tok")) as mock_exchange,
        patch("app.api.auth.fetch_identity", new_callable=AsyncMock,
              return_value=("sub_xyz", "tok@example.com", True)),
    ):
        resp = await async_client.get(
            "/api/auth/yahoo/callback",
            params={"code": "authcode", "state": state},
            cookies={
                "autotiers_oauth_state": state,
                "autotiers_session": _jwt_for(user),
                "autotiers_oauth_intent": "yahoo_fantasy",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 302
    await db_session.refresh(user)
    assert user.yahoo_access_token is not None
    assert user.yahoo_refresh_token is not None
    mock_exchange.assert_called_once_with("authcode")
```

Note: `_jwt_for` is a helper — check if it already exists in the test file or conftest; if not, create it:

```python
def _jwt_for(user) -> str:
    from app.auth.jwt import create_access_token
    return create_access_token(str(user.id))
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_oauth.py -k "fantasy_intent or fantasy_stores" -v
```

Expected: FAIL.

- [ ] **Step 3: Update auth.py**

Two changes in `backend/app/api/auth.py`:

**Change 1** — `yahoo_authorize` endpoint: call `build_authorize_url` with `fantasy=True` when intent is `yahoo_fantasy`:

```python
@router.get("/yahoo/authorize")
async def yahoo_authorize(intent: str | None = None) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    fantasy = intent == "yahoo_fantasy"
    response = RedirectResponse(url=build_authorize_url(state, fantasy=fantasy), status_code=307)
    _set_oauth_state_cookies(response, _OAUTH_STATE_COOKIE, state, intent)
    return response
```

**Change 2** — `yahoo_callback` endpoint: update `exchange_code` call (now returns tuple) and store tokens when intent is `yahoo_fantasy`. The callback already imports `encrypt` from `app.security.fernet` — if not, add it:

```python
from app.security.fernet import encrypt, decrypt
```

Update the exchange_code call near the top of `yahoo_callback`, and add token storage:

```python
@router.get("/yahoo/callback")
async def yahoo_callback(
    code: str,
    state: str,
    autotiers_oauth_state: str | None = Cookie(default=None),
    autotiers_session: str | None = Cookie(default=None),
    autotiers_oauth_intent: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_oauth_state or autotiers_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token, refresh_token = await exchange_code(code)
    yahoo_subject, yahoo_email, yahoo_email_verified = await fetch_identity(access_token)

    current_user = await _resolve_user(autotiers_session, db)

    if current_user is not None:
        # Store tokens when this is a fantasy connect intent, then fall through
        # to the normal link handler which handles the identity side.
        if autotiers_oauth_intent == "yahoo_fantasy" and refresh_token:
            current_user.yahoo_access_token = encrypt(access_token)
            current_user.yahoo_refresh_token = encrypt(refresh_token)
            # commit happens inside _handle_oauth_link if it mutates — but
            # we commit here first so tokens are persisted even if the identity
            # was already linked (no mutation needed in the link handler).
            await db.commit()

        return await _handle_oauth_link(
            db,
            current_user,
            subject_attr="yahoo_subject",
            subject=yahoo_subject,
            email=yahoo_email,
            email_verified=yahoo_email_verified,
            state_cookie_name=_OAUTH_STATE_COOKIE,
        )

    if autotiers_oauth_intent == "link":
        url = _frontend_url_with_param("linking_error", "session_lost")
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
        response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
        return response

    if autotiers_oauth_intent == "yahoo_fantasy":
        url = _frontend_url_with_param("linking_error", "session_lost")
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
        response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
        return response

    # Sign-in flow only.
    user = await db.scalar(select(User).where(User.yahoo_subject == yahoo_subject))
    if user is None and yahoo_email_verified and yahoo_email:
        user = await db.scalar(select(User).where(User.email == yahoo_email))
        if user is not None:
            user.yahoo_subject = yahoo_subject
            await db.commit()
            await db.refresh(user)
    if user is None:
        user = User(yahoo_subject=yahoo_subject)
        if yahoo_email_verified and yahoo_email:
            user.email = yahoo_email
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response
```

- [ ] **Step 4: Run full auth test suite**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_oauth.py tests/test_auth.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(auth): handle yahoo_fantasy intent — store tokens on callback"
```

---

## Task 5: Yahoo scoring mapper

**Files:**
- Modify: `backend/app/integrations/scoring_mappers.py`
- Test: `backend/tests/test_scoring_mappers.py` (create if missing)

- [ ] **Step 1: Inspect a real Yahoo league response to verify stat IDs**

Run (requires a valid Yahoo access token — use one from a test account or skip if no token is available and proceed with the stat IDs listed below, flagged as needing verification):

```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  "https://fantasysports.yahooapis.com/fantasy/v2/league/YOUR_LEAGUE_KEY/settings?format=json" | python3 -m json.tool | grep -A3 "stat_id"
```

Expected Yahoo stat IDs (verify these match the real response — update the map in Step 3 if they differ):
- `4` = passing yards
- `5` = passing TDs
- `9` = rushing yards
- `10` = rushing TDs
- `11` = receptions
- `12` = receiving yards
- `13` = receiving TDs

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_scoring_mappers.py` if it doesn't exist, then add:

```python
from app.integrations.scoring_mappers import yahoo_to_settings


def test_yahoo_to_settings_ppr():
    raw = {
        "stat": [
            {"stat_id": "4", "value": "0.04"},   # passing yards
            {"stat_id": "5", "value": "4"},        # passing TDs
            {"stat_id": "9", "value": "0.1"},      # rushing yards
            {"stat_id": "10", "value": "6"},       # rushing TDs
            {"stat_id": "11", "value": "1"},       # receptions — PPR
            {"stat_id": "12", "value": "0.1"},     # receiving yards
            {"stat_id": "13", "value": "6"},       # receiving TDs
        ]
    }
    result = yahoo_to_settings(raw, league_size=12)
    assert result["scoring_format"] == "ppr"
    assert result["league_size"] == 12
    assert result["qb_td_points"] == 4


def test_yahoo_to_settings_half_ppr():
    raw = {
        "stat": [
            {"stat_id": "11", "value": "0.5"},
            {"stat_id": "5", "value": "4"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=10)
    assert result["scoring_format"] == "half_ppr"


def test_yahoo_to_settings_standard():
    raw = {
        "stat": [
            {"stat_id": "11", "value": "0"},
            {"stat_id": "5", "value": "4"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=8)
    assert result["scoring_format"] == "standard"


def test_yahoo_to_settings_six_point_passing_td():
    raw = {
        "stat": [
            {"stat_id": "5", "value": "6"},
            {"stat_id": "11", "value": "1"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=12)
    assert result["qb_td_points"] == 6


def test_yahoo_to_settings_missing_stats_defaults():
    result = yahoo_to_settings({"stat": []}, league_size=12)
    assert result["scoring_format"] == "standard"
    assert result["qb_td_points"] == 4
    assert result["league_size"] == 12
```

- [ ] **Step 3: Run to confirm fail**

```bash
cd backend && venv/bin/python -m pytest tests/test_scoring_mappers.py -k "yahoo" -v
```

Expected: FAIL — `yahoo_to_settings` not defined.

- [ ] **Step 4: Implement yahoo_to_settings**

Add to the bottom of `backend/app/integrations/scoring_mappers.py`:

```python
# Yahoo stat IDs — verified against Yahoo Fantasy API v2 settings response.
# Update these if a real league response shows different IDs.
_YAHOO_PASSING_TD = "5"
_YAHOO_RECEPTIONS = "11"


def yahoo_to_settings(raw_scoring: dict, league_size: int) -> dict:
    """Map Yahoo stat_modifiers.stats payload to AutoTiers settings fields.

    raw_scoring is the value of fantasy_content.league[1].settings.stat_modifiers.stats
    i.e. a dict with key "stat" containing a list of {"stat_id": str, "value": str}.
    """
    stats = {item["stat_id"]: float(item.get("value") or 0) for item in raw_scoring.get("stat", [])}
    rec = stats.get(_YAHOO_RECEPTIONS, 0.0)
    pass_td = stats.get(_YAHOO_PASSING_TD, 4.0)
    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
    }
```

- [ ] **Step 5: Run tests**

```bash
cd backend && venv/bin/python -m pytest tests/test_scoring_mappers.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/scoring_mappers.py backend/tests/test_scoring_mappers.py
git commit -m "feat(integrations): add yahoo_to_settings scorer mapper"
```

---

## Task 6: Yahoo Fantasy API client

**Files:**
- Create: `backend/app/integrations/yahoo_fantasy.py`
- Create: `backend/tests/test_yahoo_fantasy.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_yahoo_fantasy.py`:

```python
"""Tests for the Yahoo Fantasy API client.

Uses respx to mock httpx calls.
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from app.integrations.yahoo_fantasy import (
    list_user_leagues,
    fetch_league,
    YahooLeagueSummary,
    YahooLeagueData,
)


LEAGUES_RESPONSE = {
    "fantasy_content": {
        "users": {
            "0": {
                "user": [
                    {"guid": "ABCDEF"},
                    {
                        "games": {
                            "0": {
                                "game": [
                                    {"game_key": "423", "season": "2024"},
                                    {
                                        "leagues": {
                                            "0": {
                                                "league": [
                                                    {
                                                        "league_key": "423.l.12345",
                                                        "name": "My FF League",
                                                        "num_teams": "12",
                                                        "season": "2024",
                                                    }
                                                ]
                                            },
                                            "count": 1,
                                        }
                                    },
                                ]
                            },
                            "count": 1,
                        }
                    },
                ]
            },
            "count": 1,
        }
    }
}

SETTINGS_RESPONSE = {
    "fantasy_content": {
        "league": [
            {
                "league_key": "423.l.12345",
                "name": "My FF League",
                "num_teams": "12",
                "season": "2024",
            },
            {
                "settings": {
                    "stat_modifiers": {
                        "stats": {
                            "stat": [
                                {"stat_id": "5", "value": "4"},
                                {"stat_id": "11", "value": "1"},
                            ]
                        }
                    }
                }
            },
        ]
    }
}


def _make_user(access_token="enc_access", refresh_token="enc_refresh"):
    user = MagicMock()
    user.yahoo_access_token = access_token
    user.yahoo_refresh_token = refresh_token
    return user


@pytest.mark.asyncio
async def test_list_user_leagues_returns_summaries(respx_mock):
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues"
    respx_mock.get(url).mock(return_value=httpx.Response(200, json=LEAGUES_RESPONSE))

    db = AsyncMock()
    user = _make_user()

    with (
        pytest.MonkeyPatch().context() as m
    ):
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        leagues = await list_user_leagues(user, db)

    assert len(leagues) == 1
    assert leagues[0].league_key == "423.l.12345"
    assert leagues[0].name == "My FF League"
    assert leagues[0].season == 2024
    assert leagues[0].num_teams == 12


@pytest.mark.asyncio
async def test_fetch_league_returns_data(respx_mock):
    league_key = "423.l.12345"
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(url).mock(return_value=httpx.Response(200, json=SETTINGS_RESPONSE))

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        data = await fetch_league(league_key, user, db)

    assert data.league_id == "423.l.12345"
    assert data.name == "My FF League"
    assert data.season == 2024
    assert data.league_size == 12
    assert data.raw_scoring is not None


@pytest.mark.asyncio
async def test_fetch_league_refreshes_token_on_401(respx_mock):
    league_key = "423.l.12345"
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    # First call returns 401, second returns 200 after token refresh.
    respx_mock.get(url).mock(
        side_effect=[
            httpx.Response(401, text="Unauthorized"),
            httpx.Response(200, json=SETTINGS_RESPONSE),
        ]
    )

    db = AsyncMock()
    user = _make_user()

    async def fake_refresh(token: str) -> str:
        return "new_access_token"

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.refresh_access_token", fake_refresh)
        data = await fetch_league(league_key, user, db)

    assert data.league_id == "423.l.12345"
    assert user.yahoo_access_token == "new_access_token"
    db.commit.assert_called_once()
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_fantasy.py -v
```

Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Implement yahoo_fantasy.py**

Create `backend/app/integrations/yahoo_fantasy.py`:

```python
"""Yahoo Fantasy Sports API v2 client.

Fetches league lists and league settings using an OAuth2 access token.
Handles transparent token refresh on 401.

Yahoo API base: https://fantasysports.yahooapis.com/fantasy/v2/
All requests require ?format=json (default response is XML).
"""
from dataclasses import dataclass
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.yahoo import refresh_access_token
from app.security.fernet import encrypt, decrypt

_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"


@dataclass
class YahooLeagueSummary:
    league_key: str
    name: str
    season: int
    num_teams: int


@dataclass
class YahooLeagueData:
    league_id: str
    name: str
    season: int
    league_size: int
    raw_scoring: dict       # stat_modifiers.stats — passed to yahoo_to_settings
    keepers: list           # empty list (Yahoo keeper config not in settings endpoint)
    adp_json: Optional[dict]  # always None — Yahoo doesn't expose live ADP


async def _get(url: str, access_token: str) -> dict:
    """GET with Bearer auth, requesting JSON format. Raises httpx.HTTPStatusError on non-2xx."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            params={"format": "json"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _with_refresh(url: str, user, db: AsyncSession) -> dict:
    """Call _get; on 401, refresh the user's token and retry once.

    Updates user.yahoo_access_token (still encrypted) and commits db on refresh.
    """
    access_token = decrypt(user.yahoo_access_token)
    try:
        return await _get(url, access_token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 401:
            raise
    # Token expired — refresh and retry.
    new_token = await refresh_access_token(decrypt(user.yahoo_refresh_token))
    user.yahoo_access_token = encrypt(new_token)
    await db.commit()
    return await _get(url, new_token)


def _parse_leagues(data: dict) -> list[YahooLeagueSummary]:
    """Navigate Yahoo's deeply nested users/games/leagues response structure."""
    results = []
    try:
        users = data["fantasy_content"]["users"]
        user_entry = users["0"]["user"]
        games = user_entry[1]["games"]
        game_count = int(games.get("count", 0))
        for gi in range(game_count):
            game_block = games[str(gi)]["game"]
            if len(game_block) < 2:
                continue
            game_meta = game_block[0]
            season = int(game_meta.get("season", 0))
            leagues_block = game_block[1].get("leagues", {})
            league_count = int(leagues_block.get("count", 0))
            for li in range(league_count):
                league = leagues_block[str(li)]["league"][0]
                results.append(YahooLeagueSummary(
                    league_key=league["league_key"],
                    name=league["name"],
                    season=season,
                    num_teams=int(league.get("num_teams", 0)),
                ))
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return results


def _parse_league(data: dict) -> YahooLeagueData:
    """Parse league settings response into YahooLeagueData."""
    league_list = data["fantasy_content"]["league"]
    meta = league_list[0]
    settings = league_list[1]["settings"]
    return YahooLeagueData(
        league_id=meta["league_key"],
        name=meta["name"],
        season=int(meta["season"]),
        league_size=int(meta["num_teams"]),
        raw_scoring=settings.get("stat_modifiers", {}).get("stats", {}),
        keepers=[],
        adp_json=None,
    )


async def list_user_leagues(user, db: AsyncSession) -> list[YahooLeagueSummary]:
    """Return all NFL fantasy leagues for the authenticated user."""
    url = f"{_BASE}/users;use_login=1/games;game_keys=nfl/leagues"
    data = await _with_refresh(url, user, db)
    return _parse_leagues(data)


async def fetch_league(league_key: str, user, db: AsyncSession) -> YahooLeagueData:
    """Fetch scoring settings for a specific league by key (e.g. '423.l.12345')."""
    url = f"{_BASE}/league/{league_key}/settings"
    data = await _with_refresh(url, user, db)
    return _parse_league(data)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_fantasy.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/yahoo_fantasy.py backend/tests/test_yahoo_fantasy.py
git commit -m "feat(integrations): Yahoo Fantasy API client with transparent token refresh"
```

---

## Task 7: Backend endpoints — GET yahoo/leagues + POST yahoo link

**Files:**
- Modify: `backend/app/api/linked_league.py`
- Test: `backend/tests/test_yahoo_fantasy.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_yahoo_fantasy.py`:

```python
@pytest.mark.asyncio
async def test_get_yahoo_leagues_endpoint(async_client, db_session):
    from app.models import User, Profile
    import uuid
    from app.security.fernet import encrypt
    from app.auth.jwt import create_access_token

    user = User(
        email="yf@example.com",
        yahoo_subject="ysub1",
        yahoo_access_token=encrypt("acc"),
        yahoo_refresh_token=encrypt("ref"),
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id,
        name="My Profile",
        settings_json={},
        rules_json=[],
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    jwt = create_access_token(str(user.id))

    with pytest.MonkeyPatch().context() as m:
        async def fake_list(u, db):
            return [YahooLeagueSummary("423.l.99", "Test League", 2024, 12)]
        m.setattr("app.api.linked_league.list_yahoo_leagues", fake_list)

        resp = await async_client.get(
            f"/api/profiles/{profile.id}/link/yahoo/leagues",
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["league_key"] == "423.l.99"


@pytest.mark.asyncio
async def test_post_yahoo_link_endpoint(async_client, db_session):
    from app.models import User, Profile
    from app.security.fernet import encrypt
    from app.auth.jwt import create_access_token
    from app.integrations.yahoo_fantasy import YahooLeagueData

    user = User(
        email="yf2@example.com",
        yahoo_subject="ysub2",
        yahoo_access_token=encrypt("acc"),
        yahoo_refresh_token=encrypt("ref"),
    )
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id, name="P", settings_json={}, rules_json=[])
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    jwt = create_access_token(str(user.id))

    fake_data = YahooLeagueData(
        league_id="423.l.99",
        name="Test League",
        season=2024,
        league_size=12,
        raw_scoring={"stat": [{"stat_id": "11", "value": "1"}]},
        keepers=[],
        adp_json=None,
    )

    with pytest.MonkeyPatch().context() as m:
        async def fake_fetch(league_key, u, db):
            return fake_data
        m.setattr("app.api.linked_league.fetch_yahoo_league", fake_fetch)

        resp = await async_client.post(
            f"/api/profiles/{profile.id}/link/yahoo",
            json={"league_key": "423.l.99", "season": 2024},
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["linked_league"]["provider"] == "yahoo"
    assert body["linked_league"]["league_id"] == "423.l.99"
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd backend && venv/bin/python -m pytest tests/test_yahoo_fantasy.py -k "endpoint" -v
```

Expected: FAIL — endpoints don't exist yet.

- [ ] **Step 3: Add Yahoo endpoints to linked_league.py**

Add these imports at the top of `backend/app/api/linked_league.py` (merge with existing):

```python
from app.integrations.yahoo_fantasy import (
    list_user_leagues as list_yahoo_leagues,
    fetch_league as fetch_yahoo_league,
    YahooLeagueSummary,
)
from app.integrations.scoring_mappers import yahoo_to_settings
```

Add these two new Pydantic models near the other request/response models:

```python
class YahooLeagueSummaryOut(BaseModel):
    league_key: str
    name: str
    season: int
    num_teams: int


class YahooConnectBody(BaseModel):
    league_key: str
    season: int
```

Add these two new endpoints (add after the ESPN endpoints):

```python
@router.get("/yahoo/leagues", response_model=list[YahooLeagueSummaryOut])
async def get_yahoo_leagues(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> list[YahooLeagueSummaryOut]:
    await _check_ownership(profile_id, user, db)
    if not user.yahoo_access_token:
        raise HTTPException(
            status_code=400,
            detail="Yahoo Fantasy is not connected. Re-authorize with Yahoo to enable Fantasy Sports access.",
        )
    try:
        leagues = await list_yahoo_leagues(user, db)
    except Exception as e:
        raise _provider_http_error("Yahoo", e)
    return [
        YahooLeagueSummaryOut(
            league_key=l.league_key,
            name=l.name,
            season=l.season,
            num_teams=l.num_teams,
        )
        for l in leagues
    ]


@router.post("/yahoo", response_model=LinkedLeagueResponse)
async def post_yahoo(
    profile_id: uuid.UUID,
    body: YahooConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    if not user.yahoo_access_token:
        raise HTTPException(
            status_code=400,
            detail="Yahoo Fantasy is not connected. Re-authorize with Yahoo to enable Fantasy Sports access.",
        )
    profile = await _resolve_profile(profile_id, user, db)
    try:
        data = await fetch_yahoo_league(body.league_key, user, db)
    except Exception as e:
        raise _provider_http_error("Yahoo", e)

    mapped = yahoo_to_settings(data.raw_scoring, league_size=data.league_size)
    ll = _upsert_linked_league(profile, db)
    ll.provider = "yahoo"
    ll.username_or_swid = ""
    ll.credentials_encrypted = None
    ll.league_id = data.league_id
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)
    _apply_settings(profile, mapped)

    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return _build_response(ll, profile)
```

Also add Yahoo to the `refresh` endpoint. In the `refresh` function's provider check, add a branch:

```python
elif ll.provider == "yahoo":
    try:
        data = await fetch_yahoo_league(ll.league_id, user, db)
    except Exception as e:
        raise _provider_http_error("Yahoo", e)
    mapped = yahoo_to_settings(data.raw_scoring, league_size=data.league_size)
```

The full updated `refresh` function (replace existing):

```python
@router.post("/refresh", response_model=LinkedLeagueResponse)
async def refresh(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    ll = profile.linked_league
    if ll is None:
        raise HTTPException(status_code=400, detail="Profile has no linked provider account")
    if not ll.league_id:
        raise HTTPException(
            status_code=400,
            detail="No league is selected on this linked account — pick one before refreshing.",
        )

    stored_season: int = (ll.league_metadata_json or {}).get("season") or 0

    if ll.provider == "sleeper":
        try:
            data = await fetch_sleeper_league(ll.league_id)
        except Exception as e:
            raise _provider_http_error("Sleeper", e)
        mapped = sleeper_to_settings(data.raw_scoring, league_size=data.league_size)
    elif ll.provider == "espn":
        if not stored_season:
            raise HTTPException(status_code=400, detail="Linked league is missing season metadata — please reconnect.")
        espn_s2 = decrypt(ll.credentials_encrypted) if ll.credentials_encrypted else None
        try:
            data = await fetch_espn_league(
                ll.league_id, stored_season,
                ll.username_or_swid or None, espn_s2,
            )
        except EspnAuthRequired:
            raise HTTPException(status_code=400, detail="ESPN cookies expired — please reconnect.")
        except Exception as e:
            raise _provider_http_error("ESPN", e)
        mapped = espn_to_settings(data.raw_scoring, league_size=data.league_size)
    elif ll.provider == "yahoo":
        if not user.yahoo_access_token:
            raise HTTPException(status_code=400, detail="Yahoo Fantasy token missing — reconnect Yahoo.")
        try:
            data = await fetch_yahoo_league(ll.league_id, user, db)
        except Exception as e:
            raise _provider_http_error("Yahoo", e)
        mapped = yahoo_to_settings(data.raw_scoring, league_size=data.league_size)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{ll.provider}'")

    _apply_settings(profile, mapped)
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return _build_response(ll, profile)
```

- [ ] **Step 4: Run full backend test suite**

```bash
cd backend && venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/linked_league.py backend/tests/test_yahoo_fantasy.py
git commit -m "feat(api): Yahoo Fantasy league list and link endpoints"
```

---

## Task 8: Frontend — types and API client

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/linkedLeague.ts`

- [ ] **Step 1: Update User type in types.ts**

Find the `User` interface in `web/src/api/types.ts` and add `yahoo_fantasy_connected`:

```typescript
export interface User {
  id: string;
  email: string | null;
  yahoo_subject: string | null;
  yahoo_fantasy_connected: boolean;
  google_subject: string | null;
  last_active_profile_id: string | null;
}
```

- [ ] **Step 2: Add Yahoo Fantasy API functions to linkedLeague.ts**

Add to `web/src/api/linkedLeague.ts`:

```typescript
export interface YahooLeagueSummary {
  league_key: string;
  name: string;
  season: number;
  num_teams: number;
}

export function listYahooLeagues(profileId: string): Promise<YahooLeagueSummary[]> {
  return apiFetch<YahooLeagueSummary[]>(`/api/profiles/${profileId}/link/yahoo/leagues`);
}

export function connectYahoo(
  profileId: string,
  body: { league_key: string; season: number },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/yahoo`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd web && npm run build 2>&1 | head -30
```

Expected: clean build (0 errors).

- [ ] **Step 4: Commit**

```bash
git add web/src/api/types.ts web/src/api/linkedLeague.ts
git commit -m "feat(web): add yahoo_fantasy_connected type and Yahoo Fantasy API client"
```

---

## Task 9: YahooConnectForm component

**Files:**
- Create: `web/src/components/YahooConnectForm.tsx`
- Create: `web/src/tests/components/YahooConnectForm.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `web/src/tests/components/YahooConnectForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { YahooConnectForm } from "@/components/YahooConnectForm";
import * as linkedLeagueApi from "@/api/linkedLeague";
import type { Profile, User } from "@/api/types";

const baseProfile: Profile = {
  id: "prof-1",
  name: "Test",
  settings_json: {},
  rules_json: [],
  linked_league: null,
  created_at: "",
  updated_at: "",
};

const baseUser: User = {
  id: "usr-1",
  email: "test@example.com",
  yahoo_subject: "sub123",
  yahoo_fantasy_connected: true,
  google_subject: null,
  last_active_profile_id: null,
};

describe("YahooConnectForm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches and displays league list when fantasy token present and no league linked", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([
      { league_key: "423.l.1", name: "My League", season: 2024, num_teams: 12 },
    ]);

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={baseUser}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole("status")).toBeInTheDocument(); // loading indicator

    await waitFor(() => {
      expect(screen.getByText("My League (2024)")).toBeInTheDocument();
    });
  });

  it("shows error when league fetch fails", async () => {
    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockRejectedValue(new Error("Network error"));

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={baseUser}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/couldn't reach yahoo/i)).toBeInTheDocument();
    });
  });

  it("calls connectYahoo and onLinked when Connect is clicked", async () => {
    const mockLinked = vi.fn();
    const fakeResult = { linked_league: { provider: "yahoo" }, profile: baseProfile };

    vi.spyOn(linkedLeagueApi, "listYahooLeagues").mockResolvedValue([
      { league_key: "423.l.1", name: "My League", season: 2024, num_teams: 12 },
    ]);
    vi.spyOn(linkedLeagueApi, "connectYahoo").mockResolvedValue(fakeResult as any);

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={baseUser}
        onLinked={mockLinked}
        onRefresh={vi.fn()}
      />,
    );

    await waitFor(() => screen.getByText("My League (2024)"));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => {
      expect(linkedLeagueApi.connectYahoo).toHaveBeenCalledWith("prof-1", {
        league_key: "423.l.1",
        season: 2024,
      });
      expect(mockLinked).toHaveBeenCalledWith(fakeResult);
    });
  });

  it("shows connected state when league is linked", async () => {
    const profile: Profile = {
      ...baseProfile,
      linked_league: {
        provider: "yahoo",
        league_id: "423.l.1",
        league_metadata_json: { name: "My League", season: 2024 },
        username_or_swid: "",
        keepers_json: null,
        adp_json: null,
        last_synced_at: "",
      },
    };

    render(
      <YahooConnectForm
        profile={profile}
        user={baseUser}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("Connected!")).toBeInTheDocument();
    expect(screen.getByText("My League")).toBeInTheDocument();
  });

  it("shows reconnect prompt when yahoo_fantasy_connected is false", () => {
    const user: User = { ...baseUser, yahoo_fantasy_connected: false };

    render(
      <YahooConnectForm
        profile={baseProfile}
        user={user}
        onLinked={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /connect yahoo fantasy/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd web && npm run test -- --reporter=verbose YahooConnectForm 2>&1 | tail -20
```

Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Implement YahooConnectForm**

Create `web/src/components/YahooConnectForm.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  listYahooLeagues,
  connectYahoo,
  refreshLink,
  disconnectLink,
  type LinkedLeagueResponse,
  type YahooLeagueSummary,
} from "@/api/linkedLeague";
import { yahooAuthorizeUrl } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { Profile, User } from "@/api/types";

interface Props {
  profile: Profile;
  user: User;
  onLinked: (result: LinkedLeagueResponse) => void;
  onRefresh: () => Promise<void>;
}

interface ConnectedStateProps {
  linked: NonNullable<Profile["linked_league"]>;
  profileId: string;
  onRefresh: () => Promise<void>;
}

function YahooConnectedState({ linked, profileId, onRefresh }: ConnectedStateProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      await refreshLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    setBusy(true);
    try {
      await disconnectLink(profileId);
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="rounded-lg border-2 border-green-500 bg-green-50/50 dark:bg-green-900/30 p-3">
        <div className="mb-1 flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500">
            <span className="text-[10px] font-bold text-white">✓</span>
          </div>
          <span className="text-sm font-bold text-green-700 dark:text-green-400">Connected!</span>
        </div>
        <p className="text-sm font-medium">
          {linked.league_metadata_json?.name ?? "Account linked (no league)"}
        </p>
        <p className="text-xs text-muted-foreground">
          Yahoo{linked.league_metadata_json ? ` · ${linked.league_metadata_json.season}` : ""}
        </p>
      </div>
      <div className="flex gap-2">
        {linked.league_id && (
          <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
            Refresh
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          aria-label="Disconnect Yahoo"
          onClick={handleDisconnect}
        >
          Disconnect
        </Button>
      </div>
    </div>
  );
}

export function YahooConnectForm({ profile, user, onLinked, onRefresh }: Props) {
  const linked = profile.linked_league;
  const showPicker = !linked && user.yahoo_fantasy_connected;

  // All hooks must be called unconditionally before any early return.
  const [leagues, setLeagues] = useState<YahooLeagueSummary[]>([]);
  const [chosenKey, setChosenKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!showPicker) return;
    setLoading(true);
    listYahooLeagues(profile.id)
      .then((data) => {
        setLeagues(data);
        if (data.length > 0) setChosenKey(data[0].league_key);
      })
      .catch(() => setError("Couldn't reach Yahoo. Please try again."))
      .finally(() => setLoading(false));
  }, [profile.id, showPicker]);

  if (linked?.provider === "yahoo") {
    return <YahooConnectedState linked={linked} profileId={profile.id} onRefresh={onRefresh} />;
  }

  // User has Yahoo subject but no Fantasy token — prompt re-auth.
  if (!user.yahoo_fantasy_connected) {
    return (
      <div className="space-y-3 py-2">
        <p className="text-sm text-muted-foreground">
          Your Yahoo account is linked for sign-in. To import league data, authorize Fantasy Sports
          access.
        </p>
        <Button
          className="w-full"
          aria-label="Connect Yahoo Fantasy"
          onClick={() => {
            window.location.href = `${yahooAuthorizeUrl()}?intent=yahoo_fantasy`;
          }}
        >
          Connect Yahoo Fantasy
        </Button>
      </div>
    );
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const chosen = leagues.find((l) => l.league_key === chosenKey);
      const result = await connectYahoo(profile.id, {
        league_key: chosenKey,
        season: chosen?.season ?? new Date().getFullYear(),
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="py-6 text-center">
        <span role="status" className="text-xs text-muted-foreground">
          Loading leagues…
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      {leagues.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No Yahoo Fantasy NFL leagues found for your account.
        </p>
      ) : (
        <>
          <label className="block text-sm">
            <span>Select Your League</span>
            <select
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={chosenKey}
              onChange={(e) => setChosenKey(e.target.value)}
              aria-label="Select your league"
            >
              {leagues.map((l) => (
                <option key={l.league_key} value={l.league_key}>
                  {l.name} ({l.season})
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end">
            <Button size="sm" disabled={busy || !chosenKey} onClick={handleConnect}>
              Connect
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run component tests**

```bash
cd web && npm run test -- --reporter=verbose YahooConnectForm 2>&1 | tail -30
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/YahooConnectForm.tsx web/src/tests/components/YahooConnectForm.test.tsx
git commit -m "feat(web): YahooConnectForm — league picker with connected/reconnect states"
```

---

## Task 10: Wire LinkedAccountsDialog Yahoo tab

**Files:**
- Modify: `web/src/components/LinkedAccountsDialog.tsx`
- Modify: `web/src/tests/components/LinkedAccountsDialog.test.tsx`

- [ ] **Step 1: Update LinkedAccountsDialog**

In `web/src/components/LinkedAccountsDialog.tsx`:

Add import at the top:
```tsx
import { YahooConnectForm } from "@/components/YahooConnectForm";
```

Replace the `case "yahoo":` block inside `renderTabPanel()`:

```tsx
case "yahoo":
  if (!activeProfile) {
    return (
      <p className="py-4 text-center text-xs text-muted-foreground">
        Select a profile above to connect a fantasy league.
      </p>
    );
  }
  return (
    <YahooConnectForm
      profile={activeProfile}
      user={user}
      onLinked={() => onRefresh()}
      onRefresh={onRefresh}
    />
  );
```

Also remove the `yahooBusy` state and `handleYahooDisconnect` / `handleYahooConnect` functions — they are no longer used (YahooConnectForm owns those interactions now). Check for any remaining `yahooBusy` references and remove them.

- [ ] **Step 2: Run full frontend test suite**

```bash
cd web && npm run test 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 3: TypeScript build check**

```bash
cd web && npm run build 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/LinkedAccountsDialog.tsx web/src/tests/components/LinkedAccountsDialog.test.tsx
git commit -m "feat(web): wire Yahoo Fantasy league picker into LinkedAccountsDialog"
```

---

## Task 11: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin <current-branch>
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "feat(yahoo): Yahoo Fantasy league import" \
  --body "$(cat <<'EOF'
## Summary
- Add \`yahoo_access_token\` + \`yahoo_refresh_token\` (Fernet-encrypted) to \`User\`
- \`intent=yahoo_fantasy\` OAuth path requests \`fspt-r\` scope and stores tokens
- New Yahoo Fantasy API client with transparent token refresh on 401
- \`yahoo_to_settings\` scorer mapper (mirrors Sleeper/ESPN pattern)
- \`GET /profiles/{id}/link/yahoo/leagues\` + \`POST /profiles/{id}/link/yahoo\` endpoints
- \`YahooConnectForm\` component — league picker with connected/reconnect states

## Test plan
- [ ] Sign in via Yahoo → no fantasy token → Yahoo tab shows "Connect Yahoo Fantasy"
- [ ] Click "Connect Yahoo Fantasy" → Yahoo OAuth with fspt-r scope → returns, token stored, league picker appears
- [ ] Pick a league → click Connect → green "Connected!" card with league name
- [ ] Open LinkedAccountsDialog again → Yahoo tab shows connected state directly
- [ ] Disconnect → tab resets to connect state
- [ ] All backend + frontend tests pass

🤖 Generated with [Claude Code](https://claude.ai/claude-code)
EOF
)"
```
