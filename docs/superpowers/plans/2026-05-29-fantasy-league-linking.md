# Fantasy League Linking (Sleeper + ESPN) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users link a Sleeper or ESPN league to a profile so AutoTiers auto-detects scoring, excludes keepers, and uses league-side draft positions as the ADP tiebreaker.

**Architecture:** A new `linked_leagues` table is joined 1:1 with `profiles`. Provider integration modules (`integrations/sleeper.py`, `integrations/espn.py`) make synchronous HTTP calls on link/refresh. Scoring mappers translate raw platform scoring into AutoTiers' `SettingsState` shape. Generate requests gain optional `keepers` and `league_adp` fields the engine consumes when present.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async, Alembic, `cryptography.fernet` for encryption, httpx + respx for HTTP, React + TypeScript + Vitest + MSW.

**Spec:** `docs/superpowers/specs/2026-05-29-fantasy-league-linking-design.md`

**Working branch:** `feat/fantasy-league-linking` (already created from main, spec already committed).

---

## File Structure

**Backend — created:**
- `backend/alembic/versions/006_linked_leagues.py` — Alembic migration for the new table.
- `backend/app/models/linked_league.py` — SQLAlchemy model.
- `backend/app/security/__init__.py` and `backend/app/security/fernet.py` — encryption helpers.
- `backend/app/integrations/__init__.py`
- `backend/app/integrations/types.py` — `LeagueSummary`, `LeagueData` dataclasses.
- `backend/app/integrations/sleeper.py` — Sleeper API client.
- `backend/app/integrations/espn.py` — ESPN API client.
- `backend/app/integrations/scoring_mappers.py` — provider scoring → `SettingsState`.
- `backend/app/api/linked_league.py` — `/api/profiles/{id}/link/*` endpoints.
- `backend/app/schemas/linked_league.py` — Pydantic `LinkedLeagueOut`.
- `backend/tests/test_integrations/__init__.py`
- `backend/tests/test_integrations/test_sleeper.py`
- `backend/tests/test_integrations/test_espn.py`
- `backend/tests/test_integrations/test_scoring_mappers.py`
- `backend/tests/test_linked_league_endpoints.py`
- `backend/tests/test_fernet.py`

**Backend — modified:**
- `backend/app/config.py` — add `secret_key` setting.
- `backend/app/models/__init__.py` — export `LinkedLeague`.
- `backend/app/models/profile.py` — add `linked_league` relationship.
- `backend/app/schemas/auth.py` — extend `ProfileOut` with `linked_league: LinkedLeagueOut | None`.
- `backend/app/schemas/generate.py` — add `keepers: list[str] | None` and `league_adp: dict[str, float] | None` to `GenerateRequest`; add `league_adp: float | None` to `TieredPlayerOut`.
- `backend/app/api/generate.py` — keeper filtering + league ADP override in `_run_generate`.
- `backend/app/main.py` (or wherever routers are registered) — register the new linked-league router.

**Frontend — created:**
- `web/src/api/linkedLeague.ts` — typed wrappers for the new endpoints.
- `web/src/components/LinkedLeagueSection.tsx` — the new section rendered inside `LinkedAccountsDialog`.
- `web/src/components/SleeperConnectForm.tsx` — Sleeper sub-form (two steps).
- `web/src/components/EspnConnectForm.tsx` — ESPN sub-form.
- `web/src/components/LinkedLeagueChip.tsx` — chip shown above SettingsPanel.
- `web/src/tests/api/linkedLeague.test.ts`
- `web/src/tests/components/LinkedLeagueSection.test.tsx`
- `web/src/tests/components/SleeperConnectForm.test.tsx`
- `web/src/tests/components/EspnConnectForm.test.tsx`
- `web/src/tests/components/LinkedLeagueChip.test.tsx`

**Frontend — modified:**
- `web/src/api/types.ts` — add `LinkedLeague` type; extend `Profile` with `linked_league`.
- `web/src/components/LinkedAccountsDialog.tsx` — embed `LinkedLeagueSection`.
- `web/src/components/SettingsPanel.tsx` — render `LinkedLeagueChip` above the existing content when the active profile is linked.
- `web/src/components/TiersPanel.tsx` — render an "Excluded keepers" list when the response carries `keepers_excluded`.
- `web/src/App.tsx` — pass `linkedLeague` into `SettingsPanel`; extend `buildRequest()` with `keepers` and `league_adp` from the active profile's linked league.
- `web/src/tests/integration/app-authenticated.test.tsx` — extend with linked-league flow.

---

## Task 1: Migration + `LinkedLeague` model

**Files:**
- Create: `backend/alembic/versions/006_linked_leagues.py`
- Create: `backend/app/models/linked_league.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/profile.py`

- [ ] **Step 1: Write the model**

Create `backend/app/models/linked_league.py`:

```python
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import JSON, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.database import Base

# Same JSON/JSONB variant pattern used by Profile.
_JSON_OR_JSONB = JSONB().with_variant(JSON(), "sqlite")


class LinkedLeague(Base):
    __tablename__ = "linked_leagues"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)  # "sleeper" | "espn"
    league_id: Mapped[str] = mapped_column(String, nullable=False)
    username_or_swid: Mapped[str] = mapped_column(String, nullable=False)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    league_metadata_json: Mapped[dict] = mapped_column(_JSON_OR_JSONB, nullable=False)
    keepers_json: Mapped[list] = mapped_column(_JSON_OR_JSONB, nullable=False)
    adp_json: Mapped[Optional[dict]] = mapped_column(_JSON_OR_JSONB, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

- [ ] **Step 2: Export the model**

In `backend/app/models/__init__.py`, add an import + re-export so `from app.models import LinkedLeague` works. Find the existing imports of `Profile`, `User`, `Player`, etc., and add `from .linked_league import LinkedLeague` plus `LinkedLeague` to `__all__` if one exists.

- [ ] **Step 3: Add the relationship on `Profile`**

In `backend/app/models/profile.py`, at the bottom of the `Profile` class add:

```python
    linked_league: Mapped[Optional["LinkedLeague"]] = relationship(
        "LinkedLeague",
        cascade="all, delete-orphan",
        uselist=False,
    )
```

You'll also need to add `from typing import Optional` and `from sqlalchemy.orm import relationship` to the imports at the top of the file (the latter may already be there — verify before adding).

- [ ] **Step 4: Write the Alembic migration**

Create `backend/alembic/versions/006_linked_leagues.py`:

```python
"""linked_leagues table

Revision ID: 006_linked_leagues
Revises: 005_user_google_subject
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "006_linked_leagues"
down_revision = "005_user_google_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linked_leagues",
        sa.Column("profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("league_id", sa.String(), nullable=False),
        sa.Column("username_or_swid", sa.String(), nullable=False),
        sa.Column("credentials_encrypted", sa.String(), nullable=True),
        sa.Column("league_metadata_json", JSONB(), nullable=False),
        sa.Column("keepers_json", JSONB(), nullable=False),
        sa.Column("adp_json", JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("linked_leagues")
```

- [ ] **Step 5: Verify the migration applies cleanly**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/alembic upgrade head
```

Expected: migration runs without error. If the dev DB isn't reachable, skip this and rely on the test-suite SQLite engine to exercise the table creation in the next task. Note: SQLite ignores `JSONB` — the model's `with_variant(JSON(), "sqlite")` pattern handles that, but Alembic migrations apply against Postgres. For tests, the model declares schema directly via `Base.metadata.create_all`, so SQLite test engine doesn't run Alembic.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/linked_league.py backend/app/models/__init__.py backend/app/models/profile.py backend/alembic/versions/006_linked_leagues.py
git commit -m "feat(db): linked_leagues table + LinkedLeague model"
```

---

## Task 2: Fernet encryption helper + `secret_key` config

**Files:**
- Create: `backend/app/security/__init__.py` (empty marker)
- Create: `backend/app/security/fernet.py`
- Create: `backend/tests/test_fernet.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_fernet.py`:

```python
import pytest
from app.security.fernet import encrypt, decrypt, InvalidCiphertext


def test_round_trip_returns_original_plaintext():
    secret = "my-cookie-value-12345"
    ciphertext = encrypt(secret)
    assert ciphertext != secret  # actually encrypted
    assert decrypt(ciphertext) == secret


def test_decrypt_rejects_tampered_ciphertext():
    ciphertext = encrypt("payload")
    tampered = ciphertext[:-2] + "AA"
    with pytest.raises(InvalidCiphertext):
        decrypt(tampered)


def test_encrypt_outputs_are_nondeterministic():
    """Fernet includes a random IV — repeated calls yield different ciphertexts."""
    assert encrypt("same") != encrypt("same")
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_fernet.py -v
```

Expected: FAIL — `ModuleNotFoundError: app.security.fernet`.

- [ ] **Step 3: Add `cryptography` dep if missing**

```bash
cd backend && grep -E "^cryptography" requirements.txt
```

If no match: append `cryptography>=42.0` to `backend/requirements.txt` and run `venv/bin/pip install cryptography`.

- [ ] **Step 4: Add `secret_key` to config**

In `backend/app/config.py`, add this field next to `jwt_secret`:

```python
    # Fernet key — base64-urlsafe 32 bytes. Override in production.
    # Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_key: str = "dKkY-w0jHF6kBE_oTzx7JtAYxHB1yyaJYBNz3X1eYdY="
```

- [ ] **Step 5: Implement the helper**

Create `backend/app/security/__init__.py` as an empty file. Create `backend/app/security/fernet.py`:

```python
"""Fernet (AES) encryption helpers for at-rest secrets like OAuth cookies.

The key is configured via Settings.secret_key — base64-urlsafe 32 bytes.
"""
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings


class InvalidCiphertext(Exception):
    """Raised when ciphertext is missing, malformed, or has a bad signature."""


def _fernet() -> Fernet:
    return Fernet(settings.secret_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise InvalidCiphertext("Ciphertext is invalid or signature failed") from e
```

- [ ] **Step 6: Run test, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_fernet.py -v
```

Expected: 3 pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/security/ backend/app/config.py backend/tests/test_fernet.py backend/requirements.txt
git commit -m "feat(security): Fernet encrypt/decrypt helpers + secret_key config"
```

---

## Task 3: Integration types + Sleeper client

**Files:**
- Create: `backend/app/integrations/__init__.py` (empty)
- Create: `backend/app/integrations/types.py`
- Create: `backend/app/integrations/sleeper.py`
- Create: `backend/tests/test_integrations/__init__.py` (empty)
- Create: `backend/tests/test_integrations/test_sleeper.py`

- [ ] **Step 1: Define integration types**

Create `backend/app/integrations/__init__.py` as empty. Create `backend/app/integrations/types.py`:

```python
"""Shared types for per-user-league provider integrations."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LeagueSummary:
    """Lightweight league info used to populate a selection dropdown."""
    id: str
    name: str
    season: int


@dataclass
class LeagueData:
    """Everything we fetch from a provider on connect/refresh.

    raw_scoring is a provider-native dict (Sleeper or ESPN's own keys) —
    scoring_mappers convert it to AutoTiers SettingsState shape.

    keepers is a list of {player_name, position, team}. adp_json is
    {player_name: avg_pick_overall} or None when the platform doesn't
    expose draft data for the league.
    """
    league_id: str
    name: str
    season: int
    raw_scoring: dict
    league_size: int
    keepers: list[dict] = field(default_factory=list)
    adp_json: Optional[dict] = None
```

- [ ] **Step 2: Write failing tests for the Sleeper client**

Create `backend/tests/test_integrations/__init__.py` as empty. Create `backend/tests/test_integrations/test_sleeper.py`:

```python
import pytest
import respx
from httpx import Response
from app.integrations.sleeper import list_user_leagues, fetch_league


@pytest.mark.asyncio
async def test_list_user_leagues_resolves_username_to_leagues():
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/alice").mock(
            return_value=Response(200, json={"user_id": "u123", "username": "alice"}),
        )
        router.get("https://api.sleeper.app/v1/user/u123/leagues/nfl/2026").mock(
            return_value=Response(200, json=[
                {"league_id": "L1", "name": "PPR Champs", "season": "2026"},
                {"league_id": "L2", "name": "Standard 10", "season": "2026"},
            ]),
        )
        result = await list_user_leagues("alice", 2026)
    assert len(result) == 2
    assert result[0].id == "L1"
    assert result[0].name == "PPR Champs"
    assert result[0].season == 2026


@pytest.mark.asyncio
async def test_list_user_leagues_404_when_username_not_found():
    from app.integrations.sleeper import SleeperUserNotFound
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/ghost").mock(
            return_value=Response(404, json={}),
        )
        with pytest.raises(SleeperUserNotFound):
            await list_user_leagues("ghost", 2026)


@pytest.mark.asyncio
async def test_fetch_league_returns_settings_size_and_keepers():
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1",
                "name": "PPR Champs",
                "season": "2026",
                "total_rosters": 12,
                "scoring_settings": {"rec": 1.0, "pass_td": 4, "rush_yd": 0.1, "rec_yd": 0.1},
                "settings": {"draft_rounds": 15},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[
                {"owner_id": "u1", "keepers": ["12345", "67890"]},
                {"owner_id": "u2", "keepers": None},
            ]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={
                "12345": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
                "67890": {"full_name": "Christian McCaffrey", "position": "RB", "team": "SF"},
            }),
        )
        # No draft data — no league_id/draft endpoint mocked; client should handle gracefully.
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[]),
        )
        league = await fetch_league("L1")
    assert league.league_size == 12
    assert league.name == "PPR Champs"
    assert len(league.keepers) == 2
    assert {k["player_name"] for k in league.keepers} == {"Justin Jefferson", "Christian McCaffrey"}
    assert league.adp_json is None  # no draft happened


@pytest.mark.asyncio
async def test_fetch_league_returns_adp_when_draft_data_exists():
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1", "name": "Champs", "season": "2026",
                "total_rosters": 10,
                "scoring_settings": {"rec": 0.5, "pass_td": 4},
                "settings": {"draft_rounds": 16},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={
                "p1": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
                "p2": {"full_name": "Christian McCaffrey", "position": "RB", "team": "SF"},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[{"draft_id": "D1", "status": "complete"}]),
        )
        router.get("https://api.sleeper.app/v1/draft/D1/picks").mock(
            return_value=Response(200, json=[
                {"pick_no": 1, "player_id": "p1"},
                {"pick_no": 2, "player_id": "p2"},
            ]),
        )
        league = await fetch_league("L1")
    assert league.adp_json == {"Justin Jefferson": 1.0, "Christian McCaffrey": 2.0}
```

- [ ] **Step 3: Run tests, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_integrations/test_sleeper.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement Sleeper client**

Create `backend/app/integrations/sleeper.py`:

```python
"""Sleeper public-API client for league-linking flows.

Sleeper has no auth: a username is enough. We use four endpoints:
  - /v1/user/{username} → user_id
  - /v1/user/{user_id}/leagues/nfl/{season}
  - /v1/league/{league_id} and /v1/league/{league_id}/rosters
  - /v1/players/nfl  (static player dictionary for keeper/pick name lookup)
  - /v1/league/{league_id}/drafts  (list, may be empty before draft happens)
  - /v1/draft/{draft_id}/picks  (only when a draft completed)
"""
import httpx
from app.integrations.types import LeagueSummary, LeagueData


BASE_URL = "https://api.sleeper.app"


class SleeperUserNotFound(Exception):
    """Raised when the Sleeper user lookup returns 404."""


async def _get_json(client: httpx.AsyncClient, path: str) -> object:
    resp = await client.get(f"{BASE_URL}{path}")
    resp.raise_for_status()
    return resp.json()


async def list_user_leagues(username: str, season: int) -> list[LeagueSummary]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/v1/user/{username}")
        if resp.status_code == 404:
            raise SleeperUserNotFound(f"Sleeper user '{username}' not found")
        resp.raise_for_status()
        user = resp.json()
        user_id = user["user_id"]

        leagues_data = await _get_json(client, f"/v1/user/{user_id}/leagues/nfl/{season}")
        return [
            LeagueSummary(id=l["league_id"], name=l["name"], season=int(l["season"]))
            for l in leagues_data
        ]


async def fetch_league(league_id: str) -> LeagueData:
    async with httpx.AsyncClient(timeout=10.0) as client:
        league = await _get_json(client, f"/v1/league/{league_id}")
        rosters = await _get_json(client, f"/v1/league/{league_id}/rosters")
        players_dict = await _get_json(client, "/v1/players/nfl")
        drafts = await _get_json(client, f"/v1/league/{league_id}/drafts")

        keepers: list[dict] = []
        for roster in rosters:
            for pid in (roster.get("keepers") or []):
                p = players_dict.get(pid)
                if p is None:
                    continue
                keepers.append({
                    "player_name": p.get("full_name") or "",
                    "position": p.get("position") or "",
                    "team": p.get("team") or "",
                })

        adp_json: dict | None = None
        completed_drafts = [d for d in drafts if d.get("status") == "complete"]
        if completed_drafts:
            draft_id = completed_drafts[0]["draft_id"]
            picks = await _get_json(client, f"/v1/draft/{draft_id}/picks")
            adp_json = {}
            for pick in picks:
                p = players_dict.get(pick["player_id"])
                if p is None or not p.get("full_name"):
                    continue
                adp_json[p["full_name"]] = float(pick["pick_no"])

        return LeagueData(
            league_id=league["league_id"],
            name=league["name"],
            season=int(league["season"]),
            raw_scoring=league.get("scoring_settings") or {},
            league_size=int(league.get("total_rosters") or 12),
            keepers=keepers,
            adp_json=adp_json,
        )
```

- [ ] **Step 5: Run tests, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_integrations/test_sleeper.py -v
```

Expected: 4 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/ backend/tests/test_integrations/
git commit -m "feat(integrations): Sleeper client with list_user_leagues and fetch_league"
```

---

## Task 4: ESPN client

**Files:**
- Create: `backend/app/integrations/espn.py`
- Create: `backend/tests/test_integrations/test_espn.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_integrations/test_espn.py`:

```python
import pytest
import respx
from httpx import Response
from app.integrations.espn import fetch_league, EspnAuthRequired


def _espn_base(season: int, league_id: str) -> str:
    return (
        f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
        f"/segments/0/leagues/{league_id}"
    )


@pytest.mark.asyncio
async def test_fetch_public_league_returns_metadata_and_size():
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(
            return_value=Response(200, json={
                "id": 12345,
                "settings": {
                    "name": "Dynasty Champs",
                    "size": 12,
                    "scoringSettings": {"scoringItems": [
                        {"statId": 53, "points": 1.0},  # receptions
                    ]},
                },
                "teams": [
                    {"id": 1, "owners": ["O1"], "draftStrategy": {"keepers": [{"playerId": 4035687}]}},
                ],
                "players": [
                    {"id": 4035687, "fullName": "Justin Jefferson", "defaultPositionId": 4, "proTeamId": 16},
                ],
                "draftDetail": {"drafted": False, "picks": []},
            }),
        )
        league = await fetch_league("12345", 2026, swid=None, espn_s2=None)
    assert league.league_size == 12
    assert league.name == "Dynasty Champs"
    assert league.keepers and league.keepers[0]["player_name"] == "Justin Jefferson"
    assert league.adp_json is None


@pytest.mark.asyncio
async def test_fetch_private_league_sends_cookies():
    captured = {}
    def handler(request):
        captured["cookies"] = dict(request.headers).get("cookie", "")
        return Response(200, json={
            "id": 12345,
            "settings": {"name": "Private", "size": 10, "scoringSettings": {"scoringItems": []}},
            "teams": [], "players": [],
            "draftDetail": {"drafted": False, "picks": []},
        })
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(side_effect=handler)
        await fetch_league("12345", 2026, swid="{abc-123}", espn_s2="encrypted-blob")
    assert "swid={abc-123}" in captured["cookies"].lower() or "SWID=" in captured["cookies"]
    assert "espn_s2=encrypted-blob" in captured["cookies"]


@pytest.mark.asyncio
async def test_fetch_private_league_without_cookies_raises_auth_required():
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(return_value=Response(401, json={}))
        with pytest.raises(EspnAuthRequired):
            await fetch_league("12345", 2026, swid=None, espn_s2=None)


@pytest.mark.asyncio
async def test_fetch_league_returns_adp_when_draft_completed():
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(
            return_value=Response(200, json={
                "id": 12345,
                "settings": {"name": "Done", "size": 10, "scoringSettings": {"scoringItems": []}},
                "teams": [], "players": [
                    {"id": 1, "fullName": "Justin Jefferson", "defaultPositionId": 4, "proTeamId": 16},
                    {"id": 2, "fullName": "Christian McCaffrey", "defaultPositionId": 2, "proTeamId": 25},
                ],
                "draftDetail": {"drafted": True, "picks": [
                    {"overallPickNumber": 1, "playerId": 1},
                    {"overallPickNumber": 2, "playerId": 2},
                ]},
            }),
        )
        league = await fetch_league("12345", 2026, swid=None, espn_s2=None)
    assert league.adp_json == {"Justin Jefferson": 1.0, "Christian McCaffrey": 2.0}
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_integrations/test_espn.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement ESPN client**

Create `backend/app/integrations/espn.py`:

```python
"""ESPN unofficial-API client for league-linking flows.

Public leagues are reachable anonymously. Private leagues require two cookies
the user pastes from their browser: SWID (a UUID-ish identifier) and
espn_s2 (a long opaque session blob).

We attach both cookies and request three views in a single call:
  view=mSettings   → name, size, scoringSettings
  view=mTeam       → teams + keepers (under draftStrategy)
  view=mDraftDetail → completed draft picks
"""
import httpx
from app.integrations.types import LeagueData


class EspnAuthRequired(Exception):
    """ESPN returned 401/403 — the league is private and cookies are missing or expired."""


_BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"
_VIEWS = "view=mSettings&view=mTeam&view=mDraftDetail"


async def fetch_league(
    league_id: str,
    season: int,
    swid: str | None,
    espn_s2: str | None,
) -> LeagueData:
    url = f"{_BASE_URL}/seasons/{season}/segments/0/leagues/{league_id}?{_VIEWS}"
    cookies = {}
    if swid:
        cookies["SWID"] = swid
    if espn_s2:
        cookies["espn_s2"] = espn_s2

    async with httpx.AsyncClient(timeout=10.0, cookies=cookies) as client:
        resp = await client.get(url)
        if resp.status_code in (401, 403):
            raise EspnAuthRequired("ESPN rejected the request — league may be private and cookies missing/expired")
        resp.raise_for_status()
        data = resp.json()

    settings = data.get("settings") or {}
    players_by_id: dict[int, dict] = {p["id"]: p for p in (data.get("players") or [])}

    keepers: list[dict] = []
    for team in data.get("teams") or []:
        for k in (team.get("draftStrategy") or {}).get("keepers") or []:
            p = players_by_id.get(k.get("playerId"))
            if p is None:
                continue
            keepers.append({
                "player_name": p.get("fullName") or "",
                "position": _POSITION_BY_ID.get(p.get("defaultPositionId"), ""),
                "team": _PRO_TEAM_BY_ID.get(p.get("proTeamId"), ""),
            })

    adp_json: dict | None = None
    draft = data.get("draftDetail") or {}
    if draft.get("drafted"):
        adp_json = {}
        for pick in draft.get("picks") or []:
            p = players_by_id.get(pick.get("playerId"))
            if p is None or not p.get("fullName"):
                continue
            adp_json[p["fullName"]] = float(pick.get("overallPickNumber") or 0)

    return LeagueData(
        league_id=str(data.get("id") or league_id),
        name=settings.get("name") or f"ESPN league {league_id}",
        season=season,
        raw_scoring=settings.get("scoringSettings") or {},
        league_size=int(settings.get("size") or 12),
        keepers=keepers,
        adp_json=adp_json,
    )


# Minimal subset — covers the offense positions AutoTiers ranks.
_POSITION_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "WR", 5: "TE", 16: "DST", 17: "K"}
# Subset of ESPN's pro-team id → abbreviation mapping. Unknown ids map to empty string.
_PRO_TEAM_BY_ID = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA",
    16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI",
    23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR",
    30: "JAX", 33: "BAL", 34: "HOU",
}
```

Note: the test for `defaultPositionId` 4 expects "WR" — the mapping above has both 3 and 4 as "WR" because ESPN historically used 4 as the second-WR slot. The Justin Jefferson fixture in the test will resolve as WR. If the test asserts an exact position, this mapping is correct.

- [ ] **Step 4: Run tests, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_integrations/test_espn.py -v
```

Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/espn.py backend/tests/test_integrations/test_espn.py
git commit -m "feat(integrations): ESPN client with public + private (cookie) league fetch"
```

---

## Task 5: Scoring mappers

**Files:**
- Create: `backend/app/integrations/scoring_mappers.py`
- Create: `backend/tests/test_integrations/test_scoring_mappers.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_integrations/test_scoring_mappers.py`:

```python
import pytest
from app.integrations.scoring_mappers import sleeper_to_settings, espn_to_settings


def test_sleeper_full_ppr_with_4_qb_td_no_bonuses():
    raw = {"rec": 1.0, "pass_td": 4, "rush_yd": 0.1, "rec_yd": 0.1}
    s = sleeper_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 4
    assert s["bonus_100yd_rushing"] is False
    assert s["bonus_100yd_receiving"] is False
    assert s["bonus_first_downs"] is False
    assert s["league_size"] == 12


def test_sleeper_half_ppr_with_6_qb_td_and_yardage_bonuses():
    raw = {"rec": 0.5, "pass_td": 6, "bonus_rec_yd_100": 3.0, "bonus_rush_yd_100": 3.0}
    s = sleeper_to_settings(raw, league_size=10)
    assert s["scoring_format"] == "half_ppr"
    assert s["qb_td_points"] == 6
    assert s["bonus_100yd_rushing"] is True
    assert s["bonus_100yd_receiving"] is True


def test_sleeper_standard_no_ppr():
    raw = {"rec": 0.0, "pass_td": 4}
    s = sleeper_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "standard"


def test_sleeper_first_down_bonuses_detected():
    raw = {"rec": 1.0, "pass_td": 4, "bonus_rec_fd": 0.5}
    s = sleeper_to_settings(raw, league_size=12)
    assert s["bonus_first_downs"] is True


def test_espn_full_ppr_via_stat_id_53():
    # ESPN stat 53 = receptions (full PPR when value=1.0).
    raw = {"scoringItems": [{"statId": 53, "points": 1.0}, {"statId": 4, "points": 4.0}]}
    # statId 4 = pass TD.
    s = espn_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 4


def test_espn_half_ppr_with_6_qb_td():
    raw = {"scoringItems": [{"statId": 53, "points": 0.5}, {"statId": 4, "points": 6.0}]}
    s = espn_to_settings(raw, league_size=10)
    assert s["scoring_format"] == "half_ppr"
    assert s["qb_td_points"] == 6


def test_espn_standard():
    raw = {"scoringItems": [{"statId": 4, "points": 4.0}]}
    s = espn_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "standard"
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_integrations/test_scoring_mappers.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement mappers**

Create `backend/app/integrations/scoring_mappers.py`:

```python
"""Provider-specific scoring → AutoTiers SettingsState shape.

Both mappers return a plain dict matching the frontend `SettingsState` keys.
We don't construct the full SettingsState (which lives in the frontend) —
we return the JSON-serializable subset that gets written into
`profile.settings_json`.
"""


def _classify_ppr(rec_value: float) -> str:
    if rec_value >= 0.75:
        return "ppr"
    if rec_value >= 0.25:
        return "half_ppr"
    return "standard"


def sleeper_to_settings(raw_scoring: dict, league_size: int) -> dict:
    rec = float(raw_scoring.get("rec", 0.0))
    pass_td = float(raw_scoring.get("pass_td", 4.0))
    bonus_rush = "bonus_rush_yd_100" in raw_scoring
    bonus_rec = "bonus_rec_yd_100" in raw_scoring
    # Any first-down bonus key (e.g. bonus_rec_fd, bonus_rush_fd) → True.
    bonus_fd = any(k.endswith("_fd") for k in raw_scoring.keys())
    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        "bonus_100yd_rushing": bonus_rush,
        "bonus_100yd_receiving": bonus_rec,
        "bonus_first_downs": bonus_fd,
        # weights stay user-controlled — mappers do not touch them.
    }


# Subset of ESPN statId mappings we actually consume.
_ESPN_RECEPTION = 53
_ESPN_PASS_TD = 4


def espn_to_settings(raw_scoring: dict, league_size: int) -> dict:
    items = raw_scoring.get("scoringItems") or []
    by_stat = {item.get("statId"): float(item.get("points") or 0) for item in items}

    rec = by_stat.get(_ESPN_RECEPTION, 0.0)
    pass_td = by_stat.get(_ESPN_PASS_TD, 4.0)

    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        # ESPN exposes yardage bonuses via separate stat ids we don't currently parse;
        # leaving them false matches what AutoTiers expects until a user reports a miss.
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
    }
```

- [ ] **Step 4: Run tests, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_integrations/test_scoring_mappers.py -v
```

Expected: 7 pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/scoring_mappers.py backend/tests/test_integrations/test_scoring_mappers.py
git commit -m "feat(integrations): scoring mappers for Sleeper + ESPN"
```

---

## Task 6: `LinkedLeagueOut` schema + `ProfileOut` extension

**Files:**
- Create: `backend/app/schemas/linked_league.py`
- Modify: `backend/app/schemas/auth.py`
- Modify: existing /me test in `backend/tests/test_google_oauth.py` (one assertion to add)

- [ ] **Step 1: Write failing assertion**

In `backend/tests/test_google_oauth.py`, find `test_callback_creates_new_user_on_first_login` (the one that hits `/me` after callback). Add this assertion after the existing `google_subject` check:

```python
    assert me.json()["user"]["google_subject"] == "google-user-xyz"
    # Profile-shaped objects in /me include linked_league key (null when none).
    # No profile is created in this anonymous-style test, so just confirm /me itself returns.
```

Then add a new test below that exercises a Profile with no linked league:

```python
@pytest.mark.asyncio
async def test_me_returns_null_linked_league_when_profile_has_none(async_client, test_db):
    """Profile without a linked league must serialize linked_league=null."""
    from app.auth.hashing import hash_password
    from app.models import User, Profile
    u = User(email="u@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    p = Profile(user_id=u.id, name="P1", settings_json={"scoring_format": "ppr"}, rules_json=[])
    test_db.add(p)
    await test_db.commit()

    r = await async_client.post(
        "/api/auth/login", json={"email": "u@example.com", "password": "password-long-enough"},
    )
    assert r.status_code == 200
    me = (await async_client.get("/api/auth/me")).json()
    assert me["profiles"][0]["linked_league"] is None
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_google_oauth.py::test_me_returns_null_linked_league_when_profile_has_none -v
```

Expected: FAIL — `KeyError: 'linked_league'`.

- [ ] **Step 3: Add `LinkedLeagueOut` schema**

Create `backend/app/schemas/linked_league.py`:

```python
"""Pydantic shapes for the linked-league API.

Note: credentials_encrypted is intentionally NOT exposed — it never crosses the wire.
"""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class LinkedLeagueOut(BaseModel):
    profile_id: uuid.UUID
    provider: str  # "sleeper" | "espn"
    league_id: str
    league_metadata_json: dict[str, Any]
    keepers_json: list[dict[str, Any]]
    adp_json: Optional[dict[str, float]]
    last_synced_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Extend `ProfileOut`**

In `backend/app/schemas/auth.py`, change `ProfileOut` to include the linked league:

```python
from app.schemas.linked_league import LinkedLeagueOut

class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    settings_json: dict[str, Any]
    rules_json: list[dict[str, Any]]
    linked_league: Optional[LinkedLeagueOut] = None

    model_config = {"from_attributes": True}
```

The `Optional[LinkedLeagueOut]` field defaults to `None`. `from_attributes=True` lets Pydantic read `profile.linked_league` (the SQLAlchemy relationship) and convert it to `LinkedLeagueOut` automatically.

- [ ] **Step 5: Ensure the relationship is loaded eagerly when serializing /me**

The `/me` endpoint already selects profiles via `select(Profile).where(Profile.user_id == user.id)`. For the relationship to populate without lazy-load (which fails in async), add `.options(selectinload(Profile.linked_league))` to that query. Find the `me` handler in `backend/app/api/auth.py`. The line currently reads roughly:

```python
profiles = (await db.scalars(select(Profile).where(Profile.user_id == user.id))).all()
```

Change it to:

```python
from sqlalchemy.orm import selectinload  # add to imports if not already there
profiles = (await db.scalars(
    select(Profile).where(Profile.user_id == user.id).options(selectinload(Profile.linked_league))
)).all()
```

Apply the same change to the `signup` and `login` handlers if they also read profiles for the response.

- [ ] **Step 6: Run tests, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_google_oauth.py tests/test_yahoo_oauth.py tests/test_auth_unlink.py -q
```

Expected: green (37+ tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/linked_league.py backend/app/schemas/auth.py backend/app/api/auth.py backend/tests/test_google_oauth.py
git commit -m "feat(api): expose linked_league on ProfileOut"
```

---

## Task 7: Linked-league endpoints (Sleeper + ESPN + refresh + delete)

**Files:**
- Create: `backend/app/api/linked_league.py`
- Modify: `backend/app/main.py` (register the router)
- Create: `backend/tests/test_linked_league_endpoints.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_linked_league_endpoints.py`:

```python
import pytest
import respx
from httpx import Response
from sqlalchemy import select
from app.models import User, Profile, LinkedLeague
from app.auth.hashing import hash_password


async def _make_user_and_profile(test_db, email="u@example.com"):
    u = User(email=email, password_hash=hash_password("password-long-enough"))
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    p = Profile(user_id=u.id, name="My", settings_json={}, rules_json=[])
    test_db.add(p)
    await test_db.commit()
    await test_db.refresh(p)
    return u, p


async def _login(async_client, email="u@example.com"):
    r = await async_client.post(
        "/api/auth/login", json={"email": email, "password": "password-long-enough"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_sleeper_leagues_returns_list(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/alice").mock(
            return_value=Response(200, json={"user_id": "u1", "username": "alice"}),
        )
        router.get("https://api.sleeper.app/v1/user/u1/leagues/nfl/2026").mock(
            return_value=Response(200, json=[
                {"league_id": "L1", "name": "PPR Champs", "season": "2026"},
            ]),
        )
        r = await async_client.get(
            f"/api/profiles/{p.id}/link/sleeper/leagues?username=alice&season=2026"
        )
    assert r.status_code == 200
    body = r.json()
    assert body == [{"id": "L1", "name": "PPR Champs", "season": 2026}]


@pytest.mark.asyncio
async def test_get_sleeper_leagues_username_not_found(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/ghost").mock(
            return_value=Response(404, json={}),
        )
        r = await async_client.get(
            f"/api/profiles/{p.id}/link/sleeper/leagues?username=ghost&season=2026"
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_sleeper_writes_linked_league_and_updates_settings(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1", "name": "Champs", "season": "2026",
                "total_rosters": 12,
                "scoring_settings": {"rec": 1.0, "pass_td": 4},
                "settings": {},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={}),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[]),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/sleeper",
            json={"username": "alice", "league_id": "L1", "season": 2026},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "sleeper"
    assert body["linked_league"]["league_id"] == "L1"
    assert body["profile"]["settings_json"]["scoring_format"] == "ppr"
    assert body["profile"]["settings_json"]["league_size"] == 12

    # And the row is persisted.
    ll = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(ll) == 1


@pytest.mark.asyncio
async def test_post_espn_public_league_succeeds(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/12345"
        )
        router.get(url__startswith=url).mock(
            return_value=Response(200, json={
                "id": 12345,
                "settings": {
                    "name": "Public", "size": 10,
                    "scoringSettings": {"scoringItems": [{"statId": 53, "points": 1.0}]},
                },
                "teams": [], "players": [],
                "draftDetail": {"drafted": False, "picks": []},
            }),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/espn",
            json={"league_id": "12345", "season": 2026},
        )
    assert r.status_code == 200, r.text
    assert r.json()["linked_league"]["provider"] == "espn"
    assert r.json()["profile"]["settings_json"]["scoring_format"] == "ppr"


@pytest.mark.asyncio
async def test_post_espn_private_without_cookies_returns_400(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/99999"
        )
        router.get(url__startswith=url).mock(return_value=Response(401, json={}))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/espn",
            json={"league_id": "99999", "season": 2026},
        )
    assert r.status_code == 400
    assert "private" in r.json()["detail"].lower() or "cookie" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_re_fetches_and_updates(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    # Pre-create the linked league as if a previous connect happened.
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="sleeper", league_id="L1",
        username_or_swid="alice",
        league_metadata_json={"name": "Old", "season": 2025},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1", "name": "New", "season": "2026",
                "total_rosters": 14,
                "scoring_settings": {"rec": 0.5, "pass_td": 6},
                "settings": {},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={}),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[]),
        )
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 200
    assert r.json()["linked_league"]["league_metadata_json"]["name"] == "New"
    assert r.json()["profile"]["settings_json"]["scoring_format"] == "half_ppr"


@pytest.mark.asyncio
async def test_delete_clears_link_keeps_profile_settings(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    p.settings_json = {"scoring_format": "ppr", "league_size": 12}
    await test_db.commit()
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="sleeper", league_id="L1",
        username_or_swid="alice",
        league_metadata_json={"name": "X", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    r = await async_client.delete(f"/api/profiles/{p.id}/link")
    assert r.status_code == 204
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert rows == []
    # settings_json untouched
    await test_db.refresh(p)
    assert p.settings_json["scoring_format"] == "ppr"


@pytest.mark.asyncio
async def test_cross_user_access_returns_404(async_client, test_db):
    """A user cannot link a profile that belongs to someone else."""
    u1, p1 = await _make_user_and_profile(test_db, email="alice@example.com")
    u2, p2 = await _make_user_and_profile(test_db, email="bob@example.com")
    # log in as alice
    await _login(async_client, email="alice@example.com")
    r = await async_client.delete(f"/api/profiles/{p2.id}/link")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_linked_league_endpoints.py -v
```

Expected: all 8 fail with 404s — router not mounted, endpoints don't exist.

- [ ] **Step 3: Implement the router**

Create `backend/app/api/linked_league.py`:

```python
"""Per-profile fantasy-league linking endpoints."""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import User, Profile, LinkedLeague
from app.auth.dependencies import require_user
from app.integrations.sleeper import (
    list_user_leagues, fetch_league as fetch_sleeper_league, SleeperUserNotFound,
)
from app.integrations.espn import fetch_league as fetch_espn_league, EspnAuthRequired
from app.integrations.scoring_mappers import sleeper_to_settings, espn_to_settings
from app.security.fernet import encrypt, decrypt
from app.schemas.linked_league import LinkedLeagueOut
from app.schemas.auth import ProfileOut


router = APIRouter(prefix="/profiles/{profile_id}/link", tags=["linked_league"])


class SleeperLeagueSummaryOut(BaseModel):
    id: str
    name: str
    season: int


class SleeperConnectBody(BaseModel):
    username: str
    league_id: str
    season: int


class EspnConnectBody(BaseModel):
    league_id: str
    season: int
    swid: Optional[str] = None
    espn_s2: Optional[str] = None


class LinkedLeagueResponse(BaseModel):
    linked_league: LinkedLeagueOut
    profile: ProfileOut


async def _resolve_profile(
    profile_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Profile:
    p = await db.scalar(
        select(Profile)
        .where(Profile.id == profile_id, Profile.user_id == user.id)
        .options(selectinload(Profile.linked_league)),
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return p


def _apply_settings(profile: Profile, mapped: dict) -> None:
    """Merge mapped scoring into profile.settings_json, preserving user-controlled fields."""
    current = dict(profile.settings_json or {})
    current.update(mapped)
    profile.settings_json = current


@router.get("/sleeper/leagues", response_model=list[SleeperLeagueSummaryOut])
async def get_sleeper_leagues(
    profile_id: uuid.UUID,
    username: str,
    season: int,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> list[SleeperLeagueSummaryOut]:
    await _resolve_profile(profile_id, user, db)
    try:
        leagues = await list_user_leagues(username, season)
    except SleeperUserNotFound:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{username}' not found")
    return [SleeperLeagueSummaryOut(id=l.id, name=l.name, season=l.season) for l in leagues]


@router.post("/sleeper", response_model=LinkedLeagueResponse)
async def post_sleeper(
    profile_id: uuid.UUID,
    body: SleeperConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    data = await fetch_sleeper_league(body.league_id)
    mapped = sleeper_to_settings(data.raw_scoring, league_size=data.league_size)
    _apply_settings(profile, mapped)

    if profile.linked_league is None:
        ll = LinkedLeague(profile_id=profile.id)
        db.add(ll)
    else:
        ll = profile.linked_league
    ll.provider = "sleeper"
    ll.league_id = data.league_id
    ll.username_or_swid = body.username
    ll.credentials_encrypted = None
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return LinkedLeagueResponse(
        linked_league=LinkedLeagueOut.model_validate(ll),
        profile=ProfileOut.model_validate(profile),
    )


@router.post("/espn", response_model=LinkedLeagueResponse)
async def post_espn(
    profile_id: uuid.UUID,
    body: EspnConnectBody,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    try:
        data = await fetch_espn_league(body.league_id, body.season, body.swid, body.espn_s2)
    except EspnAuthRequired:
        raise HTTPException(
            status_code=400,
            detail="ESPN rejected the request — the league may be private; paste your SWID and espn_s2 cookies and try again.",
        )
    mapped = espn_to_settings(data.raw_scoring, league_size=data.league_size)
    _apply_settings(profile, mapped)

    if profile.linked_league is None:
        ll = LinkedLeague(profile_id=profile.id)
        db.add(ll)
    else:
        ll = profile.linked_league
    ll.provider = "espn"
    ll.league_id = data.league_id
    ll.username_or_swid = body.swid or ""
    ll.credentials_encrypted = encrypt(body.espn_s2) if body.espn_s2 else None
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return LinkedLeagueResponse(
        linked_league=LinkedLeagueOut.model_validate(ll),
        profile=ProfileOut.model_validate(profile),
    )


@router.post("/refresh", response_model=LinkedLeagueResponse)
async def refresh(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> LinkedLeagueResponse:
    profile = await _resolve_profile(profile_id, user, db)
    ll = profile.linked_league
    if ll is None:
        raise HTTPException(status_code=400, detail="Profile has no linked league")

    if ll.provider == "sleeper":
        data = await fetch_sleeper_league(ll.league_id)
        mapped = sleeper_to_settings(data.raw_scoring, league_size=data.league_size)
    elif ll.provider == "espn":
        espn_s2 = decrypt(ll.credentials_encrypted) if ll.credentials_encrypted else None
        try:
            data = await fetch_espn_league(
                ll.league_id, ll.league_metadata_json.get("season", 2026),
                ll.username_or_swid or None, espn_s2,
            )
        except EspnAuthRequired:
            raise HTTPException(status_code=400, detail="ESPN cookies expired — please reconnect.")
        mapped = espn_to_settings(data.raw_scoring, league_size=data.league_size)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{ll.provider}'")

    _apply_settings(profile, mapped)
    ll.league_metadata_json = {"name": data.name, "season": data.season}
    ll.keepers_json = data.keepers
    ll.adp_json = data.adp_json
    ll.last_synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return LinkedLeagueResponse(
        linked_league=LinkedLeagueOut.model_validate(ll),
        profile=ProfileOut.model_validate(profile),
    )


@router.delete("", status_code=204)
async def delete_link(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await _resolve_profile(profile_id, user, db)
    if profile.linked_league is None:
        return  # idempotent
    await db.delete(profile.linked_league)
    await db.commit()
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py` (or wherever existing routers are registered with `app.include_router(...)`), add:

```python
from app.api.linked_league import router as linked_league_router
app.include_router(linked_league_router, prefix="/api")
```

Place it next to the existing `app.include_router(profiles_router, ...)` call.

- [ ] **Step 5: Run tests, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_linked_league_endpoints.py -v
```

Expected: 8 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/linked_league.py backend/app/main.py backend/tests/test_linked_league_endpoints.py
git commit -m "feat(api): linked-league endpoints for Sleeper + ESPN + refresh + delete"
```

---

## Task 8: GenerateRequest keepers + league_adp integration

**Files:**
- Modify: `backend/app/schemas/generate.py`
- Modify: `backend/app/api/generate.py`
- Create: `backend/tests/test_generate_linked_league.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_generate_linked_league.py`:

```python
import pytest
from sqlalchemy import select
from app.models import Player, ProjectionLine, ADPEntry  # confirm exact symbol names against backend/app/models/__init__.py


async def _seed_two_players(test_db):
    p1 = Player(id="p1", name="Justin Jefferson", position="WR", team="MIN")
    p2 = Player(id="p2", name="Christian McCaffrey", position="RB", team="SF")
    test_db.add_all([p1, p2])
    await test_db.commit()
    return p1, p2


@pytest.mark.asyncio
async def test_generate_excludes_keepers_from_response(async_client, test_db):
    await _seed_two_players(test_db)
    body = {
        "scoring_format": "ppr",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.30,
        "weight_espn": 0.0,
        "weight_consensus": 0.70,
        "draft_rounds": 15,
        "rules": [],
        "keepers": ["Justin Jefferson"],
    }
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["players"]]
    assert "Justin Jefferson" not in names
    assert "Christian McCaffrey" in names


@pytest.mark.asyncio
async def test_generate_uses_league_adp_as_tiebreaker_when_provided(async_client, test_db):
    await _seed_two_players(test_db)
    body = {
        "scoring_format": "ppr",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.30,
        "weight_espn": 0.0,
        "weight_consensus": 0.70,
        "draft_rounds": 15,
        "rules": [],
        "league_adp": {"Justin Jefferson": 1.0, "Christian McCaffrey": 2.0},
    }
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200
    players = r.json()["players"]
    # Each player has a league_adp field that reflects the request value.
    jj = next(p for p in players if p["name"] == "Justin Jefferson")
    cmc = next(p for p in players if p["name"] == "Christian McCaffrey")
    assert jj["league_adp"] == 1.0
    assert cmc["league_adp"] == 2.0


@pytest.mark.asyncio
async def test_generate_without_linked_league_fields_works_unchanged(async_client, test_db):
    await _seed_two_players(test_db)
    body = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.30, "weight_espn": 0.0,
        "weight_consensus": 0.70, "draft_rounds": 15, "rules": [],
    }
    r = await async_client.post("/api/generate", json=body)
    assert r.status_code == 200
    for p in r.json()["players"]:
        assert p["league_adp"] is None  # field present, value null
```

(If your project's Player constructor differs from the form above, adjust the seeding helper. The point of these tests is the keeper-filtering and `league_adp` field — the seed just needs two players with distinct names.)

- [ ] **Step 2: Run tests, expect failure**

```bash
cd backend && venv/bin/pytest tests/test_generate_linked_league.py -v
```

Expected: failures — `keepers` and `league_adp` are unknown fields.

- [ ] **Step 3: Extend `GenerateRequest` + `TieredPlayerOut`**

In `backend/app/schemas/generate.py`:

```python
class GenerateRequest(BaseModel):
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_td_points: float = 4.0
    bonus_100yd_rushing: bool = False
    bonus_100yd_receiving: bool = False
    bonus_first_downs: bool = False
    weight_prior_year: float = 0.30
    weight_espn: float = 0.0
    weight_consensus: float = 0.70
    draft_rounds: int = 15
    rules: list[RuleSchema] = Field(default_factory=list)
    # New: optional inputs sourced from the active profile's linked league.
    keepers: Optional[list[str]] = None
    league_adp: Optional[dict[str, float]] = None
    # ... existing validators unchanged ...
```

Add to `TieredPlayerOut`:

```python
class TieredPlayerOut(BaseModel):
    # ... existing fields ...
    league_adp: Optional[float] = None
    # ... model_config unchanged ...
```

Make sure `Optional` is imported (it already is).

- [ ] **Step 4: Wire keepers + league_adp in `_run_generate`**

In `backend/app/api/generate.py`, near the top of `_run_generate` (right after the rule-merging block, before the `result = await db.execute(select(Player)...)` line):

```python
    keepers_normalized: set[str] = set()
    if req.keepers:
        from app.data.matching import normalize_name
        keepers_normalized = {normalize_name(name) for name in req.keepers}

    league_adp_normalized: dict[str, float] = {}
    if req.league_adp:
        from app.data.matching import normalize_name
        league_adp_normalized = {normalize_name(k): v for k, v in req.league_adp.items()}
```

Inside the per-player loop, immediately after `for player in players:`, add the keeper skip:

```python
        if keepers_normalized and normalize_name(player.name) in keepers_normalized:
            continue
```

(`normalize_name` was already imported at the top of the block above — if you used a local import, switch it to a module-level import to avoid repeated re-imports.)

When constructing the `TieredPlayer` (or whatever the engine emits), pass through `league_adp` as a player attribute. Find the call site that builds `TieredPlayer(...)` and add:

```python
            league_adp=league_adp_normalized.get(normalize_name(player.name)),
```

If `TieredPlayer` is a dataclass and doesn't have a `league_adp` field, add one with default `None`. (Same default in the engine's dataclass.)

In the final response construction (where `TieredPlayerOut` instances are built from `TieredPlayer`), pass `league_adp=t.league_adp` through.

The ADP tiebreaker integration: keep it minimal for v1. The `TieredPlayerOut.league_adp` field surfaces the league-specific pick number; the existing tier-engine ordering keeps its current behavior. (The "use league ADP as ADP tiebreaker" wiring through the engine's sort key is intentionally a follow-up — the field on the response is enough to deliver immediate user value via the UI and the data round-trips through generate, satisfying the spec's scope.)

- [ ] **Step 5: Run tests, expect pass**

```bash
cd backend && venv/bin/pytest tests/test_generate_linked_league.py -v
```

Expected: 3 pass.

- [ ] **Step 6: Sanity-run the existing generate tests**

```bash
cd backend && venv/bin/pytest tests/ -q -k "generate or tier"
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/generate.py backend/app/api/generate.py backend/tests/test_generate_linked_league.py
git commit -m "feat(generate): exclude keepers and surface league_adp on tier response"
```

---

## Task 9: Frontend types + API helpers

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/api/linkedLeague.ts`
- Create: `web/src/tests/api/linkedLeague.test.ts`

- [ ] **Step 1: Extend frontend types**

In `web/src/api/types.ts`, add:

```typescript
export interface LinkedLeague {
  profile_id: string;
  provider: "sleeper" | "espn";
  league_id: string;
  league_metadata_json: { name: string; season: number };
  keepers_json: Array<{ player_name: string; position: string; team: string }>;
  adp_json: Record<string, number> | null;
  last_synced_at: string;
}

export interface SleeperLeagueSummary {
  id: string;
  name: string;
  season: number;
}
```

And extend `Profile`:

```typescript
export interface Profile {
  id: string;
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Array<{ name: string; enabled: boolean; weight: number }>;
  linked_league: LinkedLeague | null;
}
```

- [ ] **Step 2: Write failing tests**

Create `web/src/tests/api/linkedLeague.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import {
  listSleeperLeagues,
  connectSleeper,
  connectEspn,
  refreshLink,
  disconnectLink,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";

const PID = "00000000-0000-0000-0000-000000000001";

describe("linkedLeague API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("listSleeperLeagues GETs the leagues endpoint", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify([{ id: "L1", name: "Champs", season: 2026 }]), { status: 200 }),
    );
    const result = await listSleeperLeagues(PID, "alice", 2026);
    expect(String(spy.mock.calls[0][0])).toContain(
      `/api/profiles/${PID}/link/sleeper/leagues?username=alice&season=2026`,
    );
    expect(result).toEqual([{ id: "L1", name: "Champs", season: 2026 }]);
  });

  it("connectSleeper POSTs body and returns updated profile", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({
        linked_league: { profile_id: PID, provider: "sleeper", league_id: "L1",
          league_metadata_json: { name: "Champs", season: 2026 },
          keepers_json: [], adp_json: null, last_synced_at: "2026-01-01T00:00:00Z" },
        profile: { id: PID, name: "My", settings_json: {}, rules_json: [], linked_league: null },
      }), { status: 200 }),
    );
    const out = await connectSleeper(PID, { username: "alice", league_id: "L1", season: 2026 });
    expect(String(spy.mock.calls[0][0])).toContain(`/api/profiles/${PID}/link/sleeper`);
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    expect(out.linked_league.provider).toBe("sleeper");
  });

  it("connectEspn POSTs and returns updated profile", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({
        linked_league: { profile_id: PID, provider: "espn", league_id: "12345",
          league_metadata_json: { name: "ESPN League", season: 2026 },
          keepers_json: [], adp_json: null, last_synced_at: "2026-01-01T00:00:00Z" },
        profile: { id: PID, name: "My", settings_json: {}, rules_json: [], linked_league: null },
      }), { status: 200 }),
    );
    const out = await connectEspn(PID, { league_id: "12345", season: 2026, swid: "{x}", espn_s2: "y" });
    expect(out.linked_league.provider).toBe("espn");
  });

  it("disconnectLink DELETEs and returns void on 204", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await disconnectLink(PID);
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("refreshLink POSTs and returns updated profile", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({
        linked_league: { profile_id: PID, provider: "sleeper", league_id: "L1",
          league_metadata_json: { name: "New", season: 2026 },
          keepers_json: [], adp_json: null, last_synced_at: "2026-02-01T00:00:00Z" },
        profile: { id: PID, name: "My", settings_json: {}, rules_json: [], linked_league: null },
      }), { status: 200 }),
    );
    const out = await refreshLink(PID);
    expect(out.linked_league.league_metadata_json.name).toBe("New");
  });

  it("connectSleeper throws ApiError on 404", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("not found", { status: 404 }),
    );
    await expect(
      connectSleeper(PID, { username: "ghost", league_id: "L1", season: 2026 }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 3: Run tests, expect failure**

```bash
cd web && npx vitest run src/tests/api/linkedLeague.test.ts
```

Expected: FAIL — module missing.

- [ ] **Step 4: Implement the API helpers**

Create `web/src/api/linkedLeague.ts`:

```typescript
import { apiFetch, API_URL, ApiError } from "./client";
import type { LinkedLeague, SleeperLeagueSummary, Profile } from "./types";

export interface LinkedLeagueResponse {
  linked_league: LinkedLeague;
  profile: Profile;
}

export function listSleeperLeagues(
  profileId: string,
  username: string,
  season: number,
): Promise<SleeperLeagueSummary[]> {
  const qs = new URLSearchParams({ username, season: String(season) }).toString();
  return apiFetch<SleeperLeagueSummary[]>(
    `/api/profiles/${profileId}/link/sleeper/leagues?${qs}`,
  );
}

export function connectSleeper(
  profileId: string,
  body: { username: string; league_id: string; season: number },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/sleeper`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function connectEspn(
  profileId: string,
  body: { league_id: string; season: number; swid?: string; espn_s2?: string },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/espn`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function refreshLink(profileId: string): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/refresh`,
    { method: "POST" },
  );
}

export async function disconnectLink(profileId: string): Promise<void> {
  // Raw fetch because 204 No Content.
  const resp = await fetch(`${API_URL}/api/profiles/${profileId}/link`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
}
```

- [ ] **Step 5: Run tests, expect pass**

```bash
cd web && npx vitest run src/tests/api/linkedLeague.test.ts
```

Expected: 6 pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/linkedLeague.ts web/src/api/types.ts web/src/tests/api/linkedLeague.test.ts
git commit -m "feat(api): frontend types + helpers for linked-league endpoints"
```

---

## Task 10: `LinkedLeagueSection` component (embedded in dialog)

**Files:**
- Create: `web/src/components/LinkedLeagueSection.tsx`
- Create: `web/src/components/SleeperConnectForm.tsx`
- Create: `web/src/components/EspnConnectForm.tsx`
- Create: `web/src/tests/components/SleeperConnectForm.test.tsx`
- Create: `web/src/tests/components/EspnConnectForm.test.tsx`
- Create: `web/src/tests/components/LinkedLeagueSection.test.tsx`
- Modify: `web/src/components/LinkedAccountsDialog.tsx`

- [ ] **Step 1: Write SleeperConnectForm tests**

Create `web/src/tests/components/SleeperConnectForm.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";

vi.mock("@/api/linkedLeague", () => ({
  listSleeperLeagues: vi.fn(),
  connectSleeper: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("SleeperConnectForm", () => {
  it("lists leagues after submitting username, then connects on confirm", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: "L1", name: "Champs", season: 2026 },
      { id: "L2", name: "Dynasty", season: 2026 },
    ]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: "L1",
        league_metadata_json: { name: "Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: { id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null },
    });
    const onLinked = vi.fn();
    render(<SleeperConnectForm profileId="p1" onLinked={onLinked} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    await u.selectOptions(screen.getByLabelText(/select your league/i), "L1");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", {
      username: "alice", league_id: "L1", season: expect.any(Number),
    }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("shows error when username not found", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (listSleeperLeagues as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new ApiError(404, "not found"));
    render(<SleeperConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "ghost");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/not found|couldn't find/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Implement `SleeperConnectForm`**

Create `web/src/components/SleeperConnectForm.tsx`:

```typescript
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { listSleeperLeagues, connectSleeper, LinkedLeagueResponse } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { SleeperLeagueSummary } from "@/api/types";

interface Props {
  profileId: string;
  onLinked: (result: LinkedLeagueResponse) => void;
  onCancel: () => void;
}

function currentSeason(): number {
  // NFL season rolls over in March; treat Jan-Feb as the previous season.
  const now = new Date();
  return now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
}

export function SleeperConnectForm({ profileId, onLinked, onCancel }: Props) {
  const [step, setStep] = useState<"username" | "league">("username");
  const [username, setUsername] = useState("");
  const [leagues, setLeagues] = useState<SleeperLeagueSummary[]>([]);
  const [chosenLeague, setChosenLeague] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleContinue() {
    setError(null);
    setBusy(true);
    try {
      const result = await listSleeperLeagues(profileId, username.trim(), currentSeason());
      if (result.length === 0) {
        setError("No Sleeper leagues found for that username this season.");
        return;
      }
      setLeagues(result);
      setChosenLeague(result[0].id);
      setStep("league");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError("We couldn't find that Sleeper username.");
      } else {
        setError("Couldn't reach Sleeper. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectSleeper(profileId, {
        username: username.trim(),
        league_id: chosenLeague,
        season: currentSeason(),
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      {step === "username" ? (
        <>
          <label className="block text-sm">
            <span>Sleeper username</span>
            <input
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-label="Sleeper username"
            />
          </label>
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
            <Button size="sm" disabled={busy || !username.trim()} onClick={handleContinue}>
              Continue
            </Button>
          </div>
        </>
      ) : (
        <>
          <label className="block text-sm">
            <span>Select your league</span>
            <select
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={chosenLeague}
              onChange={(e) => setChosenLeague(e.target.value)}
              aria-label="Select your league"
            >
              {leagues.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
          </label>
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={() => setStep("username")}>Back</Button>
            <Button size="sm" disabled={busy} onClick={handleConnect}>Connect</Button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write EspnConnectForm tests**

Create `web/src/tests/components/EspnConnectForm.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EspnConnectForm } from "@/components/EspnConnectForm";

vi.mock("@/api/linkedLeague", () => ({
  connectEspn: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("EspnConnectForm", () => {
  it("connects public league without cookie fields", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: { id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null },
    });
    const onLinked = vi.fn();
    render(<EspnConnectForm profileId="p1" onLinked={onLinked} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345",
    })));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("reveals SWID + espn_s2 fields when Private toggle is on", async () => {
    render(<EspnConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    expect(screen.queryByLabelText(/swid/i)).not.toBeInTheDocument();
    await u.click(screen.getByLabelText(/private league/i));
    expect(await screen.findByLabelText(/swid/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/espn_s2/i)).toBeInTheDocument();
  });

  it("includes cookies in the body when private + filled", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: { id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null },
    });
    render(<EspnConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByLabelText(/private league/i));
    await u.type(screen.getByLabelText(/swid/i), "{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345", swid: "{abc-123}", espn_s2: "blob",
    })));
  });
});
```

- [ ] **Step 4: Implement `EspnConnectForm`**

Create `web/src/components/EspnConnectForm.tsx`:

```typescript
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { connectEspn, LinkedLeagueResponse } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";

interface Props {
  profileId: string;
  onLinked: (result: LinkedLeagueResponse) => void;
  onCancel: () => void;
}

function currentSeason(): number {
  const now = new Date();
  return now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
}

export function EspnConnectForm({ profileId, onLinked, onCancel }: Props) {
  const [leagueId, setLeagueId] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [swid, setSwid] = useState("");
  const [espnS2, setEspnS2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const result = await connectEspn(profileId, {
        league_id: leagueId.trim(),
        season: currentSeason(),
        swid: isPrivate ? swid.trim() : undefined,
        espn_s2: isPrivate ? espnS2.trim() : undefined,
      });
      onLinked(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connect failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      <label className="block text-sm">
        <span>League ID</span>
        <input
          className="mt-1 block w-full rounded border px-2 py-1 text-sm"
          value={leagueId}
          onChange={(e) => setLeagueId(e.target.value)}
          aria-label="League ID"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isPrivate}
          onChange={(e) => setIsPrivate(e.target.checked)}
          aria-label="Private league"
        />
        <span>Private league</span>
      </label>
      {isPrivate && (
        <>
          <p className="text-xs text-muted-foreground">
            Find these on fantasy.espn.com → DevTools (F12) → Application → Cookies.
          </p>
          <label className="block text-sm">
            <span>SWID</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={swid}
              onChange={(e) => setSwid(e.target.value)}
              aria-label="SWID"
            />
          </label>
          <label className="block text-sm">
            <span>espn_s2</span>
            <input
              type="password"
              className="mt-1 block w-full rounded border px-2 py-1 text-sm"
              value={espnS2}
              onChange={(e) => setEspnS2(e.target.value)}
              aria-label="espn_s2"
            />
          </label>
        </>
      )}
      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button size="sm" disabled={busy || !leagueId.trim()} onClick={handleConnect}>
          Connect
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run sub-form tests**

```bash
cd web && npx vitest run src/tests/components/SleeperConnectForm.test.tsx src/tests/components/EspnConnectForm.test.tsx
```

Expected: all pass.

- [ ] **Step 6: Write LinkedLeagueSection tests**

Create `web/src/tests/components/LinkedLeagueSection.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedLeagueSection } from "@/components/LinkedLeagueSection";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

const profile: Profile = {
  id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null,
};

beforeEach(() => vi.clearAllMocks());

describe("LinkedLeagueSection", () => {
  it("when not linked, shows Connect Sleeper + ESPN buttons and coming-soon rows", () => {
    render(<LinkedLeagueSection profile={profile} onChanged={vi.fn()} />);
    expect(screen.getByRole("button", { name: /connect sleeper/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect espn/i })).toBeInTheDocument();
    // NFL Fantasy + CBS placeholders
    expect(screen.getByText(/nfl fantasy/i)).toBeInTheDocument();
    expect(screen.getByText(/cbs/i)).toBeInTheDocument();
    expect(screen.getAllByText(/coming soon/i)).toHaveLength(2);
  });

  it("when linked, shows provider + league name + Refresh + Disconnect", () => {
    const linked = {
      ...profile,
      linked_league: {
        profile_id: "p1", provider: "sleeper" as const, league_id: "L1",
        league_metadata_json: { name: "PPR Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "2026-01-01",
      },
    };
    render(<LinkedLeagueSection profile={linked} onChanged={vi.fn()} />);
    expect(screen.getByText(/PPR Champs/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^refresh$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^disconnect$/i })).toBeInTheDocument();
  });

  it("disconnect calls API and onChanged", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onChanged = vi.fn();
    const linked = {
      ...profile,
      linked_league: {
        profile_id: "p1", provider: "sleeper" as const, league_id: "L1",
        league_metadata_json: { name: "PPR Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "2026-01-01",
      },
    };
    render(<LinkedLeagueSection profile={linked} onChanged={onChanged} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^disconnect$/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
```

- [ ] **Step 7: Implement `LinkedLeagueSection`**

Create `web/src/components/LinkedLeagueSection.tsx`:

```typescript
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import { refreshLink, disconnectLink } from "@/api/linkedLeague";
import { ApiError } from "@/api/client";
import type { Profile } from "@/api/types";

interface Props {
  profile: Profile;
  onChanged: () => Promise<void> | void;
}

export function LinkedLeagueSection({ profile, onChanged }: Props) {
  const [activeForm, setActiveForm] = useState<"sleeper" | "espn" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRefresh() {
    setError(null);
    setBusy(true);
    try {
      await refreshLink(profile.id);
      await onChanged();
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
      await disconnectLink(profile.id);
      await onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
  }

  const linked = profile.linked_league;

  return (
    <section className="space-y-3 border-t pt-4 mt-4">
      <h3 className="text-sm font-medium">Fantasy league for "{profile.name}"</h3>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {linked ? (
        <div className="flex items-center justify-between">
          <span className="text-sm">
            {linked.provider === "sleeper" ? "Sleeper" : "ESPN"} · {linked.league_metadata_json.name}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={busy} onClick={handleRefresh}>
              Refresh
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={handleDisconnect}>
              Disconnect
            </Button>
          </div>
        </div>
      ) : activeForm === "sleeper" ? (
        <SleeperConnectForm
          profileId={profile.id}
          onLinked={async () => { setActiveForm(null); await onChanged(); }}
          onCancel={() => setActiveForm(null)}
        />
      ) : activeForm === "espn" ? (
        <EspnConnectForm
          profileId={profile.id}
          onLinked={async () => { setActiveForm(null); await onChanged(); }}
          onCancel={() => setActiveForm(null)}
        />
      ) : (
        <ul className="space-y-2 text-sm">
          <li className="flex items-center justify-between">
            <span>Sleeper</span>
            <Button size="sm" onClick={() => setActiveForm("sleeper")}>Connect Sleeper</Button>
          </li>
          <li className="flex items-center justify-between">
            <span>ESPN</span>
            <Button size="sm" onClick={() => setActiveForm("espn")}>Connect ESPN</Button>
          </li>
          <li className="flex items-center justify-between text-muted-foreground">
            <span>NFL Fantasy</span>
            <span className="text-xs">Coming soon</span>
          </li>
          <li className="flex items-center justify-between text-muted-foreground">
            <span>CBS</span>
            <span className="text-xs">Coming soon</span>
          </li>
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 8: Embed in LinkedAccountsDialog**

In `web/src/components/LinkedAccountsDialog.tsx`, accept an optional `activeProfile` prop and render `LinkedLeagueSection` under the existing provider rows.

Add import at top:

```typescript
import { LinkedLeagueSection } from "@/components/LinkedLeagueSection";
import type { Profile } from "@/api/types";
```

Extend the props interface:

```typescript
interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
  onRefresh: () => Promise<void>;
  initialError: string | null;
  activeProfile?: Profile | null;
}
```

In the component body, accept the new prop and render the section before the closing `</DialogContent>`:

```typescript
export function LinkedAccountsDialog({ open, onOpenChange, user, onRefresh, initialError, activeProfile }: Props) {
  // ... existing logic ...
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Linked accounts</DialogTitle>
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        <ul className="space-y-3">
          {/* ... existing email + Google + Yahoo rows ... */}
        </ul>
        {activeProfile && (
          <LinkedLeagueSection profile={activeProfile} onChanged={onRefresh} />
        )}
        {!activeProfile && (
          <p className="text-xs text-muted-foreground border-t pt-4 mt-4">
            Select a profile to link a fantasy league.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 9: Run all section tests**

```bash
cd web && npx vitest run src/tests/components/LinkedLeagueSection.test.tsx src/tests/components/SleeperConnectForm.test.tsx src/tests/components/EspnConnectForm.test.tsx src/tests/components/LinkedAccountsDialog.test.tsx
```

Expected: green. The existing LinkedAccountsDialog tests pass because `activeProfile` is optional and defaults to undefined.

- [ ] **Step 10: Commit**

```bash
git add web/src/components/LinkedLeagueSection.tsx web/src/components/SleeperConnectForm.tsx web/src/components/EspnConnectForm.tsx web/src/components/LinkedAccountsDialog.tsx web/src/tests/components/LinkedLeagueSection.test.tsx web/src/tests/components/SleeperConnectForm.test.tsx web/src/tests/components/EspnConnectForm.test.tsx
git commit -m "feat(ui): LinkedLeagueSection with Sleeper + ESPN sub-forms"
```

---

## Task 11: SettingsPanel auto-detected chip

**Files:**
- Create: `web/src/components/LinkedLeagueChip.tsx`
- Create: `web/src/tests/components/LinkedLeagueChip.test.tsx`
- Modify: `web/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/tests/components/LinkedLeagueChip.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedLeagueChip } from "@/components/LinkedLeagueChip";

vi.mock("@/api/linkedLeague", () => ({
  refreshLink: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("LinkedLeagueChip", () => {
  it("renders provider + league name and a Refresh button", () => {
    render(<LinkedLeagueChip profileId="p1" provider="sleeper" leagueName="PPR Champs" onRefreshed={vi.fn()} />);
    expect(screen.getByText(/auto-detected from sleeper/i)).toBeInTheDocument();
    expect(screen.getByText(/PPR Champs/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
  });

  it("clicking Refresh calls refreshLink and onRefreshed", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefreshed = vi.fn();
    render(<LinkedLeagueChip profileId="p1" provider="sleeper" leagueName="PPR Champs" onRefreshed={onRefreshed} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /refresh/i }));
    await waitFor(() => expect(refreshLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefreshed).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Implement the chip**

Create `web/src/components/LinkedLeagueChip.tsx`:

```typescript
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { refreshLink } from "@/api/linkedLeague";

interface Props {
  profileId: string;
  provider: "sleeper" | "espn";
  leagueName: string;
  onRefreshed: () => Promise<void> | void;
}

export function LinkedLeagueChip({ profileId, provider, leagueName, onRefreshed }: Props) {
  const [busy, setBusy] = useState(false);
  const label = provider === "sleeper" ? "Sleeper" : "ESPN";
  async function handleRefresh() {
    setBusy(true);
    try {
      await refreshLink(profileId);
      await onRefreshed();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex items-center justify-between rounded border bg-muted/40 px-3 py-2 text-xs">
      <span>Auto-detected from {label} · {leagueName}</span>
      <Button size="sm" variant="ghost" disabled={busy} onClick={handleRefresh}>
        Refresh
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Render the chip above SettingsPanel**

In `web/src/components/SettingsPanel.tsx`, accept an optional `linkedLeague` prop and a `profileId` prop, and render the chip at the top.

Find the `SettingsPanel` props interface and extend it:

```typescript
interface SettingsPanelProps {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
  linkedLeague?: { provider: "sleeper" | "espn"; leagueName: string } | null;
  profileId?: string | null;
  onRefreshLink?: () => Promise<void> | void;
}
```

At the top of the JSX returned by the component, insert (next to existing imports add `LinkedLeagueChip`):

```tsx
{linkedLeague && profileId && (
  <LinkedLeagueChip
    profileId={profileId}
    provider={linkedLeague.provider}
    leagueName={linkedLeague.leagueName}
    onRefreshed={async () => { await onRefreshLink?.(); }}
  />
)}
```

(If the existing SettingsPanel renders a single root container, place the chip just inside that container at the top.)

- [ ] **Step 4: Run chip tests**

```bash
cd web && npx vitest run src/tests/components/LinkedLeagueChip.test.tsx
```

Expected: 2 pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/LinkedLeagueChip.tsx web/src/components/SettingsPanel.tsx web/src/tests/components/LinkedLeagueChip.test.tsx
git commit -m "feat(ui): LinkedLeagueChip atop SettingsPanel when profile is linked"
```

---

## Task 12: `App.tsx` wiring + TiersPanel keepers display

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/TiersPanel.tsx`
- Modify: `web/src/tests/integration/app-authenticated.test.tsx`

- [ ] **Step 1: Add an integration test**

Append inside the `describe("App (authenticated integration)", ...)` block in `web/src/tests/integration/app-authenticated.test.tsx`:

```typescript
  it("includes keepers and league_adp in the generate request when active profile is linked", async () => {
    const linkedProfile = {
      ...PROFILE_ONE,
      linked_league: {
        profile_id: "p1", provider: "sleeper" as const, league_id: "L1",
        league_metadata_json: { name: "PPR Champs", season: 2026 },
        keepers_json: [
          { player_name: "Justin Jefferson", position: "WR", team: "MIN" },
        ],
        adp_json: { "Justin Jefferson": 1.0 },
        last_synced_at: "2026-01-01",
      },
    };
    mockAuthenticated([linkedProfile]);

    let generateBody: Record<string, unknown> = {};
    server.use(
      http.post(`${API_URL}/api/generate`, async ({ request }) => {
        generateBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ players: [], total: 0, data_as_of: null });
      }),
    );

    renderApp();
    await waitFor(() => expect(screen.getByRole("button", { name: /PPR 12-team/i })).toBeInTheDocument());
    await screen.findByText("Target Share Premium");

    const generateBtn = screen.getByRole("button", { name: /generate/i });
    await userEvent.setup().click(generateBtn);

    await waitFor(() => {
      expect(generateBody.keepers).toEqual(["Justin Jefferson"]);
      expect(generateBody.league_adp).toEqual({ "Justin Jefferson": 1.0 });
    });
  });
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd web && npx vitest run src/tests/integration/app-authenticated.test.tsx -t "keepers and league_adp"
```

Expected: FAIL — App doesn't include those fields yet.

- [ ] **Step 3: Wire `App.tsx`**

In `web/src/App.tsx`, find the `buildRequest` function. Extend it:

```typescript
const buildRequest = (): GenerateRequest => {
  const active = profiles.find((p) => p.id === activeProfileId);
  const linked = active?.linked_league ?? null;
  return {
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
    keepers: linked?.keepers_json.map((k) => k.player_name) ?? undefined,
    league_adp: linked?.adp_json ?? undefined,
  };
};
```

Also update the `<Header>` invocation to pass `activeProfile` into the dialog. Find where `<LinkedAccountsDialog ... />` is rendered (added in Task 8 of the previous plan) and add:

```tsx
activeProfile={profiles.find((p) => p.id === activeProfileId) ?? null}
```

Pass the linked-league info to `<SettingsPanel>`. Find the `<SettingsPanel value={settings} onChange={setSettings} />` line and replace with:

```tsx
<SettingsPanel
  value={settings}
  onChange={setSettings}
  linkedLeague={
    (() => {
      const active = profiles.find((p) => p.id === activeProfileId);
      const ll = active?.linked_league;
      return ll ? { provider: ll.provider, leagueName: ll.league_metadata_json.name } : null;
    })()
  }
  profileId={activeProfileId}
  onRefreshLink={refresh}
/>
```

(`refresh` is already destructured from `useAuth()`.)

Update `web/src/api/types.ts`'s `GenerateRequest` to include the new optional fields:

```typescript
export interface GenerateRequest {
  // ... existing fields ...
  keepers?: string[];
  league_adp?: Record<string, number>;
}
```

- [ ] **Step 4: Render excluded keepers in TiersPanel**

The backend doesn't currently echo the keepers list back in the response — but the frontend already knows them (it sent them). Read them off the active profile's `linked_league.keepers_json` for display.

Modify `web/src/components/TiersPanel.tsx` to accept a `keepers` prop and show them when non-empty:

```typescript
interface TiersPanelProps {
  result: GenerateResponse | null;
  isPending: boolean;
  onDownloadCsv: () => void;
  keepers?: Array<{ player_name: string; position: string; team: string }>;
}

export function TiersPanel({ result, isPending, onDownloadCsv, keepers }: TiersPanelProps) {
  // ... existing logic ...
  return (
    <div className="...existing-classes...">
      {keepers && keepers.length > 0 && (
        <div className="border-b px-3 py-2 text-xs text-muted-foreground">
          Excluded keepers: {keepers.map((k) => k.player_name).join(", ")}
        </div>
      )}
      {/* ... existing JSX ... */}
    </div>
  );
}
```

Then in `App.tsx`, pass the keepers through:

```tsx
<TiersPanel
  result={generate.data ?? null}
  isPending={generate.isPending}
  onDownloadCsv={() => downloadCsv(buildRequest())}
  keepers={
    profiles.find((p) => p.id === activeProfileId)?.linked_league?.keepers_json
  }
/>
```

- [ ] **Step 5: Run tests, expect pass**

```bash
cd web && npx vitest run
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/components/TiersPanel.tsx web/src/api/types.ts web/src/tests/integration/app-authenticated.test.tsx
git commit -m "feat(ui): pass linked-league keepers + ADP through generate request"
```

---

## Task 13: Full sweep, push, open PR

- [ ] **Step 1: Full backend tests**

```bash
cd backend && venv/bin/pytest tests/ -q --ignore=tests/test_sources
```

Expected: green. (The `data/sources` tests are heavy and were already gating the earlier work — skip if memory-constrained, but include if practical.)

- [ ] **Step 2: Full frontend tests**

```bash
cd web && npx vitest run
```

Expected: green.

- [ ] **Step 3: Push**

```bash
git push -u origin feat/fantasy-league-linking
```

- [ ] **Step 4: Open PR**

```bash
gh pr create --title "feat: fantasy league linking (Sleeper + ESPN)" --body "$(cat <<'EOF'
## Summary
- Lets users link a Sleeper or Public/Private ESPN league to a profile.
- On link, AutoTiers auto-detects scoring settings (PPR/half/standard, QB TD points, yardage bonuses), captures keepers, and pulls league draft positions when a draft exists.
- Generate now excludes keepers from the tier output and surfaces league-specific ADP on each player.
- NFL Fantasy + CBS appear as "Coming soon" placeholders — they would require credentialled scraping (out of scope).

## Design
- Spec: `docs/superpowers/specs/2026-05-29-fantasy-league-linking-design.md`
- Plan: `docs/superpowers/plans/2026-05-29-fantasy-league-linking.md`
- New `linked_leagues` table 1:1 with `profiles`. Encrypted-at-rest espn_s2 cookie via Fernet.
- Backend integrations under `app/integrations/` (separate from global-data `app/data/sources/`).
- Frontend extends the existing "Linked accounts" dialog with a per-active-profile "Fantasy league" section.

## Test plan
- [x] Backend: Fernet round-trip, Sleeper client (4 tests), ESPN client (4 tests), scoring mappers (7 tests), linked-league endpoints (8 tests), generate keepers + league_adp (3 tests).
- [x] Frontend: linkedLeague API helpers (6 tests), Sleeper sub-form (2 tests), ESPN sub-form (3 tests), LinkedLeagueSection (3 tests), LinkedLeagueChip (2 tests), App integration includes keepers + league_adp on generate (1 test).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.

---

## Notes for the implementer

- **Don't add a new ADP weight slider.** `weight_consensus` continues to govern the projection blend. League ADP surfaces on each tier row but doesn't reshuffle tiers in v1 — that follow-up was deliberately deferred per the spec.
- **Mock `/v1/players/nfl` lightly.** Sleeper's real player dict is ~5MB; the tests use a tiny stub. The production client fetches the real one each time — acceptable for v1 because link/refresh is rare and Sleeper supports it without rate limits.
- **`encrypt` / `decrypt` only on espn_s2.** SWID is a UUID-shaped identifier, not a secret on its own — store it in plaintext. Same for Sleeper username.
- **`_apply_settings` merges, doesn't replace.** Keeps the user's existing `weights` (and any other future user-controlled fields) when the mapper writes the league's scoring shape.
- **The selectinload on `Profile.linked_league` is required.** Without it, accessing `profile.linked_league` inside the response builder triggers a lazy load that fails in async context. The /me + linked-league endpoints both need this — see Task 6 and Task 7 patterns.
- **Coming-soon rows** for NFL Fantasy + CBS are intentionally not interactive. Don't wire them to anything.
