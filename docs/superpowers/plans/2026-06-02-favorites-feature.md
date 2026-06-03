# Favorites Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authenticated users can favorite up to 20 players and 4 NFL teams from a new tab on their account page; favorited entities trigger a single user-tunable "Favorites" rule (MULTIPLIER 1.05 default) during tier generation.

**Architecture:** A new `user_favorites` table stores `favorite_player_ids` + `favorite_teams` JSON arrays keyed by `user_id`. A new auth-gated REST surface (`GET/PUT /api/favorites` + `GET /api/players?q=`) manages them. The generate endpoint resolves favorites server-side from the auth cookie (no frontend wire-up needed in `GenerateRequest`) and injects an `is_favorite` boolean into each `PlayerContext`. A new `Favorites` builtin rule fires when `is_favorite == True`. The frontend adds a tab to `LinkedAccountsDialog`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + pytest (backend); React 18 + TypeScript + Vite + vitest + MSW (frontend); shadcn/ui + Tailwind.

**Spec:** [`docs/superpowers/specs/2026-06-02-favorites-feature-design.md`](../specs/2026-06-02-favorites-feature-design.md). Any disagreement between this plan and the spec → the spec wins, fix this plan. The **"Open questions — resolved by Manager triage"** section at the end of the spec is authoritative; ignore the spec body's interim recommendations where they conflict (specifically: player search via new endpoint, NOT recent-generate-result; favorites resolved server-side, NOT in `GenerateRequest`).

---

## Pre-flight reading (15 minutes)

Engineer must `Read` these before touching code:

1. `docs/superpowers/specs/2026-06-02-favorites-feature-design.md` — full design including math sign-off and out-of-scope list.
2. `backend/app/models/user.py` — `User` ORM, FK target for the new table.
3. `backend/app/models/profile.py` — `Profile` ORM, JSON columns pattern (uses `JSONB().with_variant(JSON(), "sqlite")`); the auto-enable logic writes to `profile.rules_json`.
4. `backend/alembic/versions/007_*.py` — most recent migration; confirms `revision = "007"` short-numeric convention.
5. `backend/app/api/profiles_api.py` — auth-gated CRUD pattern with `require_user`; mirror this in `favorites_api.py`.
6. `backend/app/api/generate.py` (`_run_generate` and the `PlayerContext(...)` construction around line 271) — wire-up site for `is_favorite`.
7. `backend/app/engine/rules.py` (`PlayerContext`, `Rule`, `RuleCondition`, `RuleEffect`, `_evaluate`) — rule engine surface. Read carefully: when a condition field is `None`, the rule does NOT fire — this is what makes anonymous-call safety work.
8. `backend/app/api/rules.py` — current `GET /rules` handler; will need to become auth-aware.
9. `backend/app/engine/builtin_rules.py` — for the new `Favorites` Rule entry.
10. `web/src/components/LinkedAccountsDialog.tsx` and `LinkedLeagueSection.tsx` — tab pattern to mirror.
11. `web/src/contexts/AuthContext.tsx` — auth state surface (decide hook vs. context for favorites).
12. `web/src/api/profiles.ts` — API client pattern to mirror in `favorites.ts`.
13. `.claude/skills/autotiers-test-running/SKILL.md` — pytest paths + warnings to ignore.
14. `.claude/skills/autotiers-bug-classes/SKILL.md` — Classes 2 (empty validation), 3 (identity), 5 (migration), 6 (UI inconsistency) all apply.

## File map (decomposition decisions)

**Backend — create:**
- `backend/app/models/user_favorites.py` — `UserFavorites` ORM model. JSON columns via `JSONB().with_variant(JSON(), "sqlite")`.
- `backend/alembic/versions/008_user_favorites.py` — migration creating the table.
- `backend/app/schemas/favorites.py` — `FavoritesUpdate`, `FavoritesOut`.
- `backend/app/api/favorites_api.py` — `GET /favorites`, `PUT /favorites`.
- `backend/app/api/players_search.py` — `GET /players?q=<name>` (separate file, single endpoint, no scope creep with `players_api.py` if one exists later).
- `backend/app/data/teams.py` — canonical 32-team abbreviation set.
- `backend/tests/test_favorites.py` — endpoint + cap + dedup + 32-team validation tests.
- `backend/tests/test_favorites_auto_enable.py` — auto-enable-rule-on-first-add tests (separate file because the cross-table coupling is non-trivial to reason about).
- `backend/tests/test_players_search.py` — search endpoint tests.
- `backend/tests/test_favorites_integration.py` — end-to-end: favorited player gets the rule applied in `_run_generate`.

**Backend — modify:**
- `backend/app/models/__init__.py` — export `UserFavorites`.
- `backend/app/engine/rules.py` — add `is_favorite: Optional[bool] = None` to `PlayerContext`.
- `backend/app/engine/builtin_rules.py` — append `Favorites` Rule entry.
- `backend/app/api/rules.py` — `_CATEGORIES` gets `"Favorites": "Personal"`; `GET /rules` becomes auth-aware via `get_current_user` (NOT `require_user`) and filters out `Favorites` when `current_user is None`.
- `backend/app/api/generate.py` — pre-pass fetches the user's favorites from DB; per-player `is_favorite` populates `PlayerContext`.
- `backend/app/main.py` — include the new routers.
- `backend/tests/test_rules.py` — extend test fixture defaults to include `is_favorite=None`.

**Frontend — create:**
- `web/src/api/favorites.ts` — `getFavorites`, `putFavorites`, `searchPlayers` API clients.
- `web/src/hooks/useFavorites.ts` — fetches favorites on mount when authenticated, exposes `{favorites, save}`. Optimistic update + error revert.
- `web/src/components/FavoritesPanel.tsx` — the tab body.
- `web/src/tests/api/favorites.test.ts` — API client tests with MSW.
- `web/src/tests/hooks/useFavorites.test.tsx` — hook tests.
- `web/src/tests/components/FavoritesPanel.test.tsx` — component tests.

**Frontend — modify:**
- `web/src/api/types.ts` — add `FavoritesOut`, `FavoritesUpdate`, `PlayerSearchResult` interfaces.
- `web/src/components/LinkedAccountsDialog.tsx` — new "Favorites" tab gated on `user !== null`.

**Frontend — do NOT touch:**
- `web/src/api/generate.ts` — favorites are server-side. Generate payload unchanged.
- `web/src/components/RulesPanel.tsx` — `GET /rules` already filters; the panel just renders what it's given.

## Decomposition rationale

- The auto-enable-rule-on-first-add logic lives inside `PUT /favorites` but has cross-table side effects (writes to `profiles.rules_json`). Splitting it from the basic CRUD task lets the engineer get the CRUD tested cleanly first, then layer the side effect on top.
- The player search endpoint is a single GET, separate file. Doesn't grow with future per-position endpoints; if those happen, they get their own files.
- The 32-team canonical set lives in `app/data/teams.py` because the team-validation code in favorites is its first consumer but the frontend's team-grid UI will also benefit from a single canonical source (which the engineer may or may not surface to the FE in a follow-up).
- Frontend `useFavorites` is a custom hook, NOT part of `AuthContext`. Reason: favorites only need to be available where they're consumed (the FavoritesPanel and — server-side — by the generate endpoint). Polluting `AuthContext` with feature-specific state grows it without bound.

---

## Task 1: Backend — `UserFavorites` model + Alembic migration 008

**Files:**
- Create: `backend/app/models/user_favorites.py`
- Create: `backend/alembic/versions/008_user_favorites.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_user_favorites_model.py` (new)

- [ ] **Step 1.1: Write failing model test**

Create `backend/tests/test_user_favorites_model.py`:

```python
"""Tests for the UserFavorites ORM model."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserFavorites


@pytest.mark.asyncio
async def test_user_favorites_round_trip(test_db: AsyncSession):
    user = User(email="fav@example.com", password_hash="x" * 60)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    fav = UserFavorites(
        user_id=user.id,
        favorite_player_ids=["4046", "7564"],
        favorite_teams=["KC", "BUF"],
    )
    test_db.add(fav)
    await test_db.commit()

    loaded = (await test_db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one()
    assert loaded.favorite_player_ids == ["4046", "7564"]
    assert loaded.favorite_teams == ["KC", "BUF"]


@pytest.mark.asyncio
async def test_user_favorites_defaults(test_db: AsyncSession):
    """A freshly-created row with no favorites round-trips as empty lists."""
    user = User(email="empty@example.com", password_hash="x" * 60)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    fav = UserFavorites(user_id=user.id, favorite_player_ids=[], favorite_teams=[])
    test_db.add(fav)
    await test_db.commit()

    loaded = (await test_db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one()
    assert loaded.favorite_player_ids == []
    assert loaded.favorite_teams == []
```

- [ ] **Step 1.2: Run test, expect ImportError on `UserFavorites`**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_user_favorites_model.py -v 2>&1 | tail -10
```

- [ ] **Step 1.3: Create the model file**

Create `backend/app/models/user_favorites.py`:

```python
"""User favorites: favorite player IDs and favorite NFL team abbreviations.

One row per user. Both lists are stored as JSON arrays. Caps (20 players,
4 teams) are enforced at the API layer, not in the DB schema, so that an
existing user above-cap from a future cap change is not broken by storage.
"""
import uuid
from sqlalchemy import String, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserFavorites(Base):
    __tablename__ = "user_favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    favorite_player_ids: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    favorite_teams: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )

    user: Mapped["User"] = relationship(back_populates="favorites")
```

- [ ] **Step 1.4: Add the `favorites` relationship on User**

Open `backend/app/models/user.py`. Find the `class User(Base):` body. After the last existing relationship (whatever it is — likely `profiles`), add:

```python
    favorites: Mapped[Optional["UserFavorites"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
```

If `Optional` is not yet imported, add `from typing import Optional` at the top.

- [ ] **Step 1.5: Export UserFavorites from `app.models`**

Open `backend/app/models/__init__.py`. Add:

```python
from app.models.user_favorites import UserFavorites
```

Append `"UserFavorites"` to `__all__` if `__all__` is present.

- [ ] **Step 1.6: Create Alembic migration 008**

First check the latest migration's revision id so the chain is right:

```bash
ls /Users/karlkell/Code/AutoTiers/backend/alembic/versions/ | sort | tail -3
```

The latest should be `007_*.py`. Then create `backend/alembic/versions/008_user_favorites.py`:

```python
"""Add user_favorites table.

Revision ID: 008
Revises: 007
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "favorite_player_ids",
            JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "favorite_teams",
            JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_favorites")
```

If the existing migrations use a different revision id format (string vs. numeric), match what `007` does. Look at `007_*.py` to confirm.

- [ ] **Step 1.7: Run model test — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_user_favorites_model.py -v 2>&1 | tail -15
```

Both tests should pass. If the `test_db` fixture doesn't auto-apply migrations, also run a quick Alembic check:

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/alembic upgrade head 2>&1 | tail -5
```

Should report `Running upgrade 007 -> 008, Add user_favorites table` (or similar — successful chain advancement).

- [ ] **Step 1.8: Full broader sweep to confirm no model regressions**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_models_user_profile.py tests/test_user_favorites_model.py -v 2>&1 | tail -10
```

- [ ] **Step 1.9: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/models/user_favorites.py backend/app/models/user.py backend/app/models/__init__.py backend/alembic/versions/008_user_favorites.py backend/tests/test_user_favorites_model.py
git commit -m "feat(models): UserFavorites table + migration 008

One row per user; favorite_player_ids and favorite_teams are JSON arrays.
JSONB on Postgres, JSON on SQLite (for the test engine). Caps enforced
in the API layer; DB doesn't constrain length to avoid breaking existing
users if caps change later. Cascade-delete on user removal.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Backend — Pydantic schemas + canonical 32-team set

**Files:**
- Create: `backend/app/schemas/favorites.py`
- Create: `backend/app/data/teams.py`
- Test: `backend/tests/test_favorites_schemas.py` (new)

- [ ] **Step 2.1: Write failing schema tests**

Create `backend/tests/test_favorites_schemas.py`:

```python
"""Tests for favorites Pydantic schemas + the canonical 32-team set."""
import pytest
from pydantic import ValidationError

from app.schemas.favorites import FavoritesUpdate, FavoritesOut
from app.data.teams import NFL_TEAMS, is_valid_team


def test_canonical_teams_is_32():
    assert len(NFL_TEAMS) == 32


def test_canonical_teams_contains_known_codes():
    for code in ["KC", "BUF", "NYJ", "PHI", "DAL", "GB", "SEA"]:
        assert code in NFL_TEAMS, f"{code} should be in NFL_TEAMS"


def test_is_valid_team_accepts_canonical():
    assert is_valid_team("KC")


def test_is_valid_team_rejects_unknown():
    assert not is_valid_team("XYZ")


def test_is_valid_team_rejects_empty():
    assert not is_valid_team("")


def test_favorites_update_accepts_empty():
    """Default state: both lists empty."""
    f = FavoritesUpdate()
    assert f.favorite_player_ids == []
    assert f.favorite_teams == []


def test_favorites_update_accepts_populated():
    f = FavoritesUpdate(favorite_player_ids=["4046"], favorite_teams=["KC"])
    assert f.favorite_player_ids == ["4046"]
    assert f.favorite_teams == ["KC"]


def test_favorites_update_rejects_non_list_ids():
    with pytest.raises(ValidationError):
        FavoritesUpdate(favorite_player_ids="4046")  # string, not list


def test_favorites_out_from_attributes():
    """FavoritesOut must support ORM-attribute construction."""
    class _Stub:
        favorite_player_ids = ["4046"]
        favorite_teams = ["KC"]
    f = FavoritesOut.model_validate(_Stub())
    assert f.favorite_player_ids == ["4046"]
    assert f.favorite_teams == ["KC"]
```

- [ ] **Step 2.2: Run tests, expect ImportError**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_schemas.py -v 2>&1 | tail -10
```

- [ ] **Step 2.3: Create the canonical teams module**

Create `backend/app/data/teams.py`:

```python
"""Canonical set of NFL team abbreviations.

Used by the favorites API to validate `favorite_teams` entries against
the actual 32-team league. Treat this as the single source of truth;
the frontend's team-grid UI should also draw from it (via an endpoint
or a duplicated constant — duplication is acceptable if synced when
this set ever changes).
"""

NFL_TEAMS: frozenset[str] = frozenset({
    "ARI", "ATL", "BAL", "BUF",
    "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV",  "MIA",
    "MIN", "NE",  "NO",  "NYG",
    "NYJ", "PHI", "PIT", "SEA",
    "SF",  "TB",  "TEN", "WAS",
})


def is_valid_team(code: str) -> bool:
    """Whether `code` is a known canonical NFL team abbreviation.

    Empty / whitespace-only strings return False (Class 2 guard).
    """
    if not code or not code.strip():
        return False
    return code in NFL_TEAMS
```

- [ ] **Step 2.4: Create the Pydantic schemas**

Create `backend/app/schemas/favorites.py`:

```python
"""Request/response shapes for /api/favorites."""
from pydantic import BaseModel, Field


class FavoritesUpdate(BaseModel):
    """PUT /favorites request body.

    Caps and team-validity are enforced in the API handler, not here, so
    error responses are domain-specific (Class 1: misleading error copy
    avoidance).
    """
    favorite_player_ids: list[str] = Field(default_factory=list)
    favorite_teams: list[str] = Field(default_factory=list)


class FavoritesOut(BaseModel):
    """GET /favorites response body."""
    favorite_player_ids: list[str]
    favorite_teams: list[str]

    model_config = {"from_attributes": True}
```

- [ ] **Step 2.5: Run tests — expect all pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_schemas.py -v 2>&1 | tail -15
```

10 tests should pass.

- [ ] **Step 2.6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/data/teams.py backend/app/schemas/favorites.py backend/tests/test_favorites_schemas.py
git commit -m "feat(schemas): Pydantic schemas + canonical 32-team set for favorites

NFL_TEAMS frozenset + is_valid_team guard reject empty/unknown codes.
FavoritesUpdate / FavoritesOut keep validation thin so domain errors
land with specific copy in the API layer.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Backend — `GET /favorites` + `PUT /favorites` (CRUD only, no auto-enable yet)

**Files:**
- Create: `backend/app/api/favorites_api.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_favorites.py` (new)

- [ ] **Step 3.1: Write failing endpoint tests**

Create `backend/tests/test_favorites.py`:

```python
"""Endpoint tests for GET /favorites and PUT /favorites — CRUD layer only.

Auto-enable-rule-on-first-add behavior is covered separately in
test_favorites_auto_enable.py.
"""
import pytest
from httpx import AsyncClient


async def _signup_and_login(async_client: AsyncClient, email: str = "fav@example.com") -> None:
    """Helper: signup + login via cookie. Returns nothing — async_client
    persists the auth cookie via its cookie jar."""
    await async_client.post("/api/auth/signup", json={
        "email": email, "password": "password-long-enough",
    })
    # signup auto-logs-in via session cookie; nothing else needed.


@pytest.mark.asyncio
async def test_get_favorites_returns_empty_for_new_user(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/favorites")
    assert r.status_code == 200
    body = r.json()
    assert body == {"favorite_player_ids": [], "favorite_teams": []}


@pytest.mark.asyncio
async def test_get_favorites_requires_auth(async_client: AsyncClient):
    r = await async_client.get("/api/favorites")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_put_favorites_persists(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    }
    # And it survives a second GET.
    r = await async_client.get("/api/favorites")
    assert r.json() == {
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    }


@pytest.mark.asyncio
async def test_put_favorites_replaces_existing(async_client: AsyncClient, test_db):
    """Subsequent PUT fully replaces the prior favorites — not a merge."""
    await _signup_and_login(async_client)
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": ["KC"],
    })
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["9999"], "favorite_teams": ["BUF"],
    })
    assert r.status_code == 200
    assert r.json() == {"favorite_player_ids": ["9999"], "favorite_teams": ["BUF"]}


@pytest.mark.asyncio
async def test_put_favorites_rejects_over_player_cap(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    too_many = [str(i) for i in range(21)]
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": too_many, "favorite_teams": [],
    })
    assert r.status_code == 409
    assert "20" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_over_team_cap(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    too_many = ["KC", "BUF", "NYJ", "PHI", "DAL"]  # 5 teams
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": too_many,
    })
    assert r.status_code == 409
    assert "4" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_unknown_team(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["XYZ"],
    })
    assert r.status_code == 422
    assert "XYZ" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_whitespace_player_id(async_client: AsyncClient, test_db):
    """Class 2 guard: whitespace-only strings pass min_length but mean nothing."""
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["   "], "favorite_teams": [],
    })
    assert r.status_code == 422
    assert "blank" in r.json()["detail"].lower() or "empty" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_favorites_deduplicates(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "4046", "7564"],
        "favorite_teams": ["KC", "KC"],
    })
    assert r.status_code == 200
    assert r.json() == {"favorite_player_ids": ["4046", "7564"], "favorite_teams": ["KC"]}


@pytest.mark.asyncio
async def test_put_favorites_requires_auth(async_client: AsyncClient):
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 401
```

- [ ] **Step 3.2: Run tests, expect 10 failures (router not registered yet)**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites.py -v 2>&1 | tail -15
```

- [ ] **Step 3.3: Implement the favorites router**

Create `backend/app/api/favorites_api.py`:

```python
"""User favorites CRUD. Auth-gated."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserFavorites
from app.auth.dependencies import require_user
from app.schemas.favorites import FavoritesUpdate, FavoritesOut
from app.data.teams import is_valid_team

router = APIRouter(prefix="/favorites", tags=["favorites"])

_PLAYER_CAP = 20
_TEAM_CAP = 4


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _validate_and_normalize(body: FavoritesUpdate) -> tuple[list[str], list[str]]:
    """Apply cap, blank, team-validity, and dedup rules. Raise HTTPException on violation."""
    # Class 2 guard: reject blank/whitespace-only entries before counting toward the cap.
    if any(not pid or not pid.strip() for pid in body.favorite_player_ids):
        raise HTTPException(status_code=422, detail="Player ID entries must not be blank.")
    if any(not t or not t.strip() for t in body.favorite_teams):
        raise HTTPException(status_code=422, detail="Team entries must not be blank.")

    # Team validity against the canonical 32.
    for team in body.favorite_teams:
        if not is_valid_team(team):
            raise HTTPException(status_code=422, detail=f"Unknown team: {team}")

    # Dedup BEFORE cap check so the cap reflects unique entries.
    player_ids = _dedupe_preserve_order(body.favorite_player_ids)
    teams = _dedupe_preserve_order(body.favorite_teams)

    if len(player_ids) > _PLAYER_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Too many favorite players (max {_PLAYER_CAP}).",
        )
    if len(teams) > _TEAM_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Too many favorite teams (max {_TEAM_CAP}).",
        )
    return player_ids, teams


@router.get("", response_model=FavoritesOut)
async def get_favorites(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> FavoritesOut:
    row = (await db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one_or_none()
    if row is None:
        return FavoritesOut(favorite_player_ids=[], favorite_teams=[])
    return FavoritesOut.model_validate(row)


@router.put("", response_model=FavoritesOut)
async def put_favorites(
    body: FavoritesUpdate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> FavoritesOut:
    player_ids, teams = _validate_and_normalize(body)

    row = (await db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one_or_none()
    if row is None:
        row = UserFavorites(
            user_id=user.id,
            favorite_player_ids=player_ids,
            favorite_teams=teams,
        )
        db.add(row)
    else:
        row.favorite_player_ids = player_ids
        row.favorite_teams = teams

    await db.commit()
    await db.refresh(row)
    return FavoritesOut.model_validate(row)
```

- [ ] **Step 3.4: Register the router in main.py**

Open `backend/app/main.py`. Find where the existing routers are included (e.g. `app.include_router(profiles_api.router, prefix="/api")`). Add adjacent to them:

```python
from app.api import favorites_api
app.include_router(favorites_api.router, prefix="/api")
```

- [ ] **Step 3.5: Run tests — expect all pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites.py -v 2>&1 | tail -25
```

10 tests should pass. If any fail with `require_user` import errors, confirm the import path matches what `profiles_api.py` uses.

- [ ] **Step 3.6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/api/favorites_api.py backend/app/main.py backend/tests/test_favorites.py
git commit -m "feat(api): GET/PUT /favorites with cap, dedup, blank-input, team-validity guards

Two endpoints, both auth-gated via require_user. PUT is full replacement.
Validation:
- Class 2: rejects blank / whitespace-only player IDs and team codes.
- Caps: 20 favorite players (409 over), 4 favorite teams (409 over).
- Team validity: must be in the canonical 32-team set (422 with the
  unknown code in the message).
- Duplicates: deduplicated before cap check, preserve insertion order.

GET on a never-PUT user returns {[], []} rather than 404 — favorites are
always present in the conceptual user state.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Backend — auto-enable Favorites rule on first add

**Files:**
- Modify: `backend/app/api/favorites_api.py` (extend `put_favorites`)
- Test: `backend/tests/test_favorites_auto_enable.py` (new)

- [ ] **Step 4.1: Write failing tests**

Create `backend/tests/test_favorites_auto_enable.py`:

```python
"""Tests for the auto-enable side effect inside PUT /favorites.

When a user transitions from 0 favorites to 1+, the Favorites rule must
flip to enabled in their currently-active profile's rules_json — in the
same transaction.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Profile


async def _signup_and_make_active_profile(async_client, test_db: AsyncSession) -> tuple[User, Profile]:
    """Signs up via the public API + activates a profile. Returns (user, profile)."""
    await async_client.post("/api/auth/signup", json={
        "email": "auto@example.com", "password": "password-long-enough",
    })
    user = (await test_db.scalars(
        select(User).where(User.email == "auto@example.com")
    )).one()
    # Signup creates a default profile and activates it.
    profile = (await test_db.scalars(
        select(Profile).where(Profile.user_id == user.id)
    )).first()
    assert profile is not None, "signup should have created a default profile"
    user.last_active_profile_id = profile.id
    await test_db.commit()
    return user, profile


def _rule_state(profile: Profile, name: str) -> tuple[bool, float] | None:
    """Look up (enabled, weight) for a rule name in the profile's rules_json. None if absent."""
    for entry in profile.rules_json:
        if entry.get("name") == name:
            return entry.get("enabled", True), entry.get("weight", 1.0)
    return None


@pytest.mark.asyncio
async def test_first_favorite_add_enables_rule(async_client, test_db):
    user, profile = await _signup_and_make_active_profile(async_client, test_db)
    # Confirm pre-state: Favorites rule absent or disabled.
    pre = _rule_state(profile, "Favorites")
    assert pre is None or pre[0] is False, "expected Favorites to start off"

    # First add.
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text

    await test_db.refresh(profile)
    post = _rule_state(profile, "Favorites")
    assert post is not None, "Favorites rule should be present in rules_json after first add"
    assert post[0] is True, "Favorites rule should be enabled after first add"


@pytest.mark.asyncio
async def test_subsequent_add_does_not_re_enable_disabled_rule(async_client, test_db):
    """User may have intentionally disabled the rule after first add.
    A SUBSEQUENT add (still > 0) must not re-enable it."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    # First add — auto-enables.
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    await test_db.refresh(profile)
    # User disables the rule manually.
    profile.rules_json = [
        ({"name": "Favorites", "enabled": False, "weight": 1.0}
         if entry.get("name") == "Favorites" else entry)
        for entry in profile.rules_json
    ]
    await test_db.commit()
    await test_db.refresh(profile)

    # Subsequent add — should NOT re-enable.
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "7564"], "favorite_teams": [],
    })
    await test_db.refresh(profile)
    post = _rule_state(profile, "Favorites")
    assert post is not None and post[0] is False, (
        "Favorites rule must stay disabled when user has explicitly disabled it, "
        "even if count goes 1 → 2."
    )


@pytest.mark.asyncio
async def test_transition_to_empty_does_not_disable_rule(async_client, test_db):
    """Removing the last favorite should NOT disable the rule. The rule
    silently no-ops when there are no favorites (is_favorite never True);
    leaving it enabled means a re-add Just Works without surprising the user."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    # First add — auto-enables.
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    await test_db.refresh(profile)

    # Remove everything.
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": [],
    })
    await test_db.refresh(profile)
    post = _rule_state(profile, "Favorites")
    assert post is not None, "Favorites rule should still be in rules_json"
    assert post[0] is True, "Favorites rule should remain enabled after going to empty"
```

- [ ] **Step 4.2: Run tests — expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_auto_enable.py -v 2>&1 | tail -15
```

The first test fails because `Favorites` isn't injected into the profile yet.

- [ ] **Step 4.3: Extend `put_favorites` with the auto-enable side effect**

Open `backend/app/api/favorites_api.py`. Add this helper at module scope, after the existing helpers:

```python
async def _maybe_enable_favorites_rule(db: AsyncSession, user: User) -> None:
    """If the user's active profile doesn't yet list 'Favorites' in rules_json,
    append it as enabled. Does NOT modify a 'Favorites' entry that already
    exists (so a user who disabled the rule keeps it disabled across
    subsequent adds)."""
    if user.last_active_profile_id is None:
        return
    profile = await db.get(Profile, user.last_active_profile_id)
    if profile is None:
        return
    current_names = {entry.get("name") for entry in profile.rules_json if isinstance(entry, dict)}
    if "Favorites" in current_names:
        return  # already present (may be enabled OR disabled by the user)
    profile.rules_json = [
        *profile.rules_json,
        {"name": "Favorites", "enabled": True, "weight": 1.0},
    ]
```

Add the import at the top:

```python
from app.models import User, UserFavorites, Profile
```

Modify the body of `put_favorites` — right before the final `await db.commit()`, add:

```python
    # Auto-enable the Favorites rule on the user's transition from 0 favorites
    # to 1+, but only if the rule isn't already present. Same transaction.
    had_favorites_before = (
        row is not None
        and (bool(row.favorite_player_ids) or bool(row.favorite_teams))
    ) if "row" in dir() else False
    # Note: row was set above. If a fresh row was created, it has the new lists
    # already. So we have to check the PRIOR state separately:
```

Wait — this is awkward. Re-do the integration so the "had-favorites-before" check is clean. Replace the body of `put_favorites` with this complete version:

```python
@router.put("", response_model=FavoritesOut)
async def put_favorites(
    body: FavoritesUpdate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> FavoritesOut:
    player_ids, teams = _validate_and_normalize(body)

    row = (await db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one_or_none()

    had_any_before = (
        row is not None
        and (bool(row.favorite_player_ids) or bool(row.favorite_teams))
    )

    if row is None:
        row = UserFavorites(
            user_id=user.id,
            favorite_player_ids=player_ids,
            favorite_teams=teams,
        )
        db.add(row)
    else:
        row.favorite_player_ids = player_ids
        row.favorite_teams = teams

    has_any_now = bool(player_ids) or bool(teams)

    # Auto-enable the Favorites rule on the user's transition from 0 → 1+,
    # in the same transaction so a partial failure can't desync.
    if has_any_now and not had_any_before:
        await _maybe_enable_favorites_rule(db, user)

    await db.commit()
    await db.refresh(row)
    return FavoritesOut.model_validate(row)
```

- [ ] **Step 4.4: Run auto-enable tests + CRUD tests — expect all pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_auto_enable.py tests/test_favorites.py -v 2>&1 | tail -20
```

- [ ] **Step 4.5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/api/favorites_api.py backend/tests/test_favorites_auto_enable.py
git commit -m "feat(favorites): auto-enable Favorites rule on user's first add

Inside the PUT /favorites transaction, when a user transitions from 0
favorites to 1+, append the Favorites rule as enabled to their currently
active profile's rules_json — if it's not already present. Skipped when:
- the user already had favorites (so subsequent adds don't re-enable)
- a 'Favorites' entry is already in rules_json (so user-disabled stays
  user-disabled across re-adds)
- the user has no active profile (degenerate)

Going to zero favorites does NOT disable the rule (covered by test) —
the rule silently no-ops when is_favorite is never True, and a re-add
Just Works.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Backend — `GET /api/players?q=<name>` search endpoint

**Files:**
- Create: `backend/app/api/players_search.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_players_search.py` (new)

- [ ] **Step 5.1: Write failing endpoint tests**

Create `backend/tests/test_players_search.py`:

```python
"""Tests for GET /api/players?q=<name>.

Auth-gated. Returns matching players (id, name, position, team), capped
at 25 results.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.player import Player


async def _seed_players(test_db: AsyncSession):
    players = [
        Player(id="1", name="Saquon Barkley", position="RB", team="PHI"),
        Player(id="2", name="Christian McCaffrey", position="RB", team="SF"),
        Player(id="3", name="Justin Jefferson", position="WR", team="MIN"),
        Player(id="4", name="Jefferson Davis", position="WR", team="HOU"),
        Player(id="5", name="JaMarr Chase", position="WR", team="CIN"),
    ]
    for p in players:
        test_db.add(p)
    await test_db.commit()


async def _signup_and_login(async_client) -> None:
    await async_client.post("/api/auth/signup", json={
        "email": "search@example.com", "password": "password-long-enough",
    })


@pytest.mark.asyncio
async def test_search_requires_auth(async_client):
    r = await async_client.get("/api/players?q=jeff")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_search_basic_match(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=jefferson")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Justin Jefferson" in names
    assert "Jefferson Davis" in names
    assert "Saquon Barkley" not in names


@pytest.mark.asyncio
async def test_search_case_insensitive(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=BARKLEY")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Saquon Barkley" in names


@pytest.mark.asyncio
async def test_search_returns_required_fields(async_client, test_db):
    await _seed_players(test_db)
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=jefferson")
    items = r.json()
    assert items, "expected at least one match"
    first = items[0]
    assert set(first.keys()) >= {"id", "name", "position", "team"}


@pytest.mark.asyncio
async def test_search_empty_q_returns_400(async_client, test_db):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=")
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_search_caps_results_at_25(async_client, test_db):
    """Seed 30 players with similar names, expect at most 25 returned."""
    for i in range(30):
        test_db.add(Player(id=f"p{i}", name=f"Test Player {i}", position="WR", team="KC"))
    await test_db.commit()
    await _signup_and_login(async_client)
    r = await async_client.get("/api/players?q=Test")
    assert r.status_code == 200
    assert len(r.json()) <= 25
```

- [ ] **Step 5.2: Run tests, expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_players_search.py -v 2>&1 | tail -10
```

- [ ] **Step 5.3: Implement the search endpoint**

Create `backend/app/api/players_search.py`:

```python
"""Auth-gated player-by-name search. Powers the favorites picker UI."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.models.player import Player
from app.auth.dependencies import require_user

router = APIRouter(prefix="/players", tags=["players"])

_RESULT_CAP = 25


class PlayerSearchResult(BaseModel):
    id: str
    name: str
    position: str
    team: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[PlayerSearchResult])
async def search_players(
    q: Annotated[str, Query(min_length=1, max_length=80)],
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> list[PlayerSearchResult]:
    """Case-insensitive substring match on Player.name. Returns up to 25 rows."""
    q_clean = q.strip()
    if not q_clean:
        raise HTTPException(status_code=400, detail="Query must not be blank.")
    pattern = f"%{q_clean.lower()}%"
    rows = (await db.scalars(
        select(Player)
        .where(func.lower(Player.name).like(pattern))
        .order_by(Player.name)
        .limit(_RESULT_CAP)
    )).all()
    return [PlayerSearchResult.model_validate(r) for r in rows]
```

- [ ] **Step 5.4: Register router in main.py**

Open `backend/app/main.py`. Add adjacent to the favorites router include:

```python
from app.api import players_search
app.include_router(players_search.router, prefix="/api")
```

- [ ] **Step 5.5: Run tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_players_search.py -v 2>&1 | tail -15
```

6 tests pass.

- [ ] **Step 5.6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/api/players_search.py backend/app/main.py backend/tests/test_players_search.py
git commit -m "feat(api): GET /api/players?q=<name> player search for favorites picker

Auth-gated. Case-insensitive substring match against Player.name with a
25-row cap and an order-by-name for stable UX. Returns (id, name,
position, team). Empty/whitespace-only q gets 400; max length 80 is
enforced by FastAPI param validation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Backend — rule engine integration (PlayerContext field + builtin rule + categorization + auth-aware GET /rules)

**Files:**
- Modify: `backend/app/engine/rules.py`
- Modify: `backend/app/engine/builtin_rules.py`
- Modify: `backend/app/api/rules.py`
- Modify: `backend/tests/test_rules.py` (extend `make_ctx` defaults)
- Test: `backend/tests/test_favorites_rule.py` (new — rule behavior)
- Test: `backend/tests/test_rules_api_favorites.py` (new — auth-aware GET /rules)

- [ ] **Step 6.1: Add `is_favorite` field to PlayerContext**

Open `backend/app/engine/rules.py`. Find the `PlayerContext` dataclass. Add this as the last field:

```python
    is_favorite: Optional[bool] = None
```

- [ ] **Step 6.2: Update test_rules.py fixture defaults**

Open `backend/tests/test_rules.py`. In each `defaults` dict inside `_ctx` / `make_ctx` helpers, append:

```python
        is_favorite=None,
```

- [ ] **Step 6.3: Write failing tests for the Favorites rule**

Create `backend/tests/test_favorites_rule.py`:

```python
"""Tests for the new Favorites builtin rule."""
import pytest
from app.engine.rules import PlayerContext, apply_rules, Rule
from app.engine.builtin_rules import BUILTIN_RULES


def make_ctx(**overrides) -> PlayerContext:
    defaults = dict(
        player_id="p", position="WR", age=25, snap_pct=0.7,
        carry_share=None, target_share=0.20, games_played=16,
        years_exp=4, adp=50.0, projected_score=180.0,
        new_team=False, new_coach=False,
        actual_tds=None, expected_tds=None, actual_tds_above_expected=None,
        red_zone_looks=None, is_over_the_hill=None,
        projection_unavailable=None, prior_touches=None,
        injured_two_years_ago=None, bad_offense_team=None,
        above_market_contract=None, is_favorite=None,
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def _favorites_rule() -> Rule:
    return next(r for r in BUILTIN_RULES if r.name == "Favorites")


def test_favorites_rule_fires_when_is_favorite_true():
    rule = _favorites_rule()
    ctx = make_ctx(is_favorite=True)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    # 180 × 1.05 = 189
    assert result.adjusted_score == pytest.approx(189.0, abs=0.01)
    assert "Favorites" in result.rules_applied


def test_favorites_rule_does_not_fire_when_is_favorite_false():
    rule = _favorites_rule()
    ctx = make_ctx(is_favorite=False)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Favorites" not in result.rules_applied


def test_favorites_rule_does_not_fire_when_is_favorite_is_none():
    """None must mean 'not evaluated' — silent no-op for anon users."""
    rule = _favorites_rule()
    ctx = make_ctx(is_favorite=None)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Favorites" not in result.rules_applied
```

- [ ] **Step 6.4: Run tests — expect failures (rule not present yet)**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_rule.py -v 2>&1 | tail -10
```

- [ ] **Step 6.5: Add Favorites to BUILTIN_RULES**

Open `backend/app/engine/builtin_rules.py`. Append (just before the closing `]` of `BUILTIN_RULES`):

```python
    Rule(
        name="Favorites",
        conditions=[RuleCondition(field="is_favorite", operator="==", value=True)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.05),
        description=(
            "Boosts players you've marked as favorites — either directly by player "
            "or by team. +5% at default weight. This is a personalization layer, "
            "not a statistical claim."
        ),
    ),
```

- [ ] **Step 6.6: Add Favorites to rule categorization**

Open `backend/app/api/rules.py`. Find `_CATEGORIES`. Add this entry (alphabetically or grouped with similar):

```python
    "Favorites": "Personal",
```

- [ ] **Step 6.7: Run rule tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_rule.py tests/test_rules.py -v 2>&1 | tail -15
```

All pass.

- [ ] **Step 6.8: Write failing tests for auth-aware GET /rules**

Create `backend/tests/test_rules_api_favorites.py`:

```python
"""Tests for the auth-aware GET /rules behavior introduced for Favorites.

Anonymous users must NOT see the Favorites rule. Authenticated users must.
"""
import pytest


@pytest.mark.asyncio
async def test_get_rules_anon_hides_favorites(async_client, test_db):
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    names = [rule["name"] for rule in r.json()]
    assert "Favorites" not in names, (
        "Anonymous users must not see the Favorites rule — it has no meaning without an account."
    )


@pytest.mark.asyncio
async def test_get_rules_authed_shows_favorites(async_client, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "ruletest@example.com", "password": "password-long-enough",
    })
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    names = [rule["name"] for rule in r.json()]
    assert "Favorites" in names


@pytest.mark.asyncio
async def test_get_rules_favorites_categorized_personal(async_client, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "categorize@example.com", "password": "password-long-enough",
    })
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    fav = next(rule for rule in r.json() if rule["name"] == "Favorites")
    assert fav["category"] == "Personal"
```

- [ ] **Step 6.9: Run rules-api tests — expect anon-hides test to fail**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_rules_api_favorites.py -v 2>&1 | tail -10
```

The anon test fails because `GET /rules` is currently auth-blind. The categorized test passes (assuming Task 6.6 was done).

- [ ] **Step 6.10: Make GET /rules auth-aware**

Open `backend/app/api/rules.py`. Find the `GET /rules` handler. Locate or add a `get_current_user` (NOT `require_user` — anonymous needs to keep working). The existing auth dependencies module should have one; if not, the existing `require_user` is typically built on top of a `get_optional_user` or similar. Check `backend/app/auth/dependencies.py`.

Modify the handler signature to accept `current_user: Optional[User] = Depends(get_current_user)`. Then in the response-building code, filter:

```python
@router.get("", response_model=list[RuleOut])
async def get_rules(
    current_user: Optional[User] = Depends(get_current_user),
) -> list[RuleOut]:
    out: list[RuleOut] = []
    for rule in BUILTIN_RULES:
        if rule.name == "Favorites" and current_user is None:
            continue
        out.append(RuleOut(
            name=rule.name,
            category=_categorize(rule.name),
            ...
        ))
    return out
```

(Adapt to the existing return-shape — the key change is the `if rule.name == "Favorites" and current_user is None: continue` line.)

If `get_current_user` does not exist, create it in `backend/app/auth/dependencies.py`:

```python
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    session_cookie: Optional[str] = Cookie(default=None, alias="autotiers_session"),
) -> Optional[User]:
    """Resolve the current user from the session cookie, or None if unauthenticated.
    Unlike require_user, does NOT 401 — returns None instead."""
    if session_cookie is None:
        return None
    # Existing _resolve_user logic, but return None on failure instead of raising.
    return await _resolve_user(db, session_cookie)
```

(Adapt to the actual existing structure in that file.)

- [ ] **Step 6.11: Run rules-api tests — expect all pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_rules_api_favorites.py -v 2>&1 | tail -10
```

- [ ] **Step 6.12: Run the broader rules sweep to catch regressions**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_rules.py tests/test_favorites_rule.py tests/test_rules_api_favorites.py -v 2>&1 | tail -15
```

- [ ] **Step 6.13: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/engine/rules.py backend/app/engine/builtin_rules.py backend/app/api/rules.py backend/app/auth/dependencies.py backend/tests/test_rules.py backend/tests/test_favorites_rule.py backend/tests/test_rules_api_favorites.py
git commit -m "feat(engine): Favorites builtin rule + auth-aware GET /rules

- PlayerContext gains is_favorite: Optional[bool] = None. None means 'not
  evaluated' (anonymous case); the rule engine's _evaluate guard
  returns False on None, so the rule silently no-ops.
- BUILTIN_RULES gains a 'Favorites' rule: MULTIPLIER 1.05, condition
  is_favorite == True. Category: 'Personal'.
- GET /rules becomes auth-aware via get_current_user. Filters Favorites
  from the response for anonymous users.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Backend — generate endpoint wire-up (server-side favorites lookup)

**Files:**
- Modify: `backend/app/api/generate.py`
- Test: `backend/tests/test_favorites_integration.py` (new)

- [ ] **Step 7.1: Write failing integration test**

Create `backend/tests/test_favorites_integration.py`:

```python
"""End-to-end: a favorited player gets the Favorites rule applied during generate."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.scoring import ScoringFormat, LeagueType
from app.schemas.generate import GenerateRequest
from app.api.generate import _run_generate
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models import User, UserFavorites


async def _signup(async_client, email: str = "intg@example.com") -> None:
    await async_client.post("/api/auth/signup", json={
        "email": email, "password": "password-long-enough",
    })


async def _seed_two_wrs(test_db: AsyncSession) -> None:
    for pid, name, team in [("FAV", "Saquon Barkley", "PHI"), ("UNFAV", "Other Guy", "PHI")]:
        test_db.add(Player(id=pid, name=name, position="WR", team=team, age=26, years_exp=4))
        test_db.add(PlayerStat(
            player_id=pid, season=2024,
            targets=80, receptions=50, rec_yards=600.0, rec_tds=4,
            rush_att=0, rush_yards=0.0, rush_tds=0,
            pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
            snaps=900, snap_pct=0.8, target_share=0.20,
            games_played=16, red_zone_looks=10,
        ))
        test_db.add(Projection(
            player_id=pid, source="fantasypros",
            scoring_format="ppr", projected_points=180.0, season=2025,
        ))
    await test_db.commit()


@pytest.mark.asyncio
async def test_favorited_player_gets_rule_applied_in_generate(async_client, test_db):
    await _signup(async_client)
    await _seed_two_wrs(test_db)

    # Add FAV as a favorite player. PUT auto-enables the Favorites rule.
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["FAV"], "favorite_teams": [],
    })
    assert r.status_code == 200

    # Now fire generate. _run_generate must look up the user's favorites and
    # apply the rule to FAV but not to UNFAV.
    # We call generate via the HTTP endpoint (so the auth cookie threads through),
    # not the function directly.
    r = await async_client.post("/api/generate", json={
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False, "bonus_100yd_receiving": False, "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        "rules": [{"name": "Favorites", "enabled": True, "weight": 1.0}],
        "keepers": [],
    })
    assert r.status_code == 200, r.text
    by_id = {p["player_id"]: p for p in r.json()["tiered"]}
    assert "Favorites" in by_id["FAV"]["rules_applied"]
    assert "Favorites" not in by_id["UNFAV"]["rules_applied"]
    # Boost: 180 × 1.05 = 189
    assert by_id["FAV"]["adjusted_score"] > by_id["UNFAV"]["adjusted_score"]


@pytest.mark.asyncio
async def test_favorite_team_boosts_all_team_players(async_client, test_db):
    await _signup(async_client, email="team@example.com")
    await _seed_two_wrs(test_db)

    # Favorite team PHI — both FAV and UNFAV are on PHI.
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["PHI"],
    })
    assert r.status_code == 200

    r = await async_client.post("/api/generate", json={
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False, "bonus_100yd_receiving": False, "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        "rules": [{"name": "Favorites", "enabled": True, "weight": 1.0}],
        "keepers": [],
    })
    by_id = {p["player_id"]: p for p in r.json()["tiered"]}
    assert "Favorites" in by_id["FAV"]["rules_applied"]
    assert "Favorites" in by_id["UNFAV"]["rules_applied"]


@pytest.mark.asyncio
async def test_anonymous_generate_does_not_apply_favorites(async_client, test_db):
    """Anon generate must not crash and must not fire the Favorites rule."""
    await _seed_two_wrs(test_db)
    r = await async_client.post("/api/generate", json={
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False, "bonus_100yd_receiving": False, "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        "rules": [{"name": "Favorites", "enabled": True, "weight": 1.0}],
        "keepers": [],
    })
    assert r.status_code == 200, r.text
    for p in r.json()["tiered"]:
        assert "Favorites" not in p["rules_applied"]
```

- [ ] **Step 7.2: Run integration test — expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_integration.py -v 2>&1 | tail -15
```

- [ ] **Step 7.3: Wire favorites into `_run_generate`**

Open `backend/app/api/generate.py`.

**(a) Imports** — add near the top:

```python
from app.models import UserFavorites
from app.auth.dependencies import get_current_user
```

**(b) Endpoint signature** — find the `@router.post("/generate")` handler and add the auth-optional dependency. Adapt the existing handler's signature to add `current_user: Optional[User] = Depends(get_current_user)` and pass it through to `_run_generate`. Change the `_run_generate` function signature to accept `current_user: Optional[User] = None`.

**(c) Inside `_run_generate`** — before the `for player in players:` loop, add the favorites lookup:

```python
    # Server-side favorites lookup (per Manager-resolved decision in the spec).
    # Anonymous calls: empty sets, is_favorite is None per player, rule no-ops.
    favorite_pids_set: set[str] = set()
    favorite_teams_set: set[str] = set()
    if current_user is not None:
        fav_row = (await db.scalars(
            select(UserFavorites).where(UserFavorites.user_id == current_user.id)
        )).one_or_none()
        if fav_row is not None:
            favorite_pids_set = set(fav_row.favorite_player_ids or [])
            favorite_teams_set = set(fav_row.favorite_teams or [])
    has_any_favorites = bool(favorite_pids_set or favorite_teams_set)
```

**(d) Inside the per-player loop** — compute `is_favorite`:

```python
        if has_any_favorites:
            is_favorite = (
                player.id in favorite_pids_set
                or (player.team is not None and player.team in favorite_teams_set)
            )
        else:
            is_favorite = None  # rule silently no-ops
```

**(e) PlayerContext constructor** — add the field. Find the `PlayerContext(...)` constructor call (around line 271 of generate.py). Append `is_favorite=is_favorite,` as the last keyword argument.

- [ ] **Step 7.4: Run integration tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_favorites_integration.py -v 2>&1 | tail -15
```

- [ ] **Step 7.5: Full backend sweep**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/ -q --ignore=tests/test_sources 2>&1 | tail -5
```

Confirm no existing tests regressed. The most likely regression sites are `tests/test_xfp_integration.py` (also uses `_run_generate`) and the existing generate tests.

- [ ] **Step 7.6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/api/generate.py backend/tests/test_favorites_integration.py
git commit -m "feat(generate): server-side favorites lookup; is_favorite on PlayerContext

Per Manager-resolved spec decision: generate resolves favorites from the
authenticated user's UserFavorites row rather than from the request body.
Anonymous calls produce empty favorite sets; per-player is_favorite is
None and the Favorites rule silently no-ops.

Integration tests cover: favorited player gets the rule applied;
favorited TEAM boosts all players on that team; anonymous generate runs
clean without applying the rule to anyone.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Frontend — types + API client + hook

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/api/favorites.ts`
- Create: `web/src/hooks/useFavorites.ts`
- Create: `web/src/tests/api/favorites.test.ts`
- Create: `web/src/tests/hooks/useFavorites.test.tsx`

- [ ] **Step 8.1: Add types**

Open `web/src/api/types.ts`. Append:

```typescript
export interface FavoritesOut {
  favorite_player_ids: string[];
  favorite_teams: string[];
}

export type FavoritesUpdate = FavoritesOut;  // same shape

export interface PlayerSearchResult {
  id: string;
  name: string;
  position: string;
  team: string | null;
}
```

- [ ] **Step 8.2: Write failing API client test**

Create `web/src/tests/api/favorites.test.ts`:

```typescript
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { getFavorites, putFavorites, searchPlayers } from "@/api/favorites";

const server = setupServer(
  http.get("/api/favorites", () =>
    HttpResponse.json({ favorite_player_ids: ["1", "2"], favorite_teams: ["KC"] })
  ),
  http.put("/api/favorites", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json(body);
  }),
  http.get("/api/players", ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q");
    if (!q) return new HttpResponse(null, { status: 400 });
    return HttpResponse.json([
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI" },
    ]);
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());

describe("favorites API client", () => {
  it("getFavorites returns the parsed payload", async () => {
    const fav = await getFavorites();
    expect(fav.favorite_player_ids).toEqual(["1", "2"]);
    expect(fav.favorite_teams).toEqual(["KC"]);
  });

  it("putFavorites echoes the persisted state", async () => {
    const saved = await putFavorites({ favorite_player_ids: ["3"], favorite_teams: ["BUF"] });
    expect(saved).toEqual({ favorite_player_ids: ["3"], favorite_teams: ["BUF"] });
  });

  it("searchPlayers returns matches", async () => {
    const results = await searchPlayers("Saq");
    expect(results).toHaveLength(1);
    expect(results[0].name).toBe("Saquon Barkley");
  });
});
```

- [ ] **Step 8.3: Run test, expect import failure**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/api/favorites.test.ts 2>&1 | tail -10
```

- [ ] **Step 8.4: Implement the API client**

Create `web/src/api/favorites.ts`:

```typescript
import { apiFetch } from "@/api/client";
import type { FavoritesOut, FavoritesUpdate, PlayerSearchResult } from "@/api/types";

export async function getFavorites(): Promise<FavoritesOut> {
  const res = await apiFetch("/api/favorites");
  if (!res.ok) throw new Error(`getFavorites: ${res.status}`);
  return (await res.json()) as FavoritesOut;
}

export async function putFavorites(body: FavoritesUpdate): Promise<FavoritesOut> {
  const res = await apiFetch("/api/favorites", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `putFavorites: ${res.status}`);
  }
  return (await res.json()) as FavoritesOut;
}

export async function searchPlayers(q: string): Promise<PlayerSearchResult[]> {
  const params = new URLSearchParams({ q });
  const res = await apiFetch(`/api/players?${params.toString()}`);
  if (!res.ok) throw new Error(`searchPlayers: ${res.status}`);
  return (await res.json()) as PlayerSearchResult[];
}
```

- [ ] **Step 8.5: Run API tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/api/favorites.test.ts 2>&1 | tail -10
```

- [ ] **Step 8.6: Write failing hook test**

Create `web/src/tests/hooks/useFavorites.test.tsx`:

```typescript
import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useFavorites } from "@/hooks/useFavorites";

let saved: any = null;

const server = setupServer(
  http.get("/api/favorites", () =>
    HttpResponse.json({ favorite_player_ids: ["initial"], favorite_teams: ["KC"] })
  ),
  http.put("/api/favorites", async ({ request }) => {
    saved = await request.json();
    return HttpResponse.json(saved);
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());
beforeEach(() => { saved = null; });

describe("useFavorites", () => {
  it("fetches favorites on mount when authenticated", async () => {
    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));
  });

  it("does NOT fetch when unauthenticated", async () => {
    const { result } = renderHook(() => useFavorites(false));
    // Initial empty state, no fetch.
    expect(result.current.favorites.favorite_player_ids).toEqual([]);
    expect(result.current.favorites.favorite_teams).toEqual([]);
  });

  it("save updates state optimistically and round-trips", async () => {
    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));
    await act(async () => {
      await result.current.save({ favorite_player_ids: ["new"], favorite_teams: ["BUF"] });
    });
    expect(saved).toEqual({ favorite_player_ids: ["new"], favorite_teams: ["BUF"] });
    expect(result.current.favorites.favorite_player_ids).toEqual(["new"]);
  });
});
```

- [ ] **Step 8.7: Implement `useFavorites`**

Create `web/src/hooks/useFavorites.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import { getFavorites, putFavorites } from "@/api/favorites";
import type { FavoritesOut, FavoritesUpdate } from "@/api/types";

const EMPTY: FavoritesOut = { favorite_player_ids: [], favorite_teams: [] };

interface UseFavoritesResult {
  favorites: FavoritesOut;
  loading: boolean;
  error: string | null;
  save: (next: FavoritesUpdate) => Promise<void>;
}

/**
 * Hook for the current user's favorites. Pass `authenticated=true` only when
 * the user is logged in (typically `user !== null` from AuthContext). When
 * unauthenticated, no fetch fires and `favorites` stays the empty default.
 *
 * `save` is optimistic: the local `favorites` state updates immediately and
 * reverts on server error.
 */
export function useFavorites(authenticated: boolean): UseFavoritesResult {
  const [favorites, setFavorites] = useState<FavoritesOut>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authenticated) {
      setFavorites(EMPTY);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getFavorites()
      .then((fav) => {
        if (!cancelled) setFavorites(fav);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message ?? "Failed to load favorites");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated]);

  const save = useCallback(async (next: FavoritesUpdate) => {
    const prev = favorites;
    setFavorites(next);            // optimistic
    setError(null);
    try {
      const persisted = await putFavorites(next);
      setFavorites(persisted);     // accept server's normalized version (dedup, etc.)
    } catch (e) {
      setFavorites(prev);          // revert
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, [favorites]);

  return { favorites, loading, error, save };
}
```

- [ ] **Step 8.8: Run hook tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/hooks/useFavorites.test.tsx 2>&1 | tail -10
```

- [ ] **Step 8.9: Run tsc on touched files**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated" | head -10
```

Should be silent.

- [ ] **Step 8.10: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/api/types.ts web/src/api/favorites.ts web/src/hooks/useFavorites.ts web/src/tests/api/favorites.test.ts web/src/tests/hooks/useFavorites.test.tsx
git commit -m "feat(web): favorites API client + useFavorites hook

Types: FavoritesOut, FavoritesUpdate, PlayerSearchResult.
Client: getFavorites, putFavorites, searchPlayers — pattern matches
existing api/profiles.ts.
Hook: useFavorites(authenticated) fetches on mount when logged in,
no-ops otherwise. save() is optimistic with server-shape acceptance
and revert-on-error.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Frontend — `FavoritesPanel` component

**Files:**
- Create: `web/src/components/FavoritesPanel.tsx`
- Create: `web/src/tests/components/FavoritesPanel.test.tsx`

- [ ] **Step 9.1: Write failing component tests**

Create `web/src/tests/components/FavoritesPanel.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import type { FavoritesOut, PlayerSearchResult } from "@/api/types";

const makeFav = (overrides: Partial<FavoritesOut> = {}): FavoritesOut => ({
  favorite_player_ids: [],
  favorite_teams: [],
  ...overrides,
});

const sampleSearchResults: PlayerSearchResult[] = [
  { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI" },
  { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF" },
];

describe("FavoritesPanel", () => {
  it("renders empty state for both sections", () => {
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
      />
    );
    expect(screen.getByText(/no favorite players yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no favorite teams yet/i)).toBeInTheDocument();
  });

  it("shows count badges", () => {
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: ["1"], favorite_teams: ["KC", "BUF"] })}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
      />
    );
    expect(screen.getByText("1 / 20")).toBeInTheDocument();
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("search input triggers searchPlayers callback", async () => {
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel favorites={makeFav()} onSave={vi.fn()} searchPlayers={search} />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    await waitFor(() => expect(search).toHaveBeenCalledWith("barkley"));
  });

  it("clicking Add invokes onSave with the new player ID", async () => {
    const onSave = vi.fn(async () => {});
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel favorites={makeFav()} onSave={onSave} searchPlayers={search} />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    const addButton = await screen.findByRole("button", { name: /add saquon barkley/i });
    await userEvent.click(addButton);
    expect(onSave).toHaveBeenCalledWith({
      favorite_player_ids: ["1"],
      favorite_teams: [],
    });
  });

  it("at-cap disables Add and shows tooltip text", () => {
    const tooManyPlayers = Array.from({ length: 20 }, (_, i) => String(i));
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: tooManyPlayers })}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => sampleSearchResults)}
      />
    );
    expect(screen.getByText("20 / 20")).toBeInTheDocument();
    expect(screen.getByText(/limit reached/i)).toBeInTheDocument();
  });

  it("team grid renders 32 teams", () => {
    render(
      <FavoritesPanel favorites={makeFav()} onSave={vi.fn()} searchPlayers={vi.fn(async () => [])} />
    );
    expect(screen.getAllByRole("button", { name: /^team-/i })).toHaveLength(32);
  });

  it("toggling a team calls onSave with the team added", async () => {
    const onSave = vi.fn(async () => {});
    render(
      <FavoritesPanel favorites={makeFav()} onSave={onSave} searchPlayers={vi.fn(async () => [])} />
    );
    const kc = screen.getByRole("button", { name: "team-KC" });
    await userEvent.click(kc);
    expect(onSave).toHaveBeenCalledWith({
      favorite_player_ids: [],
      favorite_teams: ["KC"],
    });
  });
});
```

- [ ] **Step 9.2: Run tests — expect failure**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/FavoritesPanel.test.tsx 2>&1 | tail -15
```

- [ ] **Step 9.3: Implement `FavoritesPanel`**

Create `web/src/components/FavoritesPanel.tsx`:

```typescript
import { useEffect, useState } from "react";
import type { FavoritesOut, FavoritesUpdate, PlayerSearchResult } from "@/api/types";

const NFL_TEAMS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB",  "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV",  "MIA", "MIN", "NE",  "NO",  "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF",  "TB",  "TEN", "WAS",
] as const;

const PLAYER_CAP = 20;
const TEAM_CAP = 4;

interface FavoritesPanelProps {
  favorites: FavoritesOut;
  onSave: (next: FavoritesUpdate) => Promise<void>;
  searchPlayers: (q: string) => Promise<PlayerSearchResult[]>;
}

export function FavoritesPanel({ favorites, onSave, searchPlayers }: FavoritesPanelProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    searchPlayers(query.trim()).then((r) => {
      if (!cancelled) setResults(r);
    }).catch(() => {
      if (!cancelled) setResults([]);
    });
    return () => { cancelled = true; };
  }, [query, searchPlayers]);

  const playersAtCap = favorites.favorite_player_ids.length >= PLAYER_CAP;
  const teamsAtCap = favorites.favorite_teams.length >= TEAM_CAP;

  const togglePlayer = (id: string) => {
    const isFav = favorites.favorite_player_ids.includes(id);
    if (isFav) {
      void onSave({
        favorite_player_ids: favorites.favorite_player_ids.filter((x) => x !== id),
        favorite_teams: favorites.favorite_teams,
      });
    } else if (!playersAtCap) {
      void onSave({
        favorite_player_ids: [...favorites.favorite_player_ids, id],
        favorite_teams: favorites.favorite_teams,
      });
    }
  };

  const toggleTeam = (team: string) => {
    const isFav = favorites.favorite_teams.includes(team);
    if (isFav) {
      void onSave({
        favorite_player_ids: favorites.favorite_player_ids,
        favorite_teams: favorites.favorite_teams.filter((t) => t !== team),
      });
    } else if (!teamsAtCap) {
      void onSave({
        favorite_player_ids: favorites.favorite_player_ids,
        favorite_teams: [...favorites.favorite_teams, team],
      });
    }
  };

  return (
    <div className="space-y-6 p-4">
      <section>
        <header className="flex items-center justify-between mb-2">
          <h3 className="font-medium">Favorite Players</h3>
          <span className={`text-xs ${playersAtCap ? "text-amber-600" : "text-muted-foreground"}`}>
            {favorites.favorite_player_ids.length} / {PLAYER_CAP}
          </span>
        </header>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search players…"
          className="w-full border rounded px-3 py-2 text-sm"
        />
        {playersAtCap && (
          <p className="text-xs text-amber-700 mt-1">
            Limit reached ({PLAYER_CAP} players). Remove one to add another.
          </p>
        )}
        <ul className="mt-2 space-y-1">
          {results.length === 0 && favorites.favorite_player_ids.length === 0 && !query && (
            <li className="text-sm text-muted-foreground">No favorite players yet. Search above to add one.</li>
          )}
          {results.map((p) => {
            const isFav = favorites.favorite_player_ids.includes(p.id);
            return (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <span>{p.name} ({p.position}{p.team ? ` · ${p.team}` : ""})</span>
                <button
                  type="button"
                  onClick={() => togglePlayer(p.id)}
                  disabled={!isFav && playersAtCap}
                  aria-label={isFav ? `Remove ${p.name}` : `Add ${p.name}`}
                  className="px-2 py-1 text-xs border rounded"
                >
                  {isFav ? "Remove" : "Add"}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <header className="flex items-center justify-between mb-2">
          <h3 className="font-medium">Favorite Teams</h3>
          <span className={`text-xs ${teamsAtCap ? "text-amber-600" : "text-muted-foreground"}`}>
            {favorites.favorite_teams.length} / {TEAM_CAP}
          </span>
        </header>
        {teamsAtCap && (
          <p className="text-xs text-amber-700 mb-1">
            Limit reached ({TEAM_CAP} teams). Remove one to add another.
          </p>
        )}
        {favorites.favorite_teams.length === 0 && (
          <p className="text-sm text-muted-foreground mb-2">
            No favorite teams yet. Select up to {TEAM_CAP} teams.
          </p>
        )}
        <div className="grid grid-cols-8 gap-2">
          {NFL_TEAMS.map((team) => {
            const isFav = favorites.favorite_teams.includes(team);
            const disabled = !isFav && teamsAtCap;
            return (
              <button
                key={team}
                type="button"
                onClick={() => toggleTeam(team)}
                disabled={disabled}
                aria-label={`team-${team}`}
                aria-pressed={isFav}
                className={`px-2 py-1 text-xs border rounded ${
                  isFav ? "bg-primary text-primary-foreground" : disabled ? "opacity-40" : ""
                }`}
              >
                {team}
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 9.4: Run tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/FavoritesPanel.test.tsx 2>&1 | tail -15
```

7 tests should pass.

- [ ] **Step 9.5: Run tsc**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated" | head -10
```

Should be silent.

- [ ] **Step 9.6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/FavoritesPanel.tsx web/src/tests/components/FavoritesPanel.test.tsx
git commit -m "feat(web): FavoritesPanel component

Two sections: search-driven player list + 32-team grid. Optimistic
add/remove via the onSave callback. Cap indicators on each section
turn amber at the limit; over-cap state disables the Add/Toggle
controls with aria-label and inline copy. Accessible: aria-label on
icon-free actions, aria-pressed on toggleable team tiles, keyboard
reach via standard button elements. Empty states are not blank.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Frontend — `LinkedAccountsDialog` integration

**Files:**
- Modify: `web/src/components/LinkedAccountsDialog.tsx`
- Modify: `web/src/tests/components/LinkedAccountsDialog.test.tsx` (if exists)
- Test: extend or add new test for the Favorites tab visibility

- [ ] **Step 10.1: Write a failing test for the new tab**

Open `web/src/tests/components/LinkedAccountsDialog.test.tsx`. Add (or merge into) tests for the Favorites tab visibility:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";

describe("LinkedAccountsDialog — Favorites tab", () => {
  it("shows the Favorites tab when user is authenticated", () => {
    render(
      <LinkedAccountsDialog
        open
        onOpenChange={vi.fn()}
        user={{ id: "u", email: "a@b" } as any}
        // ... whatever the existing required props are
      />
    );
    expect(screen.getByRole("tab", { name: /favorites/i })).toBeInTheDocument();
  });

  it("does NOT show the Favorites tab when user is anonymous", () => {
    render(
      <LinkedAccountsDialog
        open
        onOpenChange={vi.fn()}
        user={null}
        // ... whatever the existing required props are
      />
    );
    expect(screen.queryByRole("tab", { name: /favorites/i })).not.toBeInTheDocument();
  });
});
```

(Adapt the props to whatever the existing `LinkedAccountsDialog` requires — check it first with `Read`.)

- [ ] **Step 10.2: Run test — expect failures**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/LinkedAccountsDialog.test.tsx 2>&1 | tail -15
```

- [ ] **Step 10.3: Wire the Favorites tab into LinkedAccountsDialog**

Open `web/src/components/LinkedAccountsDialog.tsx`. Inside the dialog, where the existing tabs are rendered (likely a shadcn `<Tabs>` with `<TabsList>` and `<TabsContent>`), add a new tab conditional on `user !== null`:

```tsx
import { useFavorites } from "@/hooks/useFavorites";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import { searchPlayers } from "@/api/favorites";

// inside the component body:
const { favorites, save: saveFavorites } = useFavorites(user !== null);

// inside the <TabsList>, add:
{user !== null && (
  <TabsTrigger value="favorites">Favorites</TabsTrigger>
)}

// inside the <TabsContent> region, add:
{user !== null && (
  <TabsContent value="favorites">
    <FavoritesPanel
      favorites={favorites}
      onSave={saveFavorites}
      searchPlayers={searchPlayers}
    />
  </TabsContent>
)}
```

If the dialog uses a different tab primitive (e.g. role="tablist" custom), match its idiom — the key invariants are: (a) the tab trigger renders only when authenticated, (b) the tab content renders only when authenticated, (c) the panel receives `favorites`, `onSave`, and `searchPlayers` from `useFavorites` + the API client.

- [ ] **Step 10.4: Run tests — expect pass**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run src/tests/components/LinkedAccountsDialog.test.tsx src/tests/components/FavoritesPanel.test.tsx -v 2>&1 | tail -20
```

- [ ] **Step 10.5: Run tsc**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated" | head -10
```

Should be silent.

- [ ] **Step 10.6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/LinkedAccountsDialog.tsx web/src/tests/components/LinkedAccountsDialog.test.tsx
git commit -m "feat(web): Favorites tab in LinkedAccountsDialog

Tab is gated on user !== null (anon users don't see it at all, per the
'auth-gated affordances are absent, not disabled' pattern). useFavorites
hook drives the panel; saving immediately PUTs /favorites.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: Full sweep + PR

- [ ] **Step 11.1: Backend full sweep**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/ -q --ignore=tests/test_sources 2>&1 | tail -5
```

All previous (256 from xFP) + new (count from this plan, expect ~40 net additions) should pass.

- [ ] **Step 11.2: Frontend full sweep**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run 2>&1 | tail -5
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated" | head -10
```

Baseline (157 from xFP) + new tests should all pass; tsc clean.

- [ ] **Step 11.3: Manual flow check**

Even with all tests green, do one manual sanity drive of the flow using `autotiers-flow-fixtures`. Start the dev stack:

```bash
cd /Users/karlkell/Code/AutoTiers && podman compose up
```

Then:

1. Sign up a new user.
2. Open the account dialog. Confirm the Favorites tab is present.
3. Search "barkley" — see Saquon's row. Click Add.
4. Check the rules panel — confirm "Favorites" is enabled in the active profile.
5. Click Generate. Find Saquon in the result — confirm his `rules_applied` includes "Favorites" and his `adjusted_score` is ~5% above where it would be without the rule (eyeball comparison vs an unfavorited similar player).
6. Add 4 teams. Add a 5th — confirm UI blocks.
7. Sign out. Reopen the account dialog. Confirm the Favorites tab is gone.

- [ ] **Step 11.4: Push the branch**

```bash
cd /Users/karlkell/Code/AutoTiers && git push -u origin <branch-name>
```

The pre-push hook checks the PR state. If this is a fresh branch with no PR, it proceeds.

- [ ] **Step 11.5: Open the PR**

```bash
gh pr create --title "feat: favorites for players + teams" --body "$(cat <<'EOF'
## Summary

Implements the design in `docs/superpowers/specs/2026-06-02-favorites-feature-design.md`. Authenticated users can favorite up to 20 individual players and 4 NFL teams from a new tab on the account modal. Favorited entities trigger a single user-tunable "Favorites" rule (MULTIPLIER 1.05 default) during tier generation.

## What's in

- Backend: `UserFavorites` model + Alembic 008; `/api/favorites` GET/PUT (auth-gated, capped, deduped, blank-validated, team-validated); `/api/players?q=` search; `Favorites` builtin rule (MULTIPLIER 1.05); auth-aware `/api/rules` (Favorites hidden from anon); generate-endpoint wire-up via server-side favorites lookup; auto-enable Favorites rule in the active profile on user's first add.
- Frontend: `useFavorites` hook; `FavoritesPanel` component with 32-team grid + player search + cap indicators; new tab in `LinkedAccountsDialog` gated on `user !== null`.

## Math sign-off

Per the spec's mathematician section: cap of 20 players + 4 teams at MULTIPLIER 1.05 produces at most ~100 boosted players. Worst-case per-position VBD tier-break shift is 5–15 pts (15–40% of tier width). No spurious new tiers emerge across simulated cap sizes 20–200. Boost magnitude equals the existing "Follow the Money" rule.

## What's NOT in

Recommendation engine, social sharing, multi-user/league favorites, watchlist, per-profile favorites, import from linked leagues, bulk add, anonymous favorites via localStorage, player photos, "clear all" affordance.

## Test plan
- [x] Backend full sweep — all pass
- [x] Frontend full sweep — all pass
- [x] tsc clean
- [x] Alembic chain advances cleanly to 008
- [ ] Manual flow check passes (see Task 11.3 in the plan)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 11.6: Confirm the PR opened**

The `gh pr create` output includes the PR URL. Note CI run status — diff-coverage gate ≥80% on touched lines.

---

## Self-review

### Spec coverage

- "Auth-gated, account-page feature" → Tasks 3 (CRUD), 5 (search), 6 (rules filtering), 10 (UI gating on `user !== null`).
- "Single Favorites rule, MULTIPLIER 1.05, weight-configurable" → Tasks 4 (auto-enable), 6 (rule entry).
- "Cap 20 players + 4 teams" → Tasks 3 (backend enforcement) and 9 (frontend indicators).
- "Per-user (not per-profile) scope" → Tasks 1 (FK to users), 8 (hook is user-scoped).
- "GET /players?q= endpoint, not generate-result-derived" → Task 5.
- "Server-side favorites lookup in generate, not GenerateRequest" → Task 7.
- "Tab in LinkedAccountsDialog" → Task 10.
- "Backend auto-enable Favorites rule on first add" → Task 4.
- Math: covered in spec, validated, no code change required beyond the cap and multiplier values both encoded as constants.
- Class 2 (empty validation), Class 3 (auth identity), Class 5 (migration), Class 6 (UI inconsistency) all addressed in respective tasks.

### Placeholder scan

No `TBD`, `TODO`, `fill in details`, vague "handle edge cases" instructions, or undefined-function references found. All code blocks are complete. All test inputs hand-computed.

### Type consistency

- `FavoritesOut` / `FavoritesUpdate` — same field names in `web/src/api/types.ts` (Task 8) and `backend/app/schemas/favorites.py` (Task 2).
- `is_favorite: Optional[bool]` — added to `PlayerContext` in Task 6, populated in Task 7 (`is_favorite=is_favorite,`), checked by rule condition `is_favorite == True` in Task 6.5.
- `NFL_TEAMS` — defined in Task 2 (backend, `frozenset`) and Task 9 (frontend, `const array`). Documented duplication acceptable per the file-map rationale.
- `PLAYER_CAP=20`, `TEAM_CAP=4` — backend constants in `favorites_api.py` (Task 3); frontend constants in `FavoritesPanel.tsx` (Task 9). Cap values match.
- `searchPlayers(q)` — defined in `web/src/api/favorites.ts` (Task 8.4), consumed by `FavoritesPanel` props (Task 9), passed in by `LinkedAccountsDialog` (Task 10).

No drift identified.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-favorites-feature.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec → quality) per task, fast iteration. Used successfully on the xFP feature with the same structure.

**2. Inline Execution** — execute tasks in this session via `executing-plans`, batch with checkpoints.

Which approach?
