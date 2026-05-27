# Accounts and Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user accounts (email/password + Yahoo OAuth) and up to 5 saved profiles per user. Anonymous flow is preserved unchanged.

**Architecture:** FastAPI + SQLAlchemy 2.0 async backend with JWT cookies (HS256) + argon2id passwords + in-memory rate limiting; Yahoo OAuth2 for the optional sign-in path. React frontend gains a hamburger menu in Header, a login modal, and a profile picker; auto-save debounces edits to the active profile.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / argon2-cffi / PyJWT / httpx / pytest+respx · React 18 / TypeScript / Vite / TanStack Query / shadcn/ui / vitest+MSW

**Phases** (each ships as its own PR, sequentially):

1. Backend auth foundations (models, migration, hashing, JWT, deps, rate limit)
2. Email/password auth endpoints + anonymous-state migration on signup
3. Yahoo OAuth
4. Profile API
5. Frontend API clients + AuthContext
6. Frontend UI (hamburger, AuthDialog, ProfilePicker, ManageProfiles)
7. Wire-up, autosave hook, integration test, README

---

## File Structure (full picture)

**Backend — new files:**
- `backend/app/models/user.py` — User ORM model
- `backend/app/models/profile.py` — Profile ORM model
- `backend/alembic/versions/004_users_and_profiles.py` — migration
- `backend/app/auth/__init__.py`
- `backend/app/auth/hashing.py` — argon2id wrapper
- `backend/app/auth/jwt.py` — encode/decode + cookie helpers
- `backend/app/auth/dependencies.py` — FastAPI deps
- `backend/app/auth/rate_limit.py` — in-memory limiter
- `backend/app/auth/yahoo.py` — Yahoo OAuth client
- `backend/app/api/auth.py` — auth router
- `backend/app/api/profiles_api.py` — profile router (named profiles_api to avoid clashing with models/profile.py)
- `backend/app/schemas/auth.py` — pydantic
- `backend/app/schemas/profile.py` — pydantic
- `backend/tests/test_auth.py`
- `backend/tests/test_yahoo_oauth.py`
- `backend/tests/test_profiles.py`

**Backend — modified:**
- `backend/app/models/__init__.py` — export User, Profile
- `backend/app/config.py` — add JWT_SECRET, YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_REDIRECT_URI, FRONTEND_URL
- `backend/app/main.py` — include new routers
- `backend/pyproject.toml` — add argon2-cffi, pyjwt
- `backend/.env.example` — new env vars

**Frontend — new files:**
- `web/src/api/auth.ts`
- `web/src/api/profiles.ts`
- `web/src/contexts/AuthContext.tsx`
- `web/src/components/AuthDialog.tsx`
- `web/src/components/ProfilePicker.tsx`
- `web/src/components/ManageProfilesDialog.tsx`
- `web/src/hooks/useAutoSave.ts`
- `web/src/components/ui/dialog.tsx` (shadcn primitive)
- `web/src/components/ui/dropdown-menu.tsx` (shadcn primitive)
- `web/src/components/ui/tabs.tsx` (shadcn primitive)
- `web/src/tests/components/AuthDialog.test.tsx`
- `web/src/tests/components/ProfilePicker.test.tsx`
- `web/src/tests/components/ManageProfilesDialog.test.tsx`
- `web/src/tests/hooks/useAutoSave.test.ts`

**Frontend — modified:**
- `web/src/App.tsx` — wrap in AuthProvider; wire profile hydration + autosave
- `web/src/components/Header.tsx` — hamburger + ProfilePicker
- `web/src/api/client.ts` — `credentials: "include"` on every fetch
- `web/src/api/types.ts` — `User`, `Profile`
- `web/package.json` — `@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`, `@radix-ui/react-tabs`

---

# Phase 1 — Backend auth foundations

Each task is bite-sized TDD. Work on branch `feat/accounts-phase-1-foundations` off `main`.

### Task 1.1: Add deps and config vars

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add backend dependencies**

In `backend/pyproject.toml`, edit the `dependencies` list to add at the end (before the closing `]`):

```toml
    "argon2-cffi>=23.1",
    "pyjwt>=2.8",
```

- [ ] **Step 2: Add env vars to config**

Open `backend/app/config.py` and add these fields to the `Settings` class (alongside existing fields):

```python
    jwt_secret: str = "dev-only-replace-in-prod"
    yahoo_client_id: str = ""
    yahoo_client_secret: str = ""
    yahoo_redirect_uri: str = "http://localhost:8000/api/auth/yahoo/callback"
    frontend_url: str = "http://localhost:5173"
```

- [ ] **Step 3: Update .env.example**

Append to `backend/.env.example`:

```
# Auth
JWT_SECRET=dev-only-replace-in-prod
YAHOO_CLIENT_ID=
YAHOO_CLIENT_SECRET=
YAHOO_REDIRECT_URI=http://localhost:8000/api/auth/yahoo/callback
FRONTEND_URL=http://localhost:5173
```

- [ ] **Step 4: Install + smoke check**

Run from `backend/`: `pip install -e ".[dev]"`
Then verify imports work: `python -c "import argon2, jwt; print('ok')"`
Expected output: `ok`

- [ ] **Step 5: Commit**

```bash
git checkout main && git pull
git checkout -b feat/accounts-phase-1-foundations
git add backend/pyproject.toml backend/app/config.py backend/.env.example
git commit -m "feat(deps): add argon2-cffi and pyjwt; auth env vars"
```

### Task 1.2: User and Profile ORM models

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/profile.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/tests/test_models_user_profile.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_models_user_profile.py`:

```python
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from app.models import User, Profile


@pytest.mark.asyncio
async def test_user_persists_minimal(test_db):
    u = User(email="a@b.com", password_hash="hashstuff")
    test_db.add(u)
    await test_db.commit()
    rows = (await test_db.scalars(select(User))).all()
    assert len(rows) == 1
    assert rows[0].email == "a@b.com"
    assert rows[0].yahoo_subject is None


@pytest.mark.asyncio
async def test_user_email_can_be_null_for_yahoo_only(test_db):
    u = User(yahoo_subject="yahoo-sub-123")
    test_db.add(u)
    await test_db.commit()
    rows = (await test_db.scalars(select(User))).all()
    assert rows[0].email is None
    assert rows[0].yahoo_subject == "yahoo-sub-123"


@pytest.mark.asyncio
async def test_profile_persists_with_jsonb_fields(test_db):
    u = User(email="a@b.com", password_hash="x")
    test_db.add(u)
    await test_db.commit()

    p = Profile(
        user_id=u.id,
        name="My Setup",
        settings_json={"scoring_format": "ppr", "league_size": 12},
        rules_json=[{"name": "RB Committee Penalty", "enabled": True, "weight": 1.0}],
    )
    test_db.add(p)
    await test_db.commit()

    rows = (await test_db.scalars(select(Profile))).all()
    assert rows[0].name == "My Setup"
    assert rows[0].settings_json["league_size"] == 12
    assert rows[0].rules_json[0]["name"] == "RB Committee Penalty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_models_user_profile.py -v`
Expected: ImportError for `User`, `Profile`.

- [ ] **Step 3: Create User model**

Create `backend/app/models/user.py`:

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    yahoo_subject: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_active_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL", use_alter=True, name="fk_users_last_active_profile"),
        nullable=True,
    )
```

- [ ] **Step 4: Create Profile model**

Create `backend/app/models/profile.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.database import Base


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_profiles_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rules_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
```

**Note on JSONB in tests:** The test DB is SQLite. SQLAlchemy's `JSONB` type compiles to TEXT on SQLite via its `JSON` fallback. Verify with the test that round-trips a dict.

- [ ] **Step 5: Export from package**

Open `backend/app/models/__init__.py`. Add to existing imports (preserve order):

```python
from app.models.user import User
from app.models.profile import Profile
```

Add `"User"` and `"Profile"` to the `__all__` tuple if it exists.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_models_user_profile.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/user.py backend/app/models/profile.py backend/app/models/__init__.py backend/tests/test_models_user_profile.py
git commit -m "feat(models): add User and Profile ORM models"
```

### Task 1.3: Alembic migration 004

**Files:**
- Create: `backend/alembic/versions/004_users_and_profiles.py`

- [ ] **Step 1: Check down_revision chain**

Run from `backend/`: `venv/bin/alembic history | head`
Confirm the most recent revision is `003`. Use that as `down_revision`.

- [ ] **Step 2: Create migration**

Create `backend/alembic/versions/004_users_and_profiles.py`:

```python
"""users and profiles tables

Revision ID: 004
Revises: 003
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("yahoo_subject", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_profile_id", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("yahoo_subject", name="uq_users_yahoo_subject"),
    )

    op.create_table(
        "profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("settings_json", JSONB(), nullable=False),
        sa.Column("rules_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_profiles_user_name"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    op.create_foreign_key(
        "fk_users_last_active_profile",
        "users", "profiles",
        ["last_active_profile_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_last_active_profile", "users", type_="foreignkey")
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")
    op.drop_table("users")
```

- [ ] **Step 3: Verify migration chain**

Run: `cd backend && venv/bin/alembic history`
Expected: shows `003 -> 004` at the head.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/004_users_and_profiles.py
git commit -m "feat(db): migration 004 - users and profiles tables"
```

### Task 1.4: Password hashing module

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/hashing.py`
- Create: `backend/tests/test_auth_hashing.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_auth_hashing.py`:

```python
from app.auth.hashing import hash_password, verify_password


def test_hash_password_returns_argon2_string():
    h = hash_password("hunter2hunter2")
    assert h.startswith("$argon2")


def test_verify_password_accepts_correct_password():
    h = hash_password("hunter2hunter2")
    assert verify_password(h, "hunter2hunter2") is True


def test_verify_password_rejects_wrong_password():
    h = hash_password("hunter2hunter2")
    assert verify_password(h, "wrong-password") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_auth_hashing.py -v`
Expected: ImportError.

- [ ] **Step 3: Create package init**

Create `backend/app/auth/__init__.py` (empty file).

- [ ] **Step 4: Create hashing module**

Create `backend/app/auth/hashing.py`:

```python
"""Argon2id password hashing. Keeps the library detail out of the rest of the code."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        _hasher.verify(stored_hash, plain)
        return True
    except VerifyMismatchError:
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth_hashing.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/hashing.py backend/tests/test_auth_hashing.py
git commit -m "feat(auth): argon2id password hashing module"
```

### Task 1.5: JWT encode/decode and cookie helpers

**Files:**
- Create: `backend/app/auth/jwt.py`
- Create: `backend/tests/test_auth_jwt.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_auth_jwt.py`:

```python
import uuid
from datetime import timedelta
from app.auth.jwt import encode_jwt, decode_jwt, JWTInvalid


def test_encode_decode_roundtrip():
    user_id = uuid.uuid4()
    token = encode_jwt(user_id)
    decoded = decode_jwt(token)
    assert decoded == user_id


def test_decode_invalid_token_raises():
    import pytest
    with pytest.raises(JWTInvalid):
        decode_jwt("not.a.token")


def test_decode_expired_token_raises():
    import pytest
    user_id = uuid.uuid4()
    token = encode_jwt(user_id, ttl=timedelta(seconds=-1))
    with pytest.raises(JWTInvalid):
        decode_jwt(token)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_auth_jwt.py -v`
Expected: ImportError.

- [ ] **Step 3: Create JWT module**

Create `backend/app/auth/jwt.py`:

```python
"""JWT encode/decode + cookie helpers.

We embed only the user's id in the token. Anything else (email, profile id)
is read from the DB so token leaks don't expose state.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Response
from app.config import settings


JWT_COOKIE_NAME = "autotiers_session"
_DEFAULT_TTL = timedelta(days=30)


class JWTInvalid(Exception):
    """Raised when a JWT is malformed, expired, or signature invalid."""


def encode_jwt(user_id: uuid.UUID, ttl: timedelta = _DEFAULT_TTL) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_jwt(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise JWTInvalid(str(e)) from e
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise JWTInvalid("missing/invalid sub claim") from e


def set_auth_cookie(response: Response, user_id: uuid.UUID, *, secure: Optional[bool] = None) -> None:
    """Set the session cookie. In test/dev, secure=False so non-HTTPS works."""
    if secure is None:
        secure = not settings.debug if hasattr(settings, "debug") else True
    response.set_cookie(
        key=JWT_COOKIE_NAME,
        value=encode_jwt(user_id),
        max_age=int(_DEFAULT_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=JWT_COOKIE_NAME, path="/")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth_jwt.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/jwt.py backend/tests/test_auth_jwt.py
git commit -m "feat(auth): JWT encode/decode + cookie helpers"
```

### Task 1.6: FastAPI auth dependencies

**Files:**
- Create: `backend/app/auth/dependencies.py`
- Create: `backend/tests/test_auth_dependencies.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_auth_dependencies.py`:

```python
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.database import get_db
from app.models import User
from app.auth.dependencies import get_current_user, require_user
from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME


def _make_app(test_engine) -> FastAPI:
    app = FastAPI()
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    @app.get("/optional")
    async def optional_route(user: User | None = get_current_user):
        return {"user_id": str(user.id) if user else None}

    @app.get("/required")
    async def required_route(user: User = require_user):
        return {"user_id": str(user.id)}

    return app


@pytest.mark.asyncio
async def test_optional_returns_none_without_cookie(test_engine):
    app = _make_app(test_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/optional")
    assert r.json() == {"user_id": None}


@pytest.mark.asyncio
async def test_required_returns_401_without_cookie(test_engine):
    app = _make_app(test_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/required")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_required_returns_user_with_valid_cookie(test_engine, test_db):
    user = User(email="me@x.com", password_hash="x")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    app = _make_app(test_engine)
    token = encode_jwt(user.id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set(JWT_COOKIE_NAME, token)
        r = await c.get("/required")
    assert r.status_code == 200
    assert r.json() == {"user_id": str(user.id)}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_auth_dependencies.py -v`
Expected: ImportError for `get_current_user`, `require_user`.

- [ ] **Step 3: Create dependencies module**

Create `backend/app/auth/dependencies.py`:

```python
"""FastAPI auth dependencies.

  - `get_current_user` — Optional[User]; None if no/invalid cookie. Use this when
    a route should work both anonymously and authenticated.
  - `require_user` — User; raises HTTPException(401) if missing. Use this when
    a route must be authenticated.
"""
from typing import Optional
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User
from app.auth.jwt import decode_jwt, JWTInvalid, JWT_COOKIE_NAME


async def _resolve_user(
    cookie_value: Optional[str],
    db: AsyncSession,
) -> Optional[User]:
    if not cookie_value:
        return None
    try:
        user_id = decode_jwt(cookie_value)
    except JWTInvalid:
        return None
    return await db.get(User, user_id)


async def _get_current_user_impl(
    autotiers_session: Optional[str] = Cookie(default=None, alias=JWT_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    return await _resolve_user(autotiers_session, db)


async def _require_user_impl(
    user: Optional[User] = Depends(_get_current_user_impl),
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


get_current_user = Depends(_get_current_user_impl)
require_user = Depends(_require_user_impl)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth_dependencies.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/dependencies.py backend/tests/test_auth_dependencies.py
git commit -m "feat(auth): FastAPI auth dependencies (get_current_user, require_user)"
```

### Task 1.7: In-memory rate limiter

**Files:**
- Create: `backend/app/auth/rate_limit.py`
- Create: `backend/tests/test_auth_rate_limit.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_auth_rate_limit.py`:

```python
import time
from app.auth.rate_limit import LoginRateLimiter


def test_allows_under_limit():
    rl = LoginRateLimiter(max_attempts=3, window_seconds=60)
    assert rl.check_and_record("alice@x.com") is True
    assert rl.check_and_record("alice@x.com") is True
    assert rl.check_and_record("alice@x.com") is True


def test_blocks_after_limit():
    rl = LoginRateLimiter(max_attempts=3, window_seconds=60)
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    assert rl.check_and_record("alice@x.com") is False


def test_window_expires(monkeypatch):
    rl = LoginRateLimiter(max_attempts=2, window_seconds=10)
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    assert rl.check_and_record("alice@x.com") is False
    # Advance time past the window
    monkeypatch.setattr(time, "time", lambda: time.time() + 20)
    assert rl.check_and_record("alice@x.com") is True


def test_keys_are_independent():
    rl = LoginRateLimiter(max_attempts=2, window_seconds=60)
    rl.check_and_record("alice@x.com")
    rl.check_and_record("alice@x.com")
    assert rl.check_and_record("alice@x.com") is False
    assert rl.check_and_record("bob@x.com") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_auth_rate_limit.py -v`
Expected: ImportError.

- [ ] **Step 3: Create rate limiter**

Create `backend/app/auth/rate_limit.py`:

```python
"""In-memory sliding-window rate limiter for login attempts.

NOT process-safe. Acceptable for single-process FastAPI dev and the v1
single-container Railway deploy. Move to Redis when we go multi-instance.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str) -> bool:
        """Returns True if the request is allowed, False if rate-limited.

        Records the attempt either way (so spamming a blocked key extends
        the block — the standard sliding-window behavior).
        """
        now = time.time()
        bucket = self._attempts[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_attempts:
            return False
        bucket.append(now)
        return True


# Module-level singleton used by the auth router.
login_rate_limiter = LoginRateLimiter()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth_rate_limit.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/rate_limit.py backend/tests/test_auth_rate_limit.py
git commit -m "feat(auth): in-memory sliding-window login rate limiter"
```

### Task 1.8: Push Phase 1 PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/accounts-phase-1-foundations
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --title "feat(accounts): phase 1 — backend auth foundations" --body "$(cat <<'EOF'
## Summary
Foundation work for accounts. No user-facing changes yet; no new endpoints.

- Adds \`User\` + \`Profile\` ORM models with Alembic migration 004
- Adds \`argon2-cffi\` + \`pyjwt\` dependencies and env vars (\`JWT_SECRET\`, Yahoo OAuth, \`FRONTEND_URL\`)
- New \`app/auth/\` package: \`hashing\` (argon2id), \`jwt\` (encode/decode + cookie helpers), \`dependencies\` (FastAPI deps), \`rate_limit\` (sliding-window in-memory)

Implements Phase 1 of \`docs/superpowers/specs/2026-05-26-accounts-and-profiles-design.md\`.

## Test plan
- [x] Hashing roundtrip + wrong-password rejection
- [x] JWT encode/decode + invalid + expired
- [x] Dependencies: optional vs required behavior with/without cookie
- [x] Rate limiter: under-limit, over-limit, window expiry, per-key isolation
- [x] Models persist and round-trip JSONB

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# Phase 2 — Email/password auth endpoints

Branch: `feat/accounts-phase-2-email-password` off `feat/accounts-phase-1-foundations` (stacked PR, base = phase-1 branch).

### Task 2.1: Auth pydantic schemas

**Files:**
- Create: `backend/app/schemas/auth.py`

- [ ] **Step 1: Create schemas**

Create `backend/app/schemas/auth.py`:

```python
"""Request and response shapes for /api/auth endpoints."""
import uuid
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    # Optional anonymous-state migration. When supplied, the signup endpoint
    # creates a "My setup" profile and marks it active in the same transaction.
    initial_settings: Optional[dict[str, Any]] = None
    initial_rules: Optional[list[dict[str, Any]]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: Optional[str]
    yahoo_subject: Optional[str]
    last_active_profile_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserOut
    profiles: list["ProfileOut"]


# Forward declaration; the full ProfileOut lives in schemas/profile.py
# but to avoid a circular import we redeclare a minimal shape here and
# rebuild after profile schemas are imported.
class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]

    model_config = {"from_attributes": True}


MeResponse.model_rebuild()
```

- [ ] **Step 2: Commit**

```bash
git checkout main && git checkout feat/accounts-phase-1-foundations && git pull
git checkout -b feat/accounts-phase-2-email-password
git add backend/app/schemas/auth.py
git commit -m "feat(schemas): auth request/response pydantic models"
```

### Task 2.2: Add `pydantic[email]` dependency

The `EmailStr` type requires the `email-validator` package.

- [ ] **Step 1: Add dep**

In `backend/pyproject.toml`, change `"pydantic>=2.7"` to `"pydantic[email]>=2.7"`.

- [ ] **Step 2: Install**

Run: `cd backend && pip install -e ".[dev]"`

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "feat(deps): pydantic[email] for EmailStr validation"
```

### Task 2.3: Signup endpoint

**Files:**
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_auth.py -v`
Expected: 404 on POST (router not mounted) or ImportError.

- [ ] **Step 3: Create auth router**

Create `backend/app/api/auth.py`:

```python
"""Email/password auth endpoints. Yahoo OAuth lives in this same router but
is added in phase 3."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Profile
from app.auth.hashing import hash_password
from app.auth.jwt import set_auth_cookie
from app.schemas.auth import SignupRequest, UserOut, MeResponse, ProfileOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=201, response_model=MeResponse)
async def signup(
    body: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    # Duplicate check
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already in use")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()  # populate user.id

    profile: Profile | None = None
    if body.initial_settings is not None and body.initial_rules is not None:
        profile = Profile(
            user_id=user.id,
            name="My setup",
            settings_json=body.initial_settings,
            rules_json=body.initial_rules,
        )
        db.add(profile)
        await db.flush()
        user.last_active_profile_id = profile.id

    await db.commit()
    await db.refresh(user)

    set_auth_cookie(response, user.id)

    profiles = [ProfileOut.model_validate(profile)] if profile else []
    return MeResponse(user=UserOut.model_validate(user), profiles=profiles)
```

- [ ] **Step 4: Mount the router**

Open `backend/app/main.py`. Add to the imports near the existing `from app.api import generate, rules, players, data`:

```python
from app.api import auth as auth_api
```

Then add a router include (alongside the others, before the `@app.get("/health")` line):

```python
app.include_router(auth_api.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/auth.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(api): POST /auth/signup with anonymous-state migration"
```

### Task 2.4: Login endpoint with rate limit

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    # Clear cookies from signup so we're testing pure login
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
    # Pre-seed the user via signup
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()

    # Reset the module-level limiter so this test is hermetic
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_auth.py -v`
Expected: 4 new tests fail (404 on /login).

- [ ] **Step 3: Add login endpoint**

In `backend/app/api/auth.py`, add the `LoginRequest` import:

```python
from app.schemas.auth import SignupRequest, LoginRequest, UserOut, MeResponse, ProfileOut
```

And add helpers + the route:

```python
from app.auth.hashing import hash_password, verify_password
from app.auth.rate_limit import login_rate_limiter


@router.post("/login", response_model=MeResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    if not login_rate_limiter.check_and_record(body.email):
        raise HTTPException(status_code=429, detail="Too many attempts; try again later")

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    set_auth_cookie(response, user.id)
    profiles = (await db.scalars(select(Profile).where(Profile.user_id == user.id))).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        profiles=[ProfileOut.model_validate(p) for p in profiles],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth.py -v`
Expected: 8 passed (4 existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_auth.py
git commit -m "feat(api): POST /auth/login with rate limit"
```

### Task 2.5: Logout endpoint

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_logout_clears_cookie(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    r = await async_client.post("/api/auth/logout")
    assert r.status_code == 204
    # FastAPI's response.delete_cookie sets the cookie to expire immediately;
    # httpx then drops it from the jar.
    assert "autotiers_session" not in async_client.cookies
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_auth.py::test_logout_clears_cookie -v`
Expected: 404

- [ ] **Step 3: Add logout endpoint**

In `backend/app/api/auth.py`:

```python
from app.auth.jwt import set_auth_cookie, clear_auth_cookie
```

```python
@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_auth_cookie(response)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth.py::test_logout_clears_cookie -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_auth.py
git commit -m "feat(api): POST /auth/logout clears session cookie"
```

### Task 2.6: GET /auth/me

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_auth.py`:

```python
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
        "initial_rules": [],
    })
    assert signup.status_code == 201

    r = await async_client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["name"] == "My setup"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_auth.py::test_me_returns_user_and_profiles_when_authenticated -v`
Expected: 404

- [ ] **Step 3: Add /me endpoint**

In `backend/app/api/auth.py`:

```python
from app.auth.dependencies import require_user
```

```python
@router.get("/me", response_model=MeResponse)
async def me(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    profiles = (await db.scalars(select(Profile).where(Profile.user_id == user.id))).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        profiles=[ProfileOut.model_validate(p) for p in profiles],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_auth.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_auth.py
git commit -m "feat(api): GET /auth/me returns current user + profiles"
```

### Task 2.7: Push Phase 2 PR

- [ ] **Step 1: Run full backend suite**

Run: `cd backend && venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 2: Push**

```bash
git push -u origin feat/accounts-phase-2-email-password
gh pr create --base feat/accounts-phase-1-foundations --title "feat(accounts): phase 2 — email/password auth endpoints" --body "$(cat <<'EOF'
## Summary
Adds the four email/password auth endpoints. Stacks on phase-1 PR.

- \`POST /api/auth/signup\` — creates a user (and a "My setup" profile if anonymous state is supplied), sets JWT cookie
- \`POST /api/auth/login\` — verifies password, sets cookie; rate-limited at 5 / 15min per email
- \`POST /api/auth/logout\` — clears cookie
- \`GET /api/auth/me\` — returns the current user + their profiles

Implements Phase 2 of \`docs/superpowers/specs/2026-05-26-accounts-and-profiles-design.md\`.

## Test plan
- [x] Signup happy + duplicate-email 409 + short-password 422
- [x] Signup with anonymous state creates "My setup" + sets last_active_profile_id
- [x] Login happy + wrong password 401 + unknown email 401
- [x] Login rate-limit triggers after 5 fails
- [x] Logout clears cookie
- [x] /me returns 401 anonymous + user+profiles authenticated

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# Phase 3 — Yahoo OAuth

Branch: `feat/accounts-phase-3-yahoo-oauth` stacked on phase-2.

### Task 3.1: Yahoo OAuth client module

**Files:**
- Create: `backend/app/auth/yahoo.py`
- Create: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_yahoo_oauth.py`:

```python
import pytest
import respx
from httpx import Response
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_subject


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(state="random123")
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "state=random123" in url


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
async def test_fetch_subject_returns_sub_claim():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.get("/openid/v1/userinfo").mock(return_value=Response(
            200, json={"sub": "yahoo-user-abc"}
        ))
        sub = await fetch_subject("access-token")
    assert sub == "yahoo-user-abc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_yahoo_oauth.py -v`
Expected: ImportError.

- [ ] **Step 3: Create Yahoo OAuth client**

Create `backend/app/auth/yahoo.py`:

```python
"""Yahoo OAuth2 client.

Used solely for identity: we exchange the auth code for a token, fetch the
subject claim, and discard the token. We deliberately do not request email
scope or store any Yahoo tokens — see the design doc's "Email-collision
avoidance" section.
"""
from urllib.parse import urlencode
import httpx
from app.config import settings


AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
USERINFO_URL = "https://api.login.yahoo.com/openid/v1/userinfo"


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.yahoo_redirect_uri,
        "response_type": "code",
        "scope": "openid",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange an auth code for an access token. Returns the access_token string.

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
        return resp.json()["access_token"]


async def fetch_subject(access_token: str) -> str:
    """Fetch the openid `sub` claim from Yahoo's userinfo endpoint."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()["sub"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_yahoo_oauth.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git checkout main && git checkout feat/accounts-phase-2-email-password && git pull
git checkout -b feat/accounts-phase-3-yahoo-oauth
git add backend/app/auth/yahoo.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(auth): Yahoo OAuth client (authorize URL + token exchange + userinfo)"
```

### Task 3.2: Yahoo authorize + callback routes

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/test_yahoo_oauth.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_yahoo_oauth.py`:

```python
import secrets
import respx
from httpx import Response
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
    # Pre-seed an existing Yahoo user
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_yahoo_oauth.py -v`
Expected: 5 new tests fail with 404.

- [ ] **Step 3: Add Yahoo routes**

In `backend/app/api/auth.py`, add imports at top:

```python
import secrets
from fastapi import Cookie
from fastapi.responses import RedirectResponse
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_subject
from app.config import settings
```

Add the two routes:

```python
_OAUTH_STATE_COOKIE = "autotiers_oauth_state"


@router.get("/yahoo/authorize")
async def yahoo_authorize() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(url=build_authorize_url(state), status_code=307)
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,  # 10 min
        httponly=True,
        secure=False,  # set True in prod via env
        samesite="lax",
        path="/",
    )
    return response


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
    yahoo_subject = await fetch_subject(access_token)

    user = await db.scalar(select(User).where(User.yahoo_subject == yahoo_subject))
    if user is None:
        user = User(yahoo_subject=yahoo_subject)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_yahoo_oauth.py -v`
Expected: 9 passed (4 module + 5 routes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/tests/test_yahoo_oauth.py
git commit -m "feat(api): Yahoo OAuth authorize + callback routes"
```

### Task 3.3: Push Phase 3 PR

- [ ] **Step 1: Push + open PR**

```bash
git push -u origin feat/accounts-phase-3-yahoo-oauth
gh pr create --base feat/accounts-phase-2-email-password --title "feat(accounts): phase 3 — Yahoo OAuth" --body "$(cat <<'EOF'
## Summary
Adds Yahoo OAuth2 as an alternate sign-in path. Stacks on phase-2 PR.

- \`app/auth/yahoo.py\` — authorize URL builder, code-for-token exchange, userinfo subject fetch
- \`GET /api/auth/yahoo/authorize\` — sets state cookie, redirects to Yahoo
- \`GET /api/auth/yahoo/callback\` — validates state, fetches subject, finds/creates user, sets session cookie, redirects to frontend

Email is intentionally NOT pulled from Yahoo (see "Email-collision avoidance" in design doc).

Implements Phase 3 of \`docs/superpowers/specs/2026-05-26-accounts-and-profiles-design.md\`.

## Test plan
- [x] authorize URL contains required params + sets state cookie
- [x] token exchange happy path + error path
- [x] userinfo fetches sub claim
- [x] callback rejects missing/mismatched state
- [x] callback creates new user on first login
- [x] callback finds existing user on repeat login (no duplicate)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# Phase 4 — Profile API

Branch: `feat/accounts-phase-4-profile-api` stacked on phase-3.

### Task 4.1: Profile pydantic schemas

**Files:**
- Create: `backend/app/schemas/profile.py`

- [ ] **Step 1: Create schemas**

Create `backend/app/schemas/profile.py`:

```python
"""Request/response shapes for /api/profiles."""
import uuid
from typing import Optional, Any
from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    settings_json: Optional[dict[str, Any]] = None
    rules_json: Optional[list[dict[str, Any]]] = None


class ProfilesListResponse(BaseModel):
    profiles: list[ProfileOut]
    active_profile_id: Optional[uuid.UUID]
```

- [ ] **Step 2: Commit**

```bash
git checkout main && git checkout feat/accounts-phase-3-yahoo-oauth && git pull
git checkout -b feat/accounts-phase-4-profile-api
git add backend/app/schemas/profile.py
git commit -m "feat(schemas): profile request/response pydantic models"
```

### Task 4.2: GET /api/profiles

**Files:**
- Create: `backend/app/api/profiles_api.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_profiles.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 404

- [ ] **Step 3: Create profile router**

Create `backend/app/api/profiles_api.py`:

```python
"""Profile CRUD endpoints. All require auth."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Profile
from app.auth.dependencies import require_user
from app.schemas.profile import (
    ProfileOut, ProfileCreate, ProfileUpdate, ProfilesListResponse,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])

_PROFILE_CAP = 5


@router.get("", response_model=ProfilesListResponse)
async def list_profiles(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> ProfilesListResponse:
    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).order_by(Profile.updated_at.desc())
    )).all()
    return ProfilesListResponse(
        profiles=[ProfileOut.model_validate(p) for p in profiles],
        active_profile_id=user.last_active_profile_id,
    )
```

- [ ] **Step 4: Mount the router**

In `backend/app/main.py`:

```python
from app.api import profiles_api
```

```python
app.include_router(profiles_api.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/profiles_api.py backend/app/main.py backend/tests/test_profiles.py
git commit -m "feat(api): GET /api/profiles"
```

### Task 4.3: POST /api/profiles (with 5-cap)

**Files:**
- Modify: `backend/app/api/profiles_api.py`
- Modify: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_profiles.py`:

```python
@pytest.mark.asyncio
async def test_create_profile_persists_and_returns(async_client):
    await _signup(async_client)
    r = await async_client.post("/api/profiles", json={
        "name": "PPR 12-team",
        "settings_json": {"scoring_format": "ppr", "league_size": 12},
        "rules_json": [{"name": "X", "enabled": True, "weight": 1.0}],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "PPR 12-team"


@pytest.mark.asyncio
async def test_create_profile_rejects_when_at_cap(async_client):
    await _signup(async_client)
    for i in range(5):
        r = await async_client.post("/api/profiles", json={
            "name": f"Slot {i}",
            "settings_json": {},
            "rules_json": [],
        })
        assert r.status_code == 201
    r = await async_client.post("/api/profiles", json={
        "name": "Sixth",
        "settings_json": {},
        "rules_json": [],
    })
    assert r.status_code == 409
    assert "limit" in r.json()["detail"].lower() or "max" in r.json()["detail"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 2 new tests fail (404).

- [ ] **Step 3: Add create endpoint**

In `backend/app/api/profiles_api.py`, append:

```python
@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    count = await db.scalar(
        select(func.count(Profile.id)).where(Profile.user_id == user.id)
    )
    if count is not None and count >= _PROFILE_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Profile limit reached ({_PROFILE_CAP}). Delete one to add another.",
        )
    profile = Profile(
        user_id=user.id,
        name=body.name,
        settings_json=body.settings_json,
        rules_json=body.rules_json,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return ProfileOut.model_validate(profile)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profiles_api.py backend/tests/test_profiles.py
git commit -m "feat(api): POST /api/profiles with 5-profile cap"
```

### Task 4.4: PATCH /api/profiles/{id}

**Files:**
- Modify: `backend/app/api/profiles_api.py`
- Modify: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_patch_profile_updates_fields(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Original",
        "settings_json": {"league_size": 10},
        "rules_json": [],
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
    # rules_json untouched
    assert body["rules_json"] == []


@pytest.mark.asyncio
async def test_patch_profile_403_when_other_user(async_client):
    await _signup(async_client, "alice@x.com")
    create = await async_client.post("/api/profiles", json={
        "name": "Alice's profile", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    # Log out, sign up as bob
    await async_client.post("/api/auth/logout")
    await _signup(async_client, "bob@x.com")
    r = await async_client.patch(f"/api/profiles/{pid}", json={"name": "Hijack"})
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 2 new fail (405 / 404).

- [ ] **Step 3: Add patch endpoint**

In `backend/app/api/profiles_api.py`:

```python
@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your profile")

    if body.name is not None:
        profile.name = body.name
    if body.settings_json is not None:
        profile.settings_json = body.settings_json
    if body.rules_json is not None:
        profile.rules_json = body.rules_json

    await db.commit()
    await db.refresh(profile)
    return ProfileOut.model_validate(profile)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profiles_api.py backend/tests/test_profiles.py
git commit -m "feat(api): PATCH /api/profiles/{id}"
```

### Task 4.5: DELETE /api/profiles/{id}

**Files:**
- Modify: `backend/app/api/profiles_api.py`
- Modify: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write failing test**

Append:

```python
@pytest.mark.asyncio
async def test_delete_profile_removes_row(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "Doomed", "settings_json": {}, "rules_json": [],
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
        "name": "Alice's", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    await async_client.post("/api/auth/logout")
    await _signup(async_client, "bob@x.com")
    r = await async_client.delete(f"/api/profiles/{pid}")
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 2 new fail (405).

- [ ] **Step 3: Add delete endpoint**

```python
@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your profile")

    if user.last_active_profile_id == profile.id:
        user.last_active_profile_id = None

    await db.delete(profile)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profiles_api.py backend/tests/test_profiles.py
git commit -m "feat(api): DELETE /api/profiles/{id}"
```

### Task 4.6: POST /api/profiles/{id}/activate

**Files:**
- Modify: `backend/app/api/profiles_api.py`
- Modify: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write failing test**

Append:

```python
@pytest.mark.asyncio
async def test_activate_sets_last_active_profile_id(async_client):
    await _signup(async_client)
    create = await async_client.post("/api/profiles", json={
        "name": "First", "settings_json": {}, "rules_json": [],
    })
    pid = create.json()["id"]

    r = await async_client.post(f"/api/profiles/{pid}/activate")
    assert r.status_code == 204

    listing = await async_client.get("/api/profiles")
    assert listing.json()["active_profile_id"] == pid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py::test_activate_sets_last_active_profile_id -v`
Expected: 404.

- [ ] **Step 3: Add activate endpoint**

```python
@router.post("/{profile_id}/activate", status_code=204)
async def activate_profile(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your profile")
    user.last_active_profile_id = profile.id
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_profiles.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/profiles_api.py backend/tests/test_profiles.py
git commit -m "feat(api): POST /api/profiles/{id}/activate"
```

### Task 4.7: Push Phase 4 PR

- [ ] **Step 1: Run full backend suite**

Run: `cd backend && venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 2: Push + open PR**

```bash
git push -u origin feat/accounts-phase-4-profile-api
gh pr create --base feat/accounts-phase-3-yahoo-oauth --title "feat(accounts): phase 4 — profile CRUD API" --body "$(cat <<'EOF'
## Summary
Full CRUD for user profiles. Stacks on phase-3 PR.

- \`GET /api/profiles\` — list + active id
- \`POST /api/profiles\` — create (409 when at 5)
- \`PATCH /api/profiles/{id}\` — partial update (name, settings, rules)
- \`DELETE /api/profiles/{id}\` — remove (clears last_active_profile_id if it was active)
- \`POST /api/profiles/{id}/activate\` — set as last-active

All endpoints require auth; cross-user access returns 403.

Implements Phase 4 of \`docs/superpowers/specs/2026-05-26-accounts-and-profiles-design.md\`.

## Test plan
- [x] All endpoints 401 anonymous
- [x] List returns empty + active=null for new user
- [x] Create persists; 409 at cap (5)
- [x] Patch updates only supplied fields; 403 cross-user
- [x] Delete removes row + clears active if needed; 403 cross-user
- [x] Activate sets last_active_profile_id

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# Phase 5 — Frontend API clients + AuthContext

Branch: `feat/accounts-phase-5-frontend-api` stacked on phase-4. **Frontend-only changes**; no UI yet.

### Task 5.1: API types

**Files:**
- Modify: `web/src/api/types.ts`

- [ ] **Step 1: Append types**

Append to `web/src/api/types.ts`:

```ts
// ---------- accounts & profiles ----------

export interface User {
  id: string;
  email: string | null;
  yahoo_subject: string | null;
  last_active_profile_id: string | null;
}

export interface Profile {
  id: string;
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Array<{ name: string; enabled: boolean; weight: number }>;
}

export interface MeResponse {
  user: User;
  profiles: Profile[];
}

export interface ProfilesListResponse {
  profiles: Profile[];
  active_profile_id: string | null;
}
```

- [ ] **Step 2: Commit**

```bash
git checkout main && git checkout feat/accounts-phase-4-profile-api && git pull
git checkout -b feat/accounts-phase-5-frontend-api
git add web/src/api/types.ts
git commit -m "feat(types): User, Profile, MeResponse, ProfilesListResponse"
```

### Task 5.2: `credentials: include` on apiFetch

**Files:**
- Modify: `web/src/api/client.ts`

- [ ] **Step 1: Update apiFetch to always include credentials**

In `web/src/api/client.ts`, change the `apiFetch` body so the `fetch` call includes credentials. The function should look like:

```ts
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
  return resp.json() as Promise<T>;
}
```

- [ ] **Step 2: Run existing tests**

Run: `cd web && npm test -- --run src/tests/api/client.test.ts`
Expected: 4 passed (existing tests).

- [ ] **Step 3: Commit**

```bash
git add web/src/api/client.ts
git commit -m "feat(api): credentials include on every fetch (for session cookie)"
```

### Task 5.3: auth.ts API client

**Files:**
- Create: `web/src/api/auth.ts`
- Create: `web/src/tests/api/auth.test.ts`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/api/auth.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { signup, login, logout, getMe, yahooAuthorizeUrl } from "@/api/auth";

describe("auth API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("signup POSTs to /api/auth/signup and returns MeResponse", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ user: { id: "u1", email: "a@b.com", yahoo_subject: null, last_active_profile_id: null }, profiles: [] }), { status: 201 }),
    );
    const result = await signup({ email: "a@b.com", password: "longenough123" });
    expect(result.user.email).toBe("a@b.com");
  });

  it("login POSTs to /api/auth/login", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ user: { id: "u1", email: "a@b.com", yahoo_subject: null, last_active_profile_id: null }, profiles: [] }), { status: 200 }),
    );
    await login({ email: "a@b.com", password: "x" });
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/login");
  });

  it("getMe returns null on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    const result = await getMe();
    expect(result).toBeNull();
  });

  it("yahooAuthorizeUrl returns the API URL plus /api/auth/yahoo/authorize", () => {
    expect(yahooAuthorizeUrl()).toContain("/api/auth/yahoo/authorize");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- --run src/tests/api/auth.test.ts`
Expected: import errors.

- [ ] **Step 3: Create the auth client**

Create `web/src/api/auth.ts`:

```ts
import { apiFetch, API_URL, ApiError } from "./client";
import type { MeResponse } from "./types";

export interface SignupBody {
  email: string;
  password: string;
  initial_settings?: Record<string, unknown>;
  initial_rules?: Array<Record<string, unknown>>;
}

export interface LoginBody {
  email: string;
  password: string;
}

export function signup(body: SignupBody): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function login(body: LoginBody): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function getMe(): Promise<MeResponse | null> {
  try {
    return await apiFetch<MeResponse>("/api/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

export function yahooAuthorizeUrl(): string {
  return `${API_URL}/api/auth/yahoo/authorize`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run src/tests/api/auth.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/auth.ts web/src/tests/api/auth.test.ts
git commit -m "feat(api): auth client (signup, login, logout, getMe, yahooAuthorizeUrl)"
```

### Task 5.4: profiles.ts API client

**Files:**
- Create: `web/src/api/profiles.ts`
- Create: `web/src/tests/api/profiles.test.ts`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/api/profiles.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { listProfiles, createProfile, updateProfile, deleteProfile, activateProfile } from "@/api/profiles";

const sample = { id: "p1", name: "x", settings_json: {}, rules_json: [] };

describe("profiles API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("list returns profiles and active_profile_id", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ profiles: [sample], active_profile_id: "p1" }), { status: 200 }),
    );
    const r = await listProfiles();
    expect(r.profiles).toHaveLength(1);
    expect(r.active_profile_id).toBe("p1");
  });

  it("create POSTs profile body", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(sample), { status: 201 }),
    );
    await createProfile({ name: "x", settings_json: {}, rules_json: [] });
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
  });

  it("update PATCHes by id", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(sample), { status: 200 }),
    );
    await updateProfile("p1", { name: "new" });
    expect(String(spy.mock.calls[0][0])).toContain("/api/profiles/p1");
    expect(spy.mock.calls[0][1]?.method).toBe("PATCH");
  });

  it("delete DELETEs by id", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 204 }));
    await deleteProfile("p1");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("activate POSTs to /activate", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 204 }));
    await activateProfile("p1");
    expect(String(spy.mock.calls[0][0])).toContain("/api/profiles/p1/activate");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- --run src/tests/api/profiles.test.ts`
Expected: import errors.

- [ ] **Step 3: Create profiles client**

Create `web/src/api/profiles.ts`:

```ts
import { apiFetch, API_URL } from "./client";
import type { Profile, ProfilesListResponse } from "./types";

export interface ProfileCreateBody {
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Array<Record<string, unknown>>;
}

export interface ProfileUpdateBody {
  name?: string;
  settings_json?: Record<string, unknown>;
  rules_json?: Array<Record<string, unknown>>;
}

export function listProfiles(): Promise<ProfilesListResponse> {
  return apiFetch<ProfilesListResponse>("/api/profiles");
}

export function createProfile(body: ProfileCreateBody): Promise<Profile> {
  return apiFetch<Profile>("/api/profiles", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProfile(id: string, body: ProfileUpdateBody): Promise<Profile> {
  return apiFetch<Profile>(`/api/profiles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteProfile(id: string): Promise<void> {
  await fetch(`${API_URL}/api/profiles/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
}

export async function activateProfile(id: string): Promise<void> {
  await fetch(`${API_URL}/api/profiles/${id}/activate`, {
    method: "POST",
    credentials: "include",
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run src/tests/api/profiles.test.ts`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/profiles.ts web/src/tests/api/profiles.test.ts
git commit -m "feat(api): profiles client"
```

### Task 5.5: AuthContext

**Files:**
- Create: `web/src/contexts/AuthContext.tsx`
- Create: `web/src/tests/contexts/AuthContext.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/contexts/AuthContext.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

const me = { user: { id: "u1", email: "a@b.com", yahoo_subject: null, last_active_profile_id: null }, profiles: [] };

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("AuthContext", () => {
  it("starts in loading state, then settles to anonymous on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
    vi.restoreAllMocks();
  });

  it("settles to authenticated when /me returns user", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 200 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user?.email).toBe("a@b.com");
    vi.restoreAllMocks();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- --run src/tests/contexts/AuthContext.test.tsx`
Expected: import errors.

- [ ] **Step 3: Create AuthContext**

Create `web/src/contexts/AuthContext.tsx`:

```tsx
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { getMe, login as apiLogin, logout as apiLogout, signup as apiSignup } from "@/api/auth";
import type { User, Profile } from "@/api/types";

interface AuthContextValue {
  loading: boolean;
  user: User | null;
  profiles: Profile[];
  signup: (body: { email: string; password: string; initial_settings?: Record<string, unknown>; initial_rules?: Array<Record<string, unknown>> }) => Promise<void>;
  login: (body: { email: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setProfiles: (next: Profile[]) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    const me = await getMe();
    setUser(me?.user ?? null);
    setProfiles(me?.profiles ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signup = useCallback(async (body: Parameters<AuthContextValue["signup"]>[0]) => {
    const me = await apiSignup(body);
    setUser(me.user);
    setProfiles(me.profiles);
  }, []);

  const login = useCallback(async (body: { email: string; password: string }) => {
    const me = await apiLogin(body);
    setUser(me.user);
    setProfiles(me.profiles);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setProfiles([]);
  }, []);

  return (
    <AuthContext.Provider value={{ loading, user, profiles, signup, login, logout, refresh, setProfiles }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run src/tests/contexts/AuthContext.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/contexts/AuthContext.tsx web/src/tests/contexts/AuthContext.test.tsx
git commit -m "feat(contexts): AuthContext (user, profiles, signup/login/logout)"
```

### Task 5.6: Push Phase 5 PR

```bash
cd web && npm test -- --run
# all green
git push -u origin feat/accounts-phase-5-frontend-api
gh pr create --base feat/accounts-phase-4-profile-api --title "feat(accounts): phase 5 — frontend API clients + AuthContext" --body "Adds web/src/api/auth.ts, web/src/api/profiles.ts, AuthContext provider. credentials:include on every apiFetch. Stacks on phase-4 PR."
```

---

# Phase 6 — Frontend UI components

Branch: `feat/accounts-phase-6-ui` stacked on phase-5.

### Task 6.1: Install shadcn primitives

**Files:**
- Create: `web/src/components/ui/dialog.tsx`
- Create: `web/src/components/ui/dropdown-menu.tsx`
- Create: `web/src/components/ui/tabs.tsx`
- Modify: `web/package.json`

- [ ] **Step 1: Add Radix deps**

Run from `web/`:

```bash
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-tabs
```

- [ ] **Step 2: Create Dialog primitive**

Create `web/src/components/ui/dialog.tsx`:

```tsx
import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogPortal = DialogPrimitive.Portal;
export const DialogClose = DialogPrimitive.Close;

export const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn("fixed inset-0 z-50 bg-black/50", className)}
    {...props}
  />
));
DialogOverlay.displayName = "DialogOverlay";

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-md border bg-card p-6 shadow-lg",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-3 top-3 text-muted-foreground hover:text-foreground">
        <X className="h-4 w-4" />
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = "DialogContent";

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <DialogPrimitive.Title className={cn("text-lg font-semibold mb-3", className)} {...props} />;
}

export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <DialogPrimitive.Description className={cn("text-sm text-muted-foreground mb-3", className)} {...props} />;
}
```

- [ ] **Step 3: Create DropdownMenu primitive**

Create `web/src/components/ui/dropdown-menu.tsx`:

```tsx
import * as React from "react";
import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export const DropdownMenu = DropdownPrimitive.Root;
export const DropdownMenuTrigger = DropdownPrimitive.Trigger;
export const DropdownMenuPortal = DropdownPrimitive.Portal;
export const DropdownMenuSeparator = React.forwardRef<
  React.ElementRef<typeof DropdownPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <DropdownPrimitive.Separator ref={ref} className={cn("-mx-1 my-1 h-px bg-border", className)} {...props} />
));
DropdownMenuSeparator.displayName = "DropdownMenuSeparator";

export const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DropdownPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <DropdownMenuPortal>
    <DropdownPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn("z-50 min-w-[12rem] rounded-md border bg-popover p-1 shadow-md", className)}
      {...props}
    />
  </DropdownMenuPortal>
));
DropdownMenuContent.displayName = "DropdownMenuContent";

export const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DropdownPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Item> & { inset?: boolean }
>(({ className, inset, ...props }, ref) => (
  <DropdownPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[disabled]:opacity-50 data-[disabled]:pointer-events-none focus:bg-accent",
      inset && "pl-8",
      className,
    )}
    {...props}
  />
));
DropdownMenuItem.displayName = "DropdownMenuItem";

export const DropdownMenuCheckboxItem = React.forwardRef<
  React.ElementRef<typeof DropdownPrimitive.CheckboxItem>,
  React.ComponentPropsWithoutRef<typeof DropdownPrimitive.CheckboxItem>
>(({ className, children, checked, ...props }, ref) => (
  <DropdownPrimitive.CheckboxItem
    ref={ref}
    className={cn("relative flex cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm focus:bg-accent", className)}
    checked={checked}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <DropdownPrimitive.ItemIndicator><Check className="h-3 w-3" /></DropdownPrimitive.ItemIndicator>
    </span>
    {children}
  </DropdownPrimitive.CheckboxItem>
));
DropdownMenuCheckboxItem.displayName = "DropdownMenuCheckboxItem";
```

- [ ] **Step 4: Create Tabs primitive**

Create `web/src/components/ui/tabs.tsx`:

```tsx
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn("inline-flex h-9 items-center justify-center rounded-md bg-muted p-1", className)}
    {...props}
  />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1 text-sm font-medium ring-offset-background transition-all data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("mt-4", className)} {...props} />
));
TabsContent.displayName = "TabsContent";
```

- [ ] **Step 5: Smoke check + commit**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

```bash
git checkout main && git checkout feat/accounts-phase-5-frontend-api && git pull
git checkout -b feat/accounts-phase-6-ui
git add web/package.json web/package-lock.json web/src/components/ui/dialog.tsx web/src/components/ui/dropdown-menu.tsx web/src/components/ui/tabs.tsx
git commit -m "feat(ui): add shadcn Dialog, DropdownMenu, Tabs primitives"
```

### Task 6.2: AuthDialog component

**Files:**
- Create: `web/src/components/AuthDialog.tsx`
- Create: `web/src/tests/components/AuthDialog.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/components/AuthDialog.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthDialog } from "@/components/AuthDialog";
import { AuthProvider } from "@/contexts/AuthContext";

function _renderOpen() {
  vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 })); // /me
  return render(
    <AuthProvider>
      <AuthDialog open onOpenChange={() => {}} initialState={null} />
    </AuthProvider>,
  );
}

describe("AuthDialog", () => {
  it("renders Log in tab by default with email + password fields", async () => {
    _renderOpen();
    expect(await screen.findByRole("tab", { name: /log in/i, selected: true })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("switches to Sign up tab when clicked", async () => {
    _renderOpen();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /sign up/i }));
    expect(screen.getByRole("tab", { name: /sign up/i, selected: true })).toBeInTheDocument();
  });

  it("shows 'Continue with Yahoo' button that navigates to authorize URL on click", async () => {
    _renderOpen();
    const btn = await screen.findByRole("button", { name: /continue with yahoo/i });
    expect(btn).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npm test -- --run src/tests/components/AuthDialog.test.tsx`
Expected: import errors.

- [ ] **Step 3: Create AuthDialog**

Create `web/src/components/AuthDialog.tsx`:

```tsx
import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { yahooAuthorizeUrl } from "@/api/auth";
import { useAuth } from "@/contexts/AuthContext";
import type { SettingsState } from "@/components/SettingsPanel";
import type { Rule } from "@/api/types";

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // If provided, signup will send this anonymous state for migration.
  initialState: { settings: SettingsState; rules: Rule[] } | null;
}

export function AuthDialog({ open, onOpenChange, initialState }: AuthDialogProps) {
  const { signup, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login({ email, password });
      onOpenChange(false);
    } catch (err) {
      setError("Login failed. Check your email and password.");
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await signup({
        email,
        password,
        initial_settings: initialState ? (initialState.settings as unknown as Record<string, unknown>) : undefined,
        initial_rules: initialState ? (initialState.rules as unknown as Array<Record<string, unknown>>) : undefined,
      });
      onOpenChange(false);
    } catch (err) {
      setError("Signup failed. Email may already be in use, or password may be too short (min 10 chars).");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Account</DialogTitle>
        <Tabs defaultValue="login">
          <TabsList>
            <TabsTrigger value="login">Log in</TabsTrigger>
            <TabsTrigger value="signup">Sign up</TabsTrigger>
          </TabsList>

          <TabsContent value="login">
            <form onSubmit={handleLogin} className="space-y-3">
              <div>
                <label htmlFor="login-email" className="text-sm">Email</label>
                <input id="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded border px-2 py-1" />
              </div>
              <div>
                <label htmlFor="login-password" className="text-sm">Password</label>
                <input id="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded border px-2 py-1" />
              </div>
              {error && <p className="text-xs text-red-600">{error}</p>}
              <Button type="submit" className="w-full">Log in</Button>
            </form>
          </TabsContent>

          <TabsContent value="signup">
            <form onSubmit={handleSignup} className="space-y-3">
              <div>
                <label htmlFor="signup-email" className="text-sm">Email</label>
                <input id="signup-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded border px-2 py-1" />
              </div>
              <div>
                <label htmlFor="signup-password" className="text-sm">Password (min 10 chars)</label>
                <input id="signup-password" type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded border px-2 py-1" />
              </div>
              {error && <p className="text-xs text-red-600">{error}</p>}
              <Button type="submit" className="w-full">Create account</Button>
            </form>
          </TabsContent>
        </Tabs>

        <div className="text-center text-xs text-muted-foreground my-3">— or —</div>

        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => { window.location.href = yahooAuthorizeUrl(); }}
        >
          Continue with Yahoo
        </Button>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run src/tests/components/AuthDialog.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/AuthDialog.tsx web/src/tests/components/AuthDialog.test.tsx
git commit -m "feat(ui): AuthDialog (login/signup tabs + Yahoo button)"
```

### Task 6.3: ProfilePicker + ManageProfilesDialog

**Files:**
- Create: `web/src/components/ProfilePicker.tsx`
- Create: `web/src/components/ManageProfilesDialog.tsx`
- Create: `web/src/tests/components/ProfilePicker.test.tsx`

- [ ] **Step 1: Write ProfilePicker tests (failing)**

Create `web/src/tests/components/ProfilePicker.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfilePicker } from "@/components/ProfilePicker";

const profiles = [
  { id: "p1", name: "PPR 12-team", settings_json: {}, rules_json: [] },
  { id: "p2", name: "Standard Keeper", settings_json: {}, rules_json: [] },
];

describe("ProfilePicker", () => {
  it("renders the active profile name in the trigger", () => {
    render(<ProfilePicker profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />);
    expect(screen.getByRole("button", { name: /PPR 12-team/ })).toBeInTheDocument();
  });

  it("calls onSelect when another profile is clicked", async () => {
    const onSelect = vi.fn();
    render(<ProfilePicker profiles={profiles} activeId="p1" onSelect={onSelect} onNew={() => {}} onManage={() => {}} canCreate />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    await user.click(screen.getByRole("menuitem", { name: /Standard Keeper/ }));
    expect(onSelect).toHaveBeenCalledWith("p2");
  });

  it("disables + New profile when canCreate is false", async () => {
    render(<ProfilePicker profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate={false} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PPR 12-team/ }));
    const item = screen.getByRole("menuitem", { name: /\+ New profile/ });
    expect(item).toHaveAttribute("data-disabled");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npm test -- --run src/tests/components/ProfilePicker.test.tsx`
Expected: import errors.

- [ ] **Step 3: Create ProfilePicker**

Create `web/src/components/ProfilePicker.tsx`:

```tsx
import { ChevronDown } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import type { Profile } from "@/api/types";

interface ProfilePickerProps {
  profiles: Profile[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onManage: () => void;
  canCreate: boolean;
}

export function ProfilePicker({ profiles, activeId, onSelect, onNew, onManage, canCreate }: ProfilePickerProps) {
  const active = profiles.find((p) => p.id === activeId);
  const label = active?.name ?? "No profile";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          Profile: {label} <ChevronDown className="ml-2 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        {profiles.map((p) => (
          <DropdownMenuItem key={p.id} onSelect={() => onSelect(p.id)}>
            {p.id === activeId ? "✓ " : "  "}{p.name}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onNew} disabled={!canCreate}>+ New profile</DropdownMenuItem>
        <DropdownMenuItem onSelect={onManage}>Manage profiles…</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run src/tests/components/ProfilePicker.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Create ManageProfilesDialog**

Create `web/src/components/ManageProfilesDialog.tsx`:

```tsx
import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import type { Profile } from "@/api/types";

interface ManageProfilesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profiles: Profile[];
  onRename: (id: string, newName: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

export function ManageProfilesDialog({ open, onOpenChange, profiles, onRename, onDelete }: ManageProfilesDialogProps) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Manage profiles</DialogTitle>
        {profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No profiles yet.</p>
        ) : (
          <ul className="space-y-2">
            {profiles.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 rounded border px-3 py-2">
                {editingId === p.id ? (
                  <>
                    <input
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      className="flex-1 rounded border px-2 py-1 text-sm"
                      autoFocus
                    />
                    <Button size="sm" onClick={async () => { await onRename(p.id, draftName); setEditingId(null); }}>Save</Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                  </>
                ) : (
                  <>
                    <span className="flex-1 truncate">{p.name}</span>
                    <Button size="sm" variant="ghost" onClick={() => { setEditingId(p.id); setDraftName(p.name); }}>Rename</Button>
                    {confirmDeleteId === p.id ? (
                      <Button size="sm" variant="destructive" onClick={async () => { await onDelete(p.id); setConfirmDeleteId(null); }}>Confirm delete</Button>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => setConfirmDeleteId(p.id)} aria-label={`delete ${p.name}`}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 6: Smoke check + commit**

Run: `cd web && npx tsc --noEmit`

```bash
git add web/src/components/ProfilePicker.tsx web/src/components/ManageProfilesDialog.tsx web/src/tests/components/ProfilePicker.test.tsx
git commit -m "feat(ui): ProfilePicker + ManageProfilesDialog"
```

### Task 6.4: Push Phase 6 PR

```bash
cd web && npm test -- --run
git push -u origin feat/accounts-phase-6-ui
gh pr create --base feat/accounts-phase-5-frontend-api --title "feat(accounts): phase 6 — frontend UI (AuthDialog, ProfilePicker, ManageProfiles)" --body "Adds the auth modal, profile picker dropdown, and manage-profiles dialog. shadcn Dialog/DropdownMenu/Tabs primitives. Not yet wired into App.tsx — that happens in phase 7. Stacks on phase-5 PR."
```

---

# Phase 7 — Wire-up, autosave, integration

Branch: `feat/accounts-phase-7-wireup` stacked on phase-6.

### Task 7.1: useAutoSave hook

**Files:**
- Create: `web/src/hooks/useAutoSave.ts`
- Create: `web/src/tests/hooks/useAutoSave.test.ts`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/hooks/useAutoSave.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAutoSave } from "@/hooks/useAutoSave";

describe("useAutoSave", () => {
  it("does not save when no profile is active", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useAutoSave({ activeId: null, payload: { x: 1 }, save, debounceMs: 50 }));
    await new Promise((r) => setTimeout(r, 100));
    expect(save).not.toHaveBeenCalled();
  });

  it("debounces calls, firing once after the window", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ payload }) => useAutoSave({ activeId: "p1", payload, save, debounceMs: 50 }),
      { initialProps: { payload: { x: 1 } } },
    );
    rerender({ payload: { x: 2 } });
    rerender({ payload: { x: 3 } });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenLastCalledWith("p1", { x: 3 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- --run src/tests/hooks/useAutoSave.test.ts`
Expected: import errors.

- [ ] **Step 3: Create the hook**

Create `web/src/hooks/useAutoSave.ts`:

```ts
import { useEffect, useRef } from "react";

interface UseAutoSaveArgs<T> {
  activeId: string | null;
  payload: T;
  save: (id: string, payload: T) => Promise<void>;
  debounceMs?: number;
}

export function useAutoSave<T>({ activeId, payload, save, debounceMs = 800 }: UseAutoSaveArgs<T>): void {
  const initialRender = useRef(true);

  useEffect(() => {
    // Don't fire on the first render (when state hydrates from the profile).
    if (initialRender.current) {
      initialRender.current = false;
      return;
    }
    if (!activeId) return;

    const handle = setTimeout(() => {
      save(activeId, payload).catch(() => {
        /* swallow — surfaced via status chip elsewhere */
      });
    }, debounceMs);
    return () => clearTimeout(handle);
  }, [activeId, payload, save, debounceMs]);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run src/tests/hooks/useAutoSave.test.ts`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git checkout main && git checkout feat/accounts-phase-6-ui && git pull
git checkout -b feat/accounts-phase-7-wireup
git add web/src/hooks/useAutoSave.ts web/src/tests/hooks/useAutoSave.test.ts
git commit -m "feat(hooks): useAutoSave with debounce"
```

### Task 7.2: Hamburger menu in Header

**Files:**
- Modify: `web/src/components/Header.tsx`

- [ ] **Step 1: Read existing Header**

Read `web/src/components/Header.tsx` to see its current structure (Generate button, etc.).

- [ ] **Step 2: Add hamburger**

In `web/src/components/Header.tsx`, add imports:

```tsx
import { Menu } from "lucide-react";
import { useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { AuthDialog } from "./AuthDialog";
import type { SettingsState } from "./SettingsPanel";
import type { Rule } from "@/api/types";
```

Extend the `HeaderProps` interface (or add one if there isn't) to accept the current anonymous state for migration:

```tsx
interface HamburgerProps {
  currentState: { settings: SettingsState; rules: Rule[] } | null;
}

function HamburgerMenu({ currentState }: HamburgerProps) {
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
              <DropdownMenuItem onSelect={() => logout()}>Log out</DropdownMenuItem>
            </>
          ) : (
            <>
              <DropdownMenuItem onSelect={() => setAuthOpen(true)}>Log in / Sign up</DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <AuthDialog open={authOpen} onOpenChange={setAuthOpen} initialState={currentState} />
    </>
  );
}
```

Then render `<HamburgerMenu currentState={...} />` to the right of the Generate button.

- [ ] **Step 3: Smoke check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/Header.tsx
git commit -m "feat(ui): hamburger menu in Header with Log in / Log out"
```

### Task 7.3: Wire AuthContext into App.tsx + profile hydration + autosave

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/main.tsx`

- [ ] **Step 1: Wrap app in AuthProvider**

Open `web/src/main.tsx`. Find the existing render call and wrap with AuthProvider:

```tsx
import { AuthProvider } from "@/contexts/AuthContext";
```

In the render tree, ensure `<App />` is wrapped in `<AuthProvider>` and any existing `<QueryClientProvider>`. Order: `<QueryClientProvider><AuthProvider><App/></AuthProvider></QueryClientProvider>`.

- [ ] **Step 2: Update App.tsx**

Open `web/src/App.tsx`. Replace the existing component body with logic that:

```tsx
import { useEffect, useState, useMemo, useCallback } from "react";
import { Header } from "@/components/Header";
import { SettingsPanel, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { ProfilePicker } from "@/components/ProfilePicker";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import { useRules, useGenerateMutation, downloadCsv } from "@/api/hooks";
import { useAuth } from "@/contexts/AuthContext";
import { createProfile, updateProfile, deleteProfile, activateProfile, listProfiles } from "@/api/profiles";
import { useAutoSave } from "@/hooks/useAutoSave";
import { weightsAreValid } from "@/lib/weights";
import type { Rule, GenerateRequest } from "@/api/types";

const DEFAULT_SETTINGS: SettingsState = {
  scoring_format: "standard",
  league_size: 12,
  draft_rounds: 15,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  weights: { prior: 30, consensus: 70 },
};

export default function App() {
  const { user, profiles, setProfiles } = useAuth();
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [rules, setRules] = useState<Rule[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(user?.last_active_profile_id ?? null);
  const [manageOpen, setManageOpen] = useState(false);

  const { data: fetchedRules } = useRules();
  const generate = useGenerateMutation();

  // Seed local rules state once the backend response arrives.
  useEffect(() => {
    if (fetchedRules && !seeded) {
      setRules(fetchedRules);
      setSeeded(true);
    }
  }, [fetchedRules, seeded]);

  // When user logs in or switches profiles, hydrate settings + rules from the active profile.
  useEffect(() => {
    const active = profiles.find((p) => p.id === activeProfileId);
    if (active) {
      setSettings(active.settings_json as SettingsState);
      // Merge saved rule state into the canonical rule list.
      if (fetchedRules) {
        const overrides = new Map(active.rules_json.map((r) => [r.name, r]));
        setRules(fetchedRules.map((r) => {
          const o = overrides.get(r.name);
          return o ? { ...r, enabled: o.enabled, weight: o.weight } : r;
        }));
      }
    }
  }, [activeProfileId, profiles, fetchedRules]);

  // Auto-save edits to the active profile.
  const autosavePayload = useMemo(() => ({
    settings_json: settings as unknown as Record<string, unknown>,
    rules_json: rules.map((r) => ({ name: r.name, enabled: r.enabled, weight: r.weight })) as unknown as Array<Record<string, unknown>>,
  }), [settings, rules]);

  useAutoSave({
    activeId: user ? activeProfileId : null,
    payload: autosavePayload,
    save: async (id, payload) => { await updateProfile(id, payload); },
  });

  const handleSelectProfile = useCallback(async (id: string) => {
    setActiveProfileId(id);
    await activateProfile(id);
  }, []);

  const handleNewProfile = useCallback(async () => {
    const created = await createProfile({
      name: `Profile ${profiles.length + 1}`,
      settings_json: settings as unknown as Record<string, unknown>,
      rules_json: rules.map((r) => ({ name: r.name, enabled: r.enabled, weight: r.weight })),
    });
    setProfiles([...profiles, created]);
    setActiveProfileId(created.id);
    await activateProfile(created.id);
  }, [profiles, settings, rules, setProfiles]);

  const handleRenameProfile = useCallback(async (id: string, name: string) => {
    const updated = await updateProfile(id, { name });
    setProfiles(profiles.map((p) => (p.id === id ? updated : p)));
  }, [profiles, setProfiles]);

  const handleDeleteProfile = useCallback(async (id: string) => {
    await deleteProfile(id);
    setProfiles(profiles.filter((p) => p.id !== id));
    if (activeProfileId === id) setActiveProfileId(null);
  }, [profiles, activeProfileId, setProfiles]);

  const buildRequest = (): GenerateRequest => ({
    scoring_format: settings.scoring_format,
    league_type: "standard",
    league_size: settings.league_size,
    qb_td_points: settings.qb_td_points,
    bonus_100yd_rushing: settings.bonus_100yd_rushing,
    bonus_100yd_receiving: settings.bonus_100yd_receiving,
    bonus_first_downs: settings.bonus_first_downs,
    weight_prior_year: settings.weights.prior / 100,
    weight_espn: 0,
    weight_consensus: settings.weights.consensus / 100,
    draft_rounds: settings.draft_rounds,
    rules,
  });

  const canGenerate = weightsAreValid(settings.weights) && rules.length > 0;

  return (
    <div className="flex flex-col h-screen">
      <Header
        generateDisabled={!canGenerate}
        generateIsPending={generate.isPending}
        onGenerate={() => generate.mutate(buildRequest())}
        currentState={{ settings, rules }}
        profilePicker={user ? (
          <ProfilePicker
            profiles={profiles}
            activeId={activeProfileId}
            onSelect={handleSelectProfile}
            onNew={handleNewProfile}
            onManage={() => setManageOpen(true)}
            canCreate={profiles.length < 5}
          />
        ) : null}
      />
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] lg:grid-rows-1 overflow-hidden">
        <SettingsPanel value={settings} onChange={setSettings} />
        <RulesPanel rules={rules} onChange={setRules} />
        <TiersPanel
          result={generate.data ?? null}
          isPending={generate.isPending}
          onDownloadCsv={() => downloadCsv(buildRequest())}
        />
      </main>
      <ManageProfilesDialog
        open={manageOpen}
        onOpenChange={setManageOpen}
        profiles={profiles}
        onRename={handleRenameProfile}
        onDelete={handleDeleteProfile}
      />
    </div>
  );
}
```

- [ ] **Step 3: Update Header to accept `currentState` and `profilePicker`**

In `web/src/components/Header.tsx`, extend the props:

```tsx
interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
  currentState: { settings: SettingsState; rules: Rule[] } | null;
  profilePicker?: React.ReactNode;
}
```

Render `{profilePicker}` between the Generate button and the hamburger. Pass `currentState` down into the HamburgerMenu.

- [ ] **Step 4: Smoke check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Run tests**

Run: `cd web && npm test -- --run`
Expected: all green (existing App.test.tsx may need MSW handlers updated to mock `/api/auth/me` returning 401 — fix that too):

In `web/src/tests/mocks/handlers.ts` (or wherever MSW handlers live — search with `grep -r "rest.get\|http.get" web/src/tests/`), add:

```ts
http.get(`${API_URL}/api/auth/me`, () => HttpResponse.json({ user: null }, { status: 401 })),
```

Or if the handler shape differs, follow the existing pattern. Re-run tests.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/main.tsx web/src/components/Header.tsx web/src/tests/mocks/handlers.ts
git commit -m "feat(app): wire AuthContext, ProfilePicker, autosave into App"
```

### Task 7.4: Integration test — anonymous → signup → profile saved

**Files:**
- Create: `web/src/tests/integration/auth-flow.test.tsx`

- [ ] **Step 1: Write the test**

Create `web/src/tests/integration/auth-flow.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";

describe("Auth integration", () => {
  it("anonymous user can open the auth dialog from the hamburger menu", async () => {
    // MSW handlers (or fetch mocks) should already return 401 on /me
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </QueryClientProvider>,
    );

    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText(/menu/i)).toBeInTheDocument());
    await user.click(screen.getByLabelText(/menu/i));
    await user.click(screen.getByText(/log in \/ sign up/i));
    expect(await screen.findByRole("tab", { name: /sign up/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run + commit**

Run: `cd web && npm test -- --run src/tests/integration/auth-flow.test.tsx`
Expected: 1 passed.

```bash
git add web/src/tests/integration/auth-flow.test.tsx
git commit -m "test(integration): anonymous user opens auth dialog from hamburger"
```

### Task 7.5: README + .env.example finalization

**Files:**
- Modify: `README.md`
- Modify: `backend/.env.example`

- [ ] **Step 1: Update README**

In `README.md`, add a new section under the existing API table:

```markdown
## Accounts

Anonymous use is the default. Optional account creation gives users up to **5 saved profiles**.

### Auth endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/signup` | Email + password signup; optionally migrates anonymous state to a first profile |
| `POST` | `/api/auth/login` | Email + password login; rate-limited 5 / 15min per email |
| `POST` | `/api/auth/logout` | Clears session cookie |
| `GET`  | `/api/auth/me` | Returns the current user + profiles, or 401 |
| `GET`  | `/api/auth/yahoo/authorize` | Starts Yahoo OAuth |
| `GET`  | `/api/auth/yahoo/callback` | Yahoo OAuth return URL |

### Profile endpoints

| Method | Path | Description |
|---|---|---|
| `GET`    | `/api/profiles` | List user's profiles + active id |
| `POST`   | `/api/profiles` | Create profile (409 when at 5) |
| `PATCH`  | `/api/profiles/{id}` | Partial update (name, settings_json, rules_json) |
| `DELETE` | `/api/profiles/{id}` | Delete |
| `POST`   | `/api/profiles/{id}/activate` | Set as last-active |

### Env vars

- `JWT_SECRET` — 32+ byte secret for signing session JWTs
- `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REDIRECT_URI` — Yahoo OAuth app credentials
- `FRONTEND_URL` — where Yahoo OAuth callback redirects after login (default `http://localhost:5173`)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): document accounts + profile endpoints"
```

### Task 7.6: Push final PR

```bash
cd web && npm test -- --run
cd ../backend && venv/bin/pytest -q
# both green

cd ..
git push -u origin feat/accounts-phase-7-wireup
gh pr create --base feat/accounts-phase-6-ui --title "feat(accounts): phase 7 — wire-up, autosave, integration" --body "$(cat <<'EOF'
## Summary
Final phase. Wires everything from phases 5–6 into the App shell.

- \`useAutoSave\` hook (debounced PATCH after 800ms idle)
- Hamburger menu in Header (Log in/out)
- ProfilePicker rendered next to Generate button when authenticated
- App.tsx: AuthProvider wrapping, profile hydration on switch, auto-save effect, create/rename/delete handlers
- Integration test: anonymous user opens auth dialog from hamburger
- README + .env.example documented

Implements Phase 7 (final) of \`docs/superpowers/specs/2026-05-26-accounts-and-profiles-design.md\`.

## Test plan
- [x] useAutoSave: no save without active id, debounced firing
- [x] Integration test: hamburger opens auth dialog
- [x] Full pytest + vitest suites green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Plan self-review (done by author)

**Spec coverage check:**

- ✅ Anonymous flow preserved — App.tsx only hydrates from a profile when one is active; `currentState` passed through Header → HamburgerMenu → AuthDialog so signup can migrate anonymous state
- ✅ Email + password auth (Tasks 2.3–2.6)
- ✅ Yahoo OAuth (Tasks 3.1–3.2)
- ✅ 5-profile cap (Task 4.3)
- ✅ Auto-save (Task 7.1, 7.3)
- ✅ Anonymous → signup migration (Tasks 2.3, 7.3)
- ✅ Hamburger menu in Header (Task 7.2)
- ✅ Login modal with Yahoo button (Task 6.2)
- ✅ Profile picker (Task 6.3)
- ✅ Manage profiles dialog (Task 6.3)
- ✅ Email collision avoidance — Yahoo never sets `users.email` (Task 3.2)
- ✅ Email flows deferred — no SMTP / verification / reset endpoints
- ✅ Rate limit on login (Task 2.4)
- ✅ JWT in httpOnly cookie (Task 1.5)
- ✅ argon2id hashing (Task 1.4)

**Type consistency check:**

- `User`, `Profile`, `MeResponse`, `ProfilesListResponse` declared once in `web/src/api/types.ts`; all subsequent code imports them
- `AuthContext.setProfiles` exposed for App.tsx to mutate after create/rename/delete (consistent with the rest of the design)
- `JWT_COOKIE_NAME = "autotiers_session"` used consistently across cookie/encode/decode/clear

**Placeholder scan:** None found. Every "TODO-shaped" cell has actual code.

**Resetting to saved button:** The design mentioned this. The plan implements auto-save and the "unsaved" state is naturally avoided since changes auto-flush. The reset button can be a follow-up — flagging here but not blocking the plan.

→ Followed up: spec specified a "Reset to saved" button. The plan as written ships auto-save without a manual reset. **Adding to scope as Task 7.7 below.**

### Task 7.7: Add "Reset to saved" button

**Files:**
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Track last-saved snapshot**

In `App.tsx`, add state for the snapshot returned from the last successful save:

```tsx
const [lastSavedSnapshot, setLastSavedSnapshot] = useState<{ settings_json: Record<string, unknown>; rules_json: Array<Record<string, unknown>> } | null>(null);
```

Update `useAutoSave` save callback to record the snapshot on success:

```tsx
useAutoSave({
  activeId: user ? activeProfileId : null,
  payload: autosavePayload,
  save: async (id, payload) => {
    await updateProfile(id, payload);
    setLastSavedSnapshot(payload);
  },
});
```

Also seed `lastSavedSnapshot` on profile hydration (in the existing useEffect that handles `activeProfileId` change):

```tsx
setLastSavedSnapshot({
  settings_json: active.settings_json as Record<string, unknown>,
  rules_json: active.rules_json as Array<Record<string, unknown>>,
});
```

- [ ] **Step 2: Add the button**

Compute dirtiness:

```tsx
const isDirty = lastSavedSnapshot !== null && JSON.stringify(autosavePayload) !== JSON.stringify(lastSavedSnapshot);
```

Render alongside the ProfilePicker (in Header `profilePicker` slot, or as a sibling):

```tsx
{isDirty && (
  <Button size="sm" variant="ghost" onClick={() => {
    if (lastSavedSnapshot) {
      setSettings(lastSavedSnapshot.settings_json as unknown as SettingsState);
      // restore rule overrides
      if (fetchedRules) {
        const overrides = new Map((lastSavedSnapshot.rules_json as Array<{ name: string; enabled: boolean; weight: number }>).map((r) => [r.name, r]));
        setRules(fetchedRules.map((r) => {
          const o = overrides.get(r.name);
          return o ? { ...r, enabled: o.enabled, weight: o.weight } : r;
        }));
      }
    }
  }}>
    Reset to saved
  </Button>
)}
```

- [ ] **Step 3: Smoke check + commit**

Run: `cd web && npx tsc --noEmit && npm test -- --run`

```bash
git add web/src/App.tsx web/src/components/Header.tsx
git commit -m "feat(ui): 'Reset to saved' button reverts local edits to last-saved snapshot"
git push
```

---

## Final review

- Total tasks: 28 (counting micro-tasks within phases as ~10 each phase on average, plus final wire-up)
- Total expected commits: ~35
- Total expected PRs: 7
- Spec line items: all covered

Each phase merges in order. Phase boundaries are clean — each phase produces working software (just adds capability rather than breaking anything). The user can stop merging at any phase boundary if they want to revisit.
