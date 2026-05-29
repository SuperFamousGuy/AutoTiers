# Account Linking + OAuth Email Dedupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let signed-in users link Yahoo/Google to their account, and stop "Continue with Google/Yahoo" from creating duplicates when the OAuth email matches an existing user.

**Architecture:** Extend OAuth callbacks to request `email` scope, trust `email_verified` for sign-in auto-link, and branch on auth cookie presence to handle link-vs-sign-in. Add unlink endpoints that reject if last sign-in method. Frontend gets a new "Linked accounts" dialog driven by `/me` payload state.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async, pytest + respx, React + TypeScript + Vitest + MSW, shadcn/ui dialogs.

**Spec:** `docs/superpowers/specs/2026-05-29-account-linking-design.md`

**Working branch:** `feat/account-linking` (already created from main).

---

## File Structure

**Backend — modified:**
- `backend/app/auth/google.py` — request email scope, replace `fetch_subject` → `fetch_identity`.
- `backend/app/auth/yahoo.py` — same.
- `backend/app/api/auth.py` — callback logic gains link-vs-signin branching; new `DELETE /{provider}/link` routes.
- `backend/app/schemas/auth.py` — add `google_subject` to `UserOut`.

**Backend — tests modified/added:**
- `backend/tests/test_google_oauth.py` — update fetch_subject tests to new signature; add identity + linking + auto-link cases.
- `backend/tests/test_yahoo_oauth.py` — same matrix as Google.
- `backend/tests/test_auth_unlink.py` (new) — unlink endpoint tests for both providers.

**Frontend — modified:**
- `web/src/api/types.ts` — add `google_subject` to `User`.
- `web/src/api/auth.ts` — add `unlinkYahoo`, `unlinkGoogle`.
- `web/src/components/Header.tsx` — add "Linked accounts" menu item.
- `web/src/App.tsx` — detect `linking_error` query param on mount, open dialog, strip param.

**Frontend — created:**
- `web/src/components/LinkedAccountsDialog.tsx` — provider connect/disconnect dialog.

**Frontend — tests added:**
- `web/src/tests/api/auth-unlink.test.ts` (new) — unit tests for unlink helpers.
- `web/src/tests/components/LinkedAccountsDialog.test.tsx` (new) — render + interaction tests.
- `web/src/tests/integration/app-authenticated.test.tsx` — extend with hamburger "Linked accounts" item + `linking_error` URL handling.

---

## Task 1: Surface `google_subject` in API + frontend types

**Why first:** the dialog and tests in later tasks read `user.google_subject`. Add it before anything depends on it.

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `web/src/api/types.ts`
- Modify: `backend/tests/test_google_oauth.py` (assertion only)

- [ ] **Step 1: Write failing backend assertion**

Add at the end of the existing `test_callback_creates_new_user_on_first_login` test in `backend/tests/test_google_oauth.py`:

```python
    # Also assert /me exposes google_subject
    me = await async_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["google_subject"] == "google-user-xyz"
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd backend && pytest tests/test_google_oauth.py::test_callback_creates_new_user_on_first_login -v
```

Expected: FAIL — `KeyError: 'google_subject'` (schema currently lacks the field).

- [ ] **Step 3: Add `google_subject` to `UserOut`**

In `backend/app/schemas/auth.py`, change `UserOut`:

```python
class UserOut(BaseModel):
    id: uuid.UUID
    email: Optional[str]
    yahoo_subject: Optional[str]
    google_subject: Optional[str]
    last_active_profile_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run backend test, expect pass**

```bash
cd backend && pytest tests/test_google_oauth.py -v
```

Expected: all pass.

- [ ] **Step 5: Add `google_subject` to frontend `User` type**

In `web/src/api/types.ts`, change the `User` interface to:

```typescript
export interface User {
  id: string;
  email: string | null;
  yahoo_subject: string | null;
  google_subject: string | null;
  last_active_profile_id: string | null;
}
```

- [ ] **Step 6: Update frontend test fixtures**

In `web/src/tests/integration/app-authenticated.test.tsx`, the `USER` const needs the new field. Change:

```typescript
const USER = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  google_subject: null,
  last_active_profile_id: "p1",
};
```

Search the repo for any other test that builds a `User` literal and add `google_subject: null`:

```bash
grep -rn "yahoo_subject: null" web/src/tests/
```

For each match (e.g. `web/src/tests/api/auth.test.ts`), add `google_subject: null` next to it.

- [ ] **Step 7: Run frontend tests**

```bash
cd web && npx vitest run
```

Expected: all 116 tests still pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/auth.py web/src/api/types.ts backend/tests/test_google_oauth.py web/src/tests/
git commit -m "feat(auth): expose google_subject on UserOut and User type"
```

---

## Task 2: Yahoo + Google `fetch_identity` returning verified email

**Files:**
- Modify: `backend/app/auth/google.py`
- Modify: `backend/app/auth/yahoo.py`
- Modify: `backend/tests/test_google_oauth.py`
- Modify: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing test for Google `fetch_identity`**

Replace the existing `test_fetch_subject_returns_sub_claim` in `backend/tests/test_google_oauth.py` with:

```python
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
```

Change the import at the top of the file from:

```python
from app.auth.google import build_authorize_url, exchange_code, fetch_subject
```

to:

```python
from app.auth.google import build_authorize_url, exchange_code, fetch_identity
```

Also update `test_build_authorize_url_includes_required_params` to assert the email scope:

```python
def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(state="random123")
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "state=random123" in url
    assert "scope=openid+email" in url or "scope=openid%20email" in url
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && pytest tests/test_google_oauth.py::test_fetch_identity_returns_subject_email_and_verified -v
```

Expected: FAIL — `ImportError: cannot import name 'fetch_identity'`.

- [ ] **Step 3: Implement `fetch_identity` and scope change in `google.py`**

In `backend/app/auth/google.py`, replace `fetch_subject` with `fetch_identity` and update the scope:

```python
def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "access_type": "online",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def fetch_identity(access_token: str) -> tuple[str, str | None, bool]:
    """Fetch the openid `sub`, `email`, and `email_verified` claims from Google's userinfo endpoint.

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
        return data["sub"], data.get("email"), bool(data.get("email_verified", False))
```

Also update the module docstring — replace its second paragraph with:

```python
"""Google OAuth2 client.

Used for identity: we exchange the auth code for a token, fetch the
subject + email + email_verified claims, and discard the token. We trust
`email_verified` for auto-linking on first sign-in — see the design doc's
"Email-collision policy" section.
"""
```

- [ ] **Step 4: Mirror changes in `yahoo.py`**

In `backend/app/auth/yahoo.py`, apply the same changes:

```python
def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.yahoo_redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def fetch_identity(access_token: str) -> tuple[str, str | None, bool]:
    """Fetch sub/email/email_verified from Yahoo's userinfo endpoint.

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
        return data["sub"], data.get("email"), bool(data.get("email_verified", False))
```

Update its docstring identically (just s/Google/Yahoo/).

- [ ] **Step 5: Update the API router import**

In `backend/app/api/auth.py`, change the imports at the top from:

```python
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_subject
from app.auth.google import (
    build_authorize_url as build_google_authorize_url,
    exchange_code as exchange_google_code,
    fetch_subject as fetch_google_subject,
)
```

to:

```python
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_identity
from app.auth.google import (
    build_authorize_url as build_google_authorize_url,
    exchange_code as exchange_google_code,
    fetch_identity as fetch_google_identity,
)
```

Inside the `yahoo_callback` handler, change:

```python
    access_token = await exchange_code(code)
    yahoo_subject = await fetch_subject(access_token)
```

to:

```python
    access_token = await exchange_code(code)
    yahoo_subject, yahoo_email, yahoo_email_verified = await fetch_identity(access_token)
```

(Variables `yahoo_email` and `yahoo_email_verified` are wired up in Task 3.)

Inside `google_callback`:

```python
    access_token = await exchange_google_code(code)
    google_subject, google_email, google_email_verified = await fetch_google_identity(access_token)
```

Until Task 3 lands, those new variables are unused — that's fine; pytest doesn't lint unused locals. If `ruff` is configured to flag them, prefix with `_`. Verify with:

```bash
cd backend && ruff check app/api/auth.py 2>&1 | head
```

If unused-variable warnings appear, rename to `_yahoo_email`, `_yahoo_email_verified`, etc., for this commit only — Task 3 reintroduces the names.

- [ ] **Step 6: Mirror tests in `test_yahoo_oauth.py`**

Apply the same changes in `backend/tests/test_yahoo_oauth.py`:
- Rename import `fetch_subject` → `fetch_identity`.
- Replace `test_fetch_subject_returns_sub_claim` with the two-test pattern (success + missing-email defaults), targeting Yahoo's userinfo URL (`https://api.login.yahoo.com`, path `/openid/v1/userinfo`).
- Update `test_build_authorize_url_includes_required_params` (if present) to assert the new scope.

- [ ] **Step 7: Run tests, expect pass**

```bash
cd backend && pytest tests/test_google_oauth.py tests/test_yahoo_oauth.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth/google.py backend/app/auth/yahoo.py backend/app/api/auth.py backend/tests/test_google_oauth.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(auth): request email scope and return identity tuple from OAuth providers"
```

---

## Task 3: Backend sign-in auto-link by verified email

**Files:**
- Modify: `backend/app/api/auth.py` — callback unauthenticated branch
- Modify: `backend/tests/test_google_oauth.py`
- Modify: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing test for auto-link by verified email (Google)**

Append to `backend/tests/test_google_oauth.py`:

```python
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
```

Also update `test_callback_creates_new_user_on_first_login` to assert verified email is stored on a brand-new user. Change the userinfo mock to include verified email and add the email assertion:

```python
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
```

(The existing trailing `me = await async_client.get("/api/auth/me")` block from Task 1 stays after this.)

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && pytest tests/test_google_oauth.py::test_callback_auto_links_when_email_matches_existing_user -v
```

Expected: FAIL — currently the callback always creates a new user when no subject match.

- [ ] **Step 3: Implement auto-link in `google_callback`**

In `backend/app/api/auth.py`, replace the body of `google_callback` from the `access_token = await exchange_google_code(...)` line through the `set_auth_cookie(...)` line with the new branching logic:

```python
@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    autotiers_google_oauth_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_google_oauth_state or autotiers_google_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token = await exchange_google_code(code)
    google_subject, google_email, google_email_verified = await fetch_google_identity(access_token)

    # Sign-in flow only — linking flow comes in Task 4.
    user = await db.scalar(select(User).where(User.google_subject == google_subject))
    if user is None and google_email_verified and google_email:
        user = await db.scalar(select(User).where(User.email == google_email))
        if user is not None:
            user.google_subject = google_subject  # auto-link
            await db.commit()
            await db.refresh(user)
    if user is None:
        user = User(google_subject=google_subject)
        if google_email_verified and google_email:
            user.email = google_email
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response
```

- [ ] **Step 4: Mirror in `yahoo_callback`**

Same restructure for the Yahoo handler in the same file, using the Yahoo names (`yahoo_subject`, `yahoo_email`, `yahoo_email_verified`, `_OAUTH_STATE_COOKIE`):

```python
@router.get("/yahoo/callback")
async def yahoo_callback(
    code: str,
    state: str,
    autotiers_oauth_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_oauth_state or autotiers_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token = await exchange_code(code)
    yahoo_subject, yahoo_email, yahoo_email_verified = await fetch_identity(access_token)

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
    set_auth_cookie(response, user.id)
    return response
```

- [ ] **Step 5: Add equivalent Yahoo tests**

Append two tests to `backend/tests/test_yahoo_oauth.py` mirroring the Google ones — same structure, but with `autotiers_oauth_state` cookie name (no `_google_` infix) and `User.yahoo_subject`/Yahoo userinfo URL. Update the existing "creates new user" Yahoo test the same way (verified email asserted).

- [ ] **Step 6: Run all OAuth tests**

```bash
cd backend && pytest tests/test_google_oauth.py tests/test_yahoo_oauth.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_google_oauth.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(auth): auto-link OAuth sign-in to existing account when email_verified"
```

---

## Task 4: Backend OAuth linking flow (authenticated callback)

**Files:**
- Modify: `backend/app/api/auth.py` — callback authenticated branch
- Modify: `backend/tests/test_google_oauth.py`
- Modify: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing test for linking when authenticated (Google)**

Append to `backend/tests/test_google_oauth.py`:

```python
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
    assert "linking_error" not in (r.headers["location"])
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
    assert "linking_error" not in (r.headers["location"])


@pytest.mark.asyncio
async def test_callback_redirects_with_linking_error_when_subject_on_other_user(async_client, test_db):
    # Other user owns the subject.
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
```

Note: the backfill test uses `encode_jwt(user_id)` from `app.auth.jwt` to mint a session token without going through the password-login path (the user has no password). The cookie name `JWT_COOKIE_NAME` is exported from the same module — it resolves to `"autotiers_session"`.

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && pytest tests/test_google_oauth.py -v -k "links_subject or no_op or linking_error or backfills"
```

Expected: failures — callback is not yet branching on auth state.

- [ ] **Step 3: Add link-vs-signin branching to `google_callback`**

In `backend/app/api/auth.py`, at the top add the dependency import:

```python
from app.auth.dependencies import _resolve_user
```

(`_resolve_user` already exists in `dependencies.py` and accepts an optional cookie + db.)

Refactor `google_callback` to accept the auth cookie and branch:

```python
@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    autotiers_google_oauth_state: str | None = Cookie(default=None),
    autotiers_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_google_oauth_state or autotiers_google_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token = await exchange_google_code(code)
    google_subject, google_email, google_email_verified = await fetch_google_identity(access_token)

    current_user = await _resolve_user(autotiers_session, db)

    if current_user is not None:
        # Linking flow.
        existing_owner = await db.scalar(
            select(User).where(User.google_subject == google_subject)
        )
        if existing_owner is not None and existing_owner.id != current_user.id:
            url = f"{settings.frontend_url}?linking_error=already_linked_elsewhere"
            response = RedirectResponse(url=url, status_code=302)
            response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
            return response
        if existing_owner is None:
            current_user.google_subject = google_subject
        if current_user.email is None and google_email_verified and google_email:
            current_user.email = google_email
        await db.commit()
        response = RedirectResponse(url=settings.frontend_url, status_code=302)
        response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
        return response

    # Sign-in flow (from Task 3, unchanged).
    user = await db.scalar(select(User).where(User.google_subject == google_subject))
    if user is None and google_email_verified and google_email:
        user = await db.scalar(select(User).where(User.email == google_email))
        if user is not None:
            user.google_subject = google_subject
            await db.commit()
            await db.refresh(user)
    if user is None:
        user = User(google_subject=google_subject)
        if google_email_verified and google_email:
            user.email = google_email
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response
```

Note: in the linking flow we do NOT call `set_auth_cookie` — the user is already logged in.

- [ ] **Step 4: Mirror in `yahoo_callback`**

Same structure for `yahoo_callback` in the same file, using `yahoo_subject`, `yahoo_email`, `yahoo_email_verified`, and `_OAUTH_STATE_COOKIE` (the Yahoo cookie name).

- [ ] **Step 5: Add equivalent Yahoo linking tests**

Append the same four tests to `backend/tests/test_yahoo_oauth.py`, using `yahoo_subject`, Yahoo URLs (`https://api.login.yahoo.com/oauth2/get_token`, `https://api.login.yahoo.com/openid/v1/userinfo`), and `autotiers_oauth_state` cookie.

- [ ] **Step 6: Run all OAuth tests**

```bash
cd backend && pytest tests/test_google_oauth.py tests/test_yahoo_oauth.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_google_oauth.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(auth): link OAuth provider to current user when authenticated"
```

---

## Task 5: Backend unlink endpoints

**Files:**
- Modify: `backend/app/api/auth.py` — add `DELETE /{provider}/link` routes
- Create: `backend/tests/test_auth_unlink.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_auth_unlink.py`:

```python
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
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && pytest tests/test_auth_unlink.py -v
```

Expected: 404s (routes don't exist).

- [ ] **Step 3: Add unlink endpoints**

At the bottom of `backend/app/api/auth.py`, add:

```python
def _has_other_method(user: User, removing: str) -> bool:
    """True if the user has at least one sign-in method besides `removing`.

    `removing` is one of: "password", "yahoo_subject", "google_subject".
    """
    methods = {
        "password": user.password_hash is not None,
        "yahoo_subject": user.yahoo_subject is not None,
        "google_subject": user.google_subject is not None,
    }
    methods[removing] = False
    return any(methods.values())


@router.delete("/google/link", status_code=204)
async def unlink_google(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.google_subject is None:
        return  # idempotent
    if not _has_other_method(user, "google_subject"):
        raise HTTPException(status_code=400, detail="Cannot unlink last sign-in method")
    user.google_subject = None
    await db.commit()


@router.delete("/yahoo/link", status_code=204)
async def unlink_yahoo(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.yahoo_subject is None:
        return
    if not _has_other_method(user, "yahoo_subject"):
        raise HTTPException(status_code=400, detail="Cannot unlink last sign-in method")
    user.yahoo_subject = None
    await db.commit()
```

- [ ] **Step 4: Run tests, expect pass**

```bash
cd backend && pytest tests/test_auth_unlink.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_auth_unlink.py
git commit -m "feat(auth): add DELETE /api/auth/{provider}/link endpoints with last-method guard"
```

---

## Task 6: Frontend `unlinkYahoo` / `unlinkGoogle`

**Files:**
- Modify: `web/src/api/auth.ts`
- Create: `web/src/tests/api/auth-unlink.test.ts`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/api/auth-unlink.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import { unlinkGoogle, unlinkYahoo } from "@/api/auth";
import { ApiError } from "@/api/client";

describe("unlink helpers", () => {
  afterEach(() => vi.restoreAllMocks());

  it("unlinkGoogle DELETEs /api/auth/google/link", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await unlinkGoogle();
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/google/link");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("unlinkYahoo DELETEs /api/auth/yahoo/link", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await unlinkYahoo();
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/yahoo/link");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("unlinkGoogle throws ApiError on non-2xx", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("Cannot unlink last sign-in method", { status: 400 }),
    );
    await expect(unlinkGoogle()).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd web && npx vitest run src/tests/api/auth-unlink.test.ts
```

Expected: FAIL — `unlinkGoogle` / `unlinkYahoo` not exported.

- [ ] **Step 3: Implement helpers**

Append to `web/src/api/auth.ts`:

```typescript
async function unlinkProvider(path: string): Promise<void> {
  // Raw fetch because 204 No Content; check resp.ok so non-2xx surfaces.
  const resp = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
}

export function unlinkGoogle(): Promise<void> {
  return unlinkProvider("/api/auth/google/link");
}

export function unlinkYahoo(): Promise<void> {
  return unlinkProvider("/api/auth/yahoo/link");
}
```

- [ ] **Step 4: Run test, expect pass**

```bash
cd web && npx vitest run src/tests/api/auth-unlink.test.ts
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/auth.ts web/src/tests/api/auth-unlink.test.ts
git commit -m "feat(auth): add unlinkGoogle and unlinkYahoo API helpers"
```

---

## Task 7: `LinkedAccountsDialog` component + Header menu item

**Files:**
- Create: `web/src/components/LinkedAccountsDialog.tsx`
- Modify: `web/src/components/Header.tsx`
- Create: `web/src/tests/components/LinkedAccountsDialog.test.tsx`

- [ ] **Step 1: Write failing component test**

Create `web/src/tests/components/LinkedAccountsDialog.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import type { User } from "@/api/types";

vi.mock("@/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/api/auth")>("@/api/auth");
  return {
    ...actual,
    unlinkGoogle: vi.fn(),
    unlinkYahoo: vi.fn(),
    googleAuthorizeUrl: () => "http://localhost:8000/api/auth/google/authorize",
    yahooAuthorizeUrl: () => "http://localhost:8000/api/auth/yahoo/authorize",
  };
});

const baseUser: User = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  google_subject: null,
  last_active_profile_id: null,
};

const noop = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LinkedAccountsDialog", () => {
  it("renders email and shows both providers as not connected", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^connect$/i })).toHaveLength(2);
  });

  it("shows Disconnect when a provider is connected", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getByRole("button", { name: /disconnect google/i })).toBeInTheDocument();
  });

  it("Disconnect calls unlinkGoogle then refresh", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const refresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={refresh}
        initialError={null}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    await waitFor(() => expect(unlinkGoogle).toHaveBeenCalled());
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("shows the API error message when Disconnect fails", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    const { ApiError } = await import("@/api/client");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, "Cannot unlink last sign-in method"),
    );
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop}
        initialError={null}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    expect(await screen.findByText(/last sign-in method/i)).toBeInTheDocument();
  });

  it("renders an initial error when provided", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={noop}
        initialError="This Google account is already linked to a different AutoTiers account."
      />,
    );
    expect(screen.getByText(/already linked/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd web && npx vitest run src/tests/components/LinkedAccountsDialog.test.tsx
```

Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Implement the dialog**

Create `web/src/components/LinkedAccountsDialog.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { googleAuthorizeUrl, yahooAuthorizeUrl, unlinkGoogle, unlinkYahoo } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
  onRefresh: () => Promise<void>;
  initialError: string | null;
}

export function LinkedAccountsDialog({ open, onOpenChange, user, onRefresh, initialError }: Props) {
  const [error, setError] = useState<string | null>(initialError);
  const [busy, setBusy] = useState<"google" | "yahoo" | null>(null);

  // Refresh local error when initialError prop changes (e.g. dialog reopened with new error).
  useEffect(() => {
    setError(initialError);
  }, [initialError]);

  async function handleDisconnect(provider: "google" | "yahoo") {
    setError(null);
    setBusy(provider);
    try {
      if (provider === "google") await unlinkGoogle();
      else await unlinkYahoo();
      await onRefresh();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Disconnect failed. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  function handleConnect(provider: "google" | "yahoo") {
    // Full-page navigation; OAuth callback brings us back.
    window.location.href = provider === "google" ? googleAuthorizeUrl() : yahooAuthorizeUrl();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Linked accounts</DialogTitle>
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        <ul className="space-y-3">
          <li className="flex items-center justify-between">
            <span className="text-sm">Email</span>
            <span className="text-sm text-muted-foreground">
              {user.email ?? "Not set"}
            </span>
          </li>
          <li className="flex items-center justify-between">
            <span className="text-sm">Google</span>
            {user.google_subject ? (
              <Button
                size="sm"
                variant="outline"
                aria-label="Disconnect Google"
                disabled={busy === "google"}
                onClick={() => handleDisconnect("google")}
              >
                Disconnect
              </Button>
            ) : (
              <Button size="sm" onClick={() => handleConnect("google")}>
                Connect
              </Button>
            )}
          </li>
          <li className="flex items-center justify-between">
            <span className="text-sm">Yahoo</span>
            {user.yahoo_subject ? (
              <Button
                size="sm"
                variant="outline"
                aria-label="Disconnect Yahoo"
                disabled={busy === "yahoo"}
                onClick={() => handleDisconnect("yahoo")}
              >
                Disconnect
              </Button>
            ) : (
              <Button size="sm" onClick={() => handleConnect("yahoo")}>
                Connect
              </Button>
            )}
          </li>
        </ul>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Wire the dialog into the Header menu**

In `web/src/components/Header.tsx`, change `HamburgerMenu` to expose an open-dialog callback (rendered by `App.tsx`, which owns the dialog state since it needs to also auto-open on URL param).

Modify the props and authenticated branch:

```typescript
interface HamburgerProps {
  currentState: { settings: SettingsState; rules: Rule[] } | null;
  onOpenLinkedAccounts?: () => void;
}

function HamburgerMenu({ currentState, onOpenLinkedAccounts }: HamburgerProps) {
  const { user, logout } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Menu">
            <Menu className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {user ? (
            <>
              <DropdownMenuItem disabled>{user.email ?? "Yahoo account"}</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
                Linked accounts
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => logout()}>Log out</DropdownMenuItem>
            </>
          ) : (
            <DropdownMenuItem onSelect={() => setAuthOpen(true)}>Log in / Sign up</DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <AuthDialog open={authOpen} onOpenChange={setAuthOpen} initialState={currentState} />
    </>
  );
}
```

Then update the `HeaderProps` and the `Header` function to plumb the new prop through:

```typescript
interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
  currentState: { settings: SettingsState; rules: Rule[] } | null;
  profilePicker?: React.ReactNode;
  onOpenLinkedAccounts?: () => void;
}

export function Header({
  generateDisabled, generateIsPending, onGenerate, currentState, profilePicker, onOpenLinkedAccounts,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div className="flex items-baseline gap-6">
        <h1 className="text-2xl font-bold text-foreground">AutoTiers</h1>
        <DataFreshness />
      </div>
      <div className="flex items-center gap-3">
        {profilePicker}
        <GenerateButton
          disabled={generateDisabled}
          isPending={generateIsPending}
          onClick={onGenerate}
        />
        <HamburgerMenu currentState={currentState} onOpenLinkedAccounts={onOpenLinkedAccounts} />
      </div>
    </header>
  );
}
```

- [ ] **Step 5: Run component tests, expect pass**

```bash
cd web && npx vitest run src/tests/components/LinkedAccountsDialog.test.tsx
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/LinkedAccountsDialog.tsx web/src/components/Header.tsx web/src/tests/components/LinkedAccountsDialog.test.tsx
git commit -m "feat(ui): add LinkedAccountsDialog and Header menu item"
```

---

## Task 8: App-level wiring — open dialog from menu and on `linking_error` URL param

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/tests/integration/app-authenticated.test.tsx`

- [ ] **Step 1: Write failing integration tests**

Append to `web/src/tests/integration/app-authenticated.test.tsx`:

```typescript
  it("opens Linked accounts dialog from the hamburger menu", async () => {
    mockAuthenticated();
    renderApp();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));
    await user.click(screen.getByRole("menuitem", { name: /linked accounts/i }));
    expect(await screen.findByText(/^linked accounts$/i)).toBeInTheDocument();
  });

  it("auto-opens Linked accounts dialog with error when ?linking_error is present", async () => {
    mockAuthenticated();
    window.history.replaceState({}, "", "/?linking_error=already_linked_elsewhere");
    renderApp();
    await waitFor(() =>
      expect(screen.getByText(/already linked to a different AutoTiers account/i)).toBeInTheDocument(),
    );
    // URL param is stripped.
    expect(window.location.search).toBe("");
  });
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd web && npx vitest run src/tests/integration/app-authenticated.test.tsx -t "Linked accounts"
```

Expected: FAIL — no menu item, no auto-open.

- [ ] **Step 3: Wire dialog in `App.tsx`**

In `web/src/App.tsx`:

Add an import:

```typescript
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
```

Pull `refresh` out of `useAuth`:

```typescript
const { user, profiles, setProfiles, refresh } = useAuth();
```

Add state right next to `manageOpen`:

```typescript
const [linkedOpen, setLinkedOpen] = useState(false);
const [linkingError, setLinkingError] = useState<string | null>(null);
```

Add a mount effect to detect the URL param:

```typescript
// On first mount, surface OAuth linking failures the backend signalled via query param.
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("linking_error") === "already_linked_elsewhere") {
    setLinkingError("This Google or Yahoo account is already linked to a different AutoTiers account.");
    setLinkedOpen(true);
    params.delete("linking_error");
    const rest = params.toString();
    window.history.replaceState({}, "", window.location.pathname + (rest ? `?${rest}` : ""));
  }
}, []);
```

Pass the callback into `Header`:

```tsx
<Header
  generateDisabled={!canGenerate}
  generateIsPending={generate.isPending}
  onGenerate={() => generate.mutate(buildRequest())}
  currentState={{ settings, rules }}
  onOpenLinkedAccounts={user ? () => { setLinkingError(null); setLinkedOpen(true); } : undefined}
  profilePicker={user ? (
    /* ...existing profilePicker JSX unchanged... */
  ) : null}
/>
```

Render the dialog next to `ManageProfilesDialog` near the end of the component:

```tsx
{user && (
  <LinkedAccountsDialog
    open={linkedOpen}
    onOpenChange={setLinkedOpen}
    user={user}
    onRefresh={refresh}
    initialError={linkingError}
  />
)}
```

- [ ] **Step 4: Run tests, expect pass**

```bash
cd web && npx vitest run src/tests/integration/app-authenticated.test.tsx
```

Expected: all (now 11) pass.

- [ ] **Step 5: Run the full frontend suite as a sanity check**

```bash
cd web && npx vitest run
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/tests/integration/app-authenticated.test.tsx
git commit -m "feat(ui): open Linked accounts dialog from menu and on OAuth linking_error"
```

---

## Task 9: Full test sweep, push, open PR

- [ ] **Step 1: Full backend test run**

```bash
cd backend && pytest -q
```

Expected: green.

- [ ] **Step 2: Full frontend test run**

```bash
cd web && npx vitest run
```

Expected: green.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/account-linking
```

- [ ] **Step 4: Open PR**

```bash
gh pr create --title "feat(auth): account linking + OAuth email-verified dedupe" --body "$(cat <<'EOF'
## Summary
- Adds account linking: signed-in users can connect/disconnect Google or Yahoo via a new Linked accounts dialog.
- Stops "Continue with Google/Yahoo" from creating duplicate accounts when an existing user already has the OAuth-returned (verified) email — the new OAuth subject is attached to the existing account instead.
- Adds `DELETE /api/auth/{google,yahoo}/link` endpoints that reject if removal would leave the user with no sign-in method.

## Design
- Spec: `docs/superpowers/specs/2026-05-29-account-linking-design.md`
- OAuth scope now requests `email`. We trust `email_verified` for auto-linking.
- Callback branches on auth-cookie presence: linking flow when authenticated, sign-in flow otherwise.
- Subject-already-on-another-user surfaces via a `?linking_error=already_linked_elsewhere` redirect that auto-opens the dialog with the error.

## Test plan
- [x] Backend OAuth tests cover: subject match, email-verified auto-link, no-auto-link when unverified, new-user creation, linking when authed (success + idempotent + conflict + email backfill).
- [x] Backend unlink tests cover: success when other method present, last-method rejection, auth required.
- [x] Frontend tests cover: LinkedAccountsDialog render/connect/disconnect/error, menu item visible only when authenticated, URL-driven auto-open + strip.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.

---

## Notes for the implementer

- **Don't change the OAuth state cookie names** (`autotiers_oauth_state`, `autotiers_google_oauth_state`). Yahoo and Google must remain isolated so an in-progress flow on one provider can't be hijacked by the other.
- **`_resolve_user` is private (underscore-prefixed) but already used by existing dependency code.** Importing it directly is fine — it accepts `(cookie_value, db)`. If you'd prefer a public alias, factor one out, but don't gold-plate.
- **`set_auth_cookie` is only called in the sign-in branch.** Linking does not re-issue the cookie — the user already has a valid one.
- **The dialog is mounted inside `App.tsx` (not the Header)** because App owns the URL-param effect and the `refresh` function. The Header just signals "open it."
- **Frontend `User` literals appear in multiple test files.** After Task 1's `grep -rn "yahoo_subject: null" web/src/tests/`, add `google_subject: null` everywhere. Missing one will surface as a TypeScript error when running vitest.
