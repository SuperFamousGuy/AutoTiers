# AutoTiers Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `DataFetcher` with a real pipeline that pulls live data from Sleeper, nfl_data_py, ESPN, and FantasyPros, normalizes it against Sleeper's master player ID, persists it idempotently, computes play-by-play-derived stats (`expected_tds`, `red_zone_looks`), adds the two BUILTIN_RULES that depend on those stats, and surfaces per-source freshness/errors via `/api/data/status`.

**Architecture:** Sleeper is the master player ID source. Each `SourceFetcher` runs in its own DB transaction so a partial failure doesn't roll back the whole refresh. FantasyPros (no IDs) resolves to players via fuzzy match on `(normalized_name, team, position)`. All HTTP traffic flows through `httpx`, mocked in tests with `respx`; `nfl_data_py` is monkey-patched to read fixture CSVs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, httpx, nfl_data_py, rapidfuzz, beautifulsoup4 (with lxml), respx (test).

**Prerequisites:**
- Working directory: a fresh feature branch off `main` named `data-pipeline` (create with `git checkout main && git pull && git checkout -b data-pipeline`)
- Venv set up: `cd backend && python -m venv venv && source venv/bin/activate && pip install -e ".[dev]"`
- All 40 Plan 1 tests passing as the baseline: `pytest -v`

---

## Task 1: Add new dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add runtime deps**

Add to the `dependencies` list in `backend/pyproject.toml`:

```toml
    "nfl_data_py>=0.3",
    "rapidfuzz>=3.0",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
```

(`nfl_data_py` is already implicitly available because the parent project listed it conceptually; verify it's in the `dependencies` block and add it if missing.)

- [ ] **Step 2: Add dev dep**

Add to the `dev` optional-dependencies list:

```toml
    "respx>=0.21",
```

- [ ] **Step 3: Reinstall**

```bash
cd backend && source venv/bin/activate && pip install -e ".[dev]"
```

Expected: pip resolves and installs all four runtime deps and respx.

- [ ] **Step 4: Smoke-test imports**

```bash
python -c "import rapidfuzz, bs4, lxml, nfl_data_py, respx; print('ok')"
```

Expected: prints `ok` with no ImportError.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml
git commit -m "deps: add data pipeline runtime + test dependencies"
```

---

## Task 2: Schema changes — Player columns + DataSourceStatus model

**Files:**
- Modify: `backend/app/models/player.py`
- Create: `backend/app/models/data_source_status.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_models.py` (NEW)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models.py`:

```python
import pytest
from datetime import datetime
from sqlalchemy import select
from app.models import Player, DataSourceStatus


@pytest.mark.asyncio
async def test_player_has_new_columns(test_db):
    p = Player(
        id="sleep_1234", name="Test Player", position="WR", team="DAL",
        age=25, years_exp=3, active=True, gsis_id="00-1234567", espn_id="9999",
    )
    test_db.add(p)
    await test_db.commit()
    fetched = await test_db.scalar(select(Player).where(Player.id == "sleep_1234"))
    assert fetched.active is True
    assert fetched.gsis_id == "00-1234567"
    assert fetched.espn_id == "9999"


@pytest.mark.asyncio
async def test_data_source_status_round_trip(test_db):
    now = datetime(2026, 5, 20, 3, 0, 0)
    s = DataSourceStatus(
        source="sleeper", last_updated=now, last_attempted=now,
        last_error=None, rows_upserted=1542,
    )
    test_db.add(s)
    await test_db.commit()
    fetched = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "sleeper"))
    assert fetched.rows_upserted == 1542
    assert fetched.last_error is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_models.py -v
```

Expected: FAIL — `Player` has no attribute `active`, `DataSourceStatus` not importable.

- [ ] **Step 3: Add columns to Player**

In `backend/app/models/player.py`, the `Player` class gets three new fields. The full updated class:

```python
class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str] = mapped_column(String(10), nullable=False)
    team: Mapped[Optional[str]] = mapped_column(String(5))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    years_exp: Mapped[Optional[int]] = mapped_column(Integer)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    gsis_id: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    espn_id: Mapped[Optional[str]] = mapped_column(String(20), index=True)

    stats: Mapped[list["PlayerStat"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    projections: Mapped[list["Projection"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    adp_entries: Mapped[list["ADPData"]] = relationship(back_populates="player", cascade="all, delete-orphan")
```

Don't forget to add `Boolean` to the import line at the top:

```python
from sqlalchemy import String, Integer, Float, ForeignKey, Date, Boolean, UniqueConstraint
```

- [ ] **Step 4: Create DataSourceStatus model**

Create `backend/app/models/data_source_status.py`:

```python
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DataSourceStatus(Base):
    __tablename__ = "data_source_status"

    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_attempted: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: Register in `__init__.py`**

Update `backend/app/models/__init__.py` to:

```python
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models.adp import ADPData
from app.models.team import TeamContext
from app.models.data_source_status import DataSourceStatus

__all__ = ["Player", "PlayerStat", "Projection", "ADPData", "TeamContext", "DataSourceStatus"]
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 7: Verify Plan 1 tests still pass**

```bash
pytest -v 2>&1 | tail -5
```

Expected: 42 passed (40 existing + 2 new).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/ backend/tests/test_models.py
git commit -m "feat: add Player.active/gsis_id/espn_id and DataSourceStatus model"
```

---

## Task 3: Alembic migration 002

**Files:**
- Create: `backend/alembic/versions/002_data_pipeline.py`

- [ ] **Step 1: Find the previous revision ID**

```bash
cd backend && source venv/bin/activate && grep "^revision" alembic/versions/001_initial.py
```

Expected: prints `revision = "001_initial"` or similar — note that exact string.

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/002_data_pipeline.py` (substitute the actual previous revision ID from Step 1 for `001_initial`):

```python
"""data pipeline schema changes

Revision ID: 002_data_pipeline
Revises: 001_initial
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa


revision = "002_data_pipeline"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("players", sa.Column("gsis_id", sa.String(length=20), nullable=True))
    op.add_column("players", sa.Column("espn_id", sa.String(length=20), nullable=True))
    op.create_index("ix_players_gsis_id", "players", ["gsis_id"])
    op.create_index("ix_players_espn_id", "players", ["espn_id"])

    op.create_table(
        "data_source_status",
        sa.Column("source", sa.String(length=30), primary_key=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("last_attempted", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("data_source_status")
    op.drop_index("ix_players_espn_id", table_name="players")
    op.drop_index("ix_players_gsis_id", table_name="players")
    op.drop_column("players", "espn_id")
    op.drop_column("players", "gsis_id")
    op.drop_column("players", "active")
```

- [ ] **Step 3: Verify migration parses with offline SQL render**

```bash
alembic upgrade --sql head 2>&1 | tail -20
```

Expected: prints SQL for the new ALTER TABLE / CREATE TABLE / CREATE INDEX statements with no Python errors.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/002_data_pipeline.py
git commit -m "feat: alembic 002 — add Player columns and data_source_status table"
```

---

## Task 4: Name normalization + fuzzy matching (TDD)

**Files:**
- Create: `backend/app/data/matching.py`
- Test: `backend/tests/test_sources/__init__.py` (NEW empty file)
- Test: `backend/tests/test_sources/test_matching.py` (NEW)

- [ ] **Step 1: Create test dir**

```bash
mkdir -p backend/tests/test_sources && touch backend/tests/test_sources/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_sources/test_matching.py`:

```python
import pytest
from sqlalchemy import select
from app.models import Player
from app.data.matching import normalize_name, fuzzy_match


@pytest.mark.parametrize("raw,expected", [
    ("Patrick Mahomes II", "patrick mahomes"),
    ("Marvin Harrison Jr.", "marvin harrison"),
    ("Odell Beckham Jr", "odell beckham"),
    ("D.J. Moore", "dj moore"),
    ("Ja'Marr Chase", "jamarr chase"),
    ("  CeeDee  Lamb  ", "ceedee lamb"),
    ("Amon-Ra St. Brown", "amonra st brown"),
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.asyncio
async def test_fuzzy_match_exact(test_db):
    test_db.add(Player(id="sleep_1", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Justin Jefferson", "MIN", "WR")
    assert match is not None
    assert match.id == "sleep_1"


@pytest.mark.asyncio
async def test_fuzzy_match_ignores_jr_suffix(test_db):
    test_db.add(Player(id="sleep_1", name="Marvin Harrison Jr.", position="WR", team="ARI"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Marvin Harrison", "ARI", "WR")
    assert match is not None and match.id == "sleep_1"


@pytest.mark.asyncio
async def test_fuzzy_match_handles_traded_player(test_db):
    """Player traded mid-cycle — name and position match, team differs."""
    test_db.add(Player(id="sleep_1", name="Davante Adams", position="WR", team="NYJ"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Davante Adams", "LV", "WR")
    assert match is not None and match.id == "sleep_1"


@pytest.mark.asyncio
async def test_fuzzy_match_returns_none_below_threshold(test_db):
    test_db.add(Player(id="sleep_1", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Totally Unrelated Player", "MIN", "WR")
    assert match is None


@pytest.mark.asyncio
async def test_fuzzy_match_respects_position(test_db):
    test_db.add(Player(id="sleep_qb", name="Josh Allen", position="QB", team="BUF"))
    test_db.add(Player(id="sleep_lb", name="Josh Allen", position="LB", team="JAX"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Josh Allen", "BUF", "QB")
    assert match.id == "sleep_qb"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_sources/test_matching.py -v
```

Expected: FAIL — `app.data.matching` doesn't exist.

- [ ] **Step 4: Create `backend/app/data/matching.py`**

```python
"""Player name normalization and fuzzy matching for sources without stable IDs."""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player


_SUFFIX_PATTERN = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)
_PUNCT_PATTERN = re.compile(r"[^\w\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes (Jr/Sr/II/III/IV), remove punctuation, collapse whitespace."""
    s = name.lower()
    s = _SUFFIX_PATTERN.sub("", s)
    s = _PUNCT_PATTERN.sub("", s)
    s = _WHITESPACE_PATTERN.sub(" ", s).strip()
    return s


async def fuzzy_match(
    db: AsyncSession,
    name: str,
    team: str,
    position: str,
    threshold: int = 90,
) -> Optional[Player]:
    """
    Resolve a (name, team, position) triple to a Player row.

    Strategy (in order):
      1. Exact match on (normalized_name, team, position) — return immediately.
      2. Exact match on (normalized_name, position), ignoring team — handles traded players.
      3. rapidfuzz token_set_ratio on normalized_name within the position bucket — return if score >= threshold.
    Returns None if no candidate scores above threshold.
    """
    target = normalize_name(name)

    # Strategy 1: exact match including team
    candidates = (await db.scalars(
        select(Player).where(Player.position == position)
    )).all()

    same_team = [p for p in candidates if normalize_name(p.name) == target and p.team == team]
    if same_team:
        return same_team[0]

    # Strategy 2: exact name + position, any team
    any_team = [p for p in candidates if normalize_name(p.name) == target]
    if any_team:
        return any_team[0]

    # Strategy 3: fuzzy
    best: Optional[Player] = None
    best_score = 0
    for p in candidates:
        score = fuzz.token_set_ratio(target, normalize_name(p.name))
        if score >= threshold and score > best_score:
            best = p
            best_score = score
    return best
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sources/test_matching.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/matching.py backend/tests/test_sources/
git commit -m "feat: name normalization and fuzzy matching for FantasyPros resolution"
```

---

## Task 5: Source base protocol + status helpers (TDD)

**Files:**
- Create: `backend/app/data/sources/__init__.py` (empty)
- Create: `backend/app/data/sources/base.py`
- Create: `backend/app/data/status.py`
- Test: `backend/tests/test_data_status.py` (NEW)

- [ ] **Step 1: Create directory**

```bash
mkdir -p backend/app/data/sources && touch backend/app/data/sources/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_data_status.py`:

```python
import pytest
from datetime import datetime
from sqlalchemy import select
from app.models import DataSourceStatus
from app.data.status import upsert_status, get_all_status


@pytest.mark.asyncio
async def test_upsert_status_inserts_new(test_db):
    now = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="sleeper", last_attempted=now,
                        success=True, rows_upserted=1000, error=None)
    await test_db.commit()
    row = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "sleeper"))
    assert row.rows_upserted == 1000
    assert row.last_updated == now
    assert row.last_error is None


@pytest.mark.asyncio
async def test_upsert_status_updates_existing(test_db):
    t1 = datetime(2026, 5, 19, 12, 0, 0)
    t2 = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="sleeper", last_attempted=t1, success=True, rows_upserted=500, error=None)
    await test_db.commit()
    await upsert_status(test_db, source="sleeper", last_attempted=t2, success=True, rows_upserted=600, error=None)
    await test_db.commit()
    row = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "sleeper"))
    assert row.rows_upserted == 600
    assert row.last_updated == t2


@pytest.mark.asyncio
async def test_upsert_status_failure_keeps_last_updated(test_db):
    """When a refresh fails, last_attempted advances but last_updated does not."""
    t1 = datetime(2026, 5, 19, 12, 0, 0)
    t2 = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="espn", last_attempted=t1, success=True, rows_upserted=400, error=None)
    await test_db.commit()
    await upsert_status(test_db, source="espn", last_attempted=t2, success=False, rows_upserted=0, error="HTTP 503")
    await test_db.commit()
    row = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "espn"))
    assert row.last_updated == t1   # unchanged
    assert row.last_attempted == t2  # advanced
    assert row.last_error == "HTTP 503"


@pytest.mark.asyncio
async def test_get_all_status_returns_dict(test_db):
    now = datetime(2026, 5, 20, 12, 0, 0)
    await upsert_status(test_db, source="sleeper", last_attempted=now, success=True, rows_upserted=10, error=None)
    await upsert_status(test_db, source="espn", last_attempted=now, success=False, rows_upserted=0, error="bad")
    await test_db.commit()
    result = await get_all_status(test_db)
    assert set(result.keys()) == {"sleeper", "espn"}
    assert result["sleeper"]["rows_upserted"] == 10
    assert result["espn"]["last_error"] == "bad"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_data_status.py -v
```

Expected: FAIL — `app.data.status` doesn't exist.

- [ ] **Step 4: Create `backend/app/data/sources/base.py`**

```python
"""Source-agnostic protocol and result type for data fetchers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SourceResult:
    source: str
    rows_upserted: int
    last_attempted: datetime
    success: bool
    error: Optional[str] = None


class SourceFetcher(Protocol):
    name: str

    async def fetch(self, db: AsyncSession) -> SourceResult: ...
```

- [ ] **Step 5: Create `backend/app/data/status.py`**

```python
"""Read/write helpers for DataSourceStatus rows."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSourceStatus


async def upsert_status(
    db: AsyncSession,
    source: str,
    last_attempted: datetime,
    success: bool,
    rows_upserted: int,
    error: Optional[str],
) -> None:
    """Upsert a status row. `last_updated` only advances on success."""
    existing = await db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == source))
    if existing is None:
        existing = DataSourceStatus(source=source, last_attempted=last_attempted, rows_upserted=0)
        db.add(existing)
    existing.last_attempted = last_attempted
    existing.last_error = error
    if success:
        existing.last_updated = last_attempted
        existing.rows_upserted = rows_upserted


async def get_all_status(db: AsyncSession) -> dict[str, dict]:
    """Return a {source: {...}} dict for all sources currently tracked."""
    rows = (await db.scalars(select(DataSourceStatus))).all()
    return {
        r.source: {
            "last_updated": r.last_updated.isoformat() if r.last_updated else None,
            "last_attempted": r.last_attempted.isoformat() if r.last_attempted else None,
            "last_error": r.last_error,
            "rows_upserted": r.rows_upserted,
        }
        for r in rows
    }
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_data_status.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/data/sources/__init__.py backend/app/data/sources/base.py backend/app/data/status.py backend/tests/test_data_status.py
git commit -m "feat: SourceFetcher protocol and DataSourceStatus read/write helpers"
```

---

## Task 6: Sleeper fetcher (TDD)

**Files:**
- Create: `backend/app/data/sources/sleeper.py`
- Create: `backend/tests/fixtures/sleeper_players.json` (NEW)
- Create: `backend/tests/test_sources/test_sleeper.py` (NEW)

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/__init__.py` (empty) and `backend/tests/fixtures/sleeper_players.json`:

```json
{
  "4017": {"player_id": "4017", "first_name": "Josh", "last_name": "Allen", "full_name": "Josh Allen", "position": "QB", "team": "BUF", "age": 29, "years_exp": 7, "active": true, "gsis_id": "00-0034796", "espn_id": 3918298},
  "6794": {"player_id": "6794", "first_name": "Ja'Marr", "last_name": "Chase", "full_name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "age": 26, "years_exp": 4, "active": true, "gsis_id": "00-0036900", "espn_id": 4362628},
  "6786": {"player_id": "6786", "first_name": "Justin", "last_name": "Jefferson", "full_name": "Justin Jefferson", "position": "WR", "team": "MIN", "age": 27, "years_exp": 5, "active": true, "gsis_id": "00-0036322", "espn_id": 4262921},
  "8112": {"player_id": "8112", "first_name": "Bijan", "last_name": "Robinson", "full_name": "Bijan Robinson", "position": "RB", "team": "ATL", "age": 23, "years_exp": 2, "active": true, "gsis_id": "00-0039169", "espn_id": 4430807},
  "4866": {"player_id": "4866", "first_name": "Saquon", "last_name": "Barkley", "full_name": "Saquon Barkley", "position": "PHI", "team": "PHI", "age": 28, "years_exp": 7, "active": true, "gsis_id": "00-0034844", "espn_id": 3929630},
  "4035": {"player_id": "4035", "first_name": "Lamar", "last_name": "Jackson", "full_name": "Lamar Jackson", "position": "QB", "team": "BAL", "age": 28, "years_exp": 7, "active": true, "gsis_id": "00-0034796", "espn_id": 3916387},
  "1234_inactive": {"player_id": "1234_inactive", "first_name": "Retired", "last_name": "Player", "full_name": "Retired Player", "position": "WR", "team": null, "age": 38, "years_exp": 15, "active": false, "gsis_id": null, "espn_id": null},
  "9999_kicker": {"player_id": "9999_kicker", "first_name": "Justin", "last_name": "Tucker", "full_name": "Justin Tucker", "position": "K", "team": "BAL", "age": 35, "years_exp": 13, "active": true, "gsis_id": "00-0028018", "espn_id": 15683}
}
```

> NOTE: real Sleeper responses contain ~11000 entries including practice-squad and historical players. This fixture is a curated subset — the fetcher must filter on `position in {QB, RB, WR, TE, K, DST}` AND `team is not None`, so `1234_inactive` should be skipped.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_sources/test_sleeper.py`:

```python
import json
import pytest
import respx
from httpx import Response
from pathlib import Path

from sqlalchemy import select
from app.models import Player
from app.data.sources.sleeper import SleeperFetcher


FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "sleeper_players.json").read_text())


@pytest.fixture
def mock_sleeper():
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(200, json=FIXTURE))
        yield router


@pytest.mark.asyncio
async def test_sleeper_upserts_active_players(test_db, mock_sleeper):
    fetcher = SleeperFetcher()
    result = await fetcher.fetch(test_db)
    assert result.success
    # Only players with team != null AND fantasy position get inserted.
    # 7 fantasy-eligible with a team. (1234_inactive has team=null so dropped.)
    assert result.rows_upserted == 7
    players = (await test_db.scalars(select(Player))).all()
    ids = {p.id for p in players}
    assert "4017" in ids
    assert "1234_inactive" not in ids


@pytest.mark.asyncio
async def test_sleeper_marks_missing_players_inactive(test_db, mock_sleeper):
    # Pre-seed a player who is NOT in the upcoming Sleeper response.
    test_db.add(Player(id="ghost_player", name="Old Guy", position="WR", team="DEN", active=True))
    await test_db.commit()

    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    ghost = await test_db.scalar(select(Player).where(Player.id == "ghost_player"))
    assert ghost.active is False


@pytest.mark.asyncio
async def test_sleeper_populates_cross_ids(test_db, mock_sleeper):
    fetcher = SleeperFetcher()
    await fetcher.fetch(test_db)
    allen = await test_db.scalar(select(Player).where(Player.id == "4017"))
    assert allen.gsis_id == "00-0034796"
    assert allen.espn_id == "3918298"  # str, not int
    assert allen.team == "BUF"


@pytest.mark.asyncio
async def test_sleeper_handles_http_error(test_db):
    with respx.mock(base_url="https://api.sleeper.app") as router:
        router.get("/v1/players/nfl").mock(return_value=Response(503, text="Service Unavailable"))
        fetcher = SleeperFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "503" in (result.error or "")
        assert result.rows_upserted == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_sources/test_sleeper.py -v
```

Expected: FAIL — `app.data.sources.sleeper` doesn't exist.

- [ ] **Step 4: Implement the fetcher**

Create `backend/app/data/sources/sleeper.py`:

```python
"""Sleeper API fetcher — the master player list."""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player


_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}


class SleeperFetcher:
    name: ClassVar[str] = "sleeper"
    base_url: ClassVar[str] = "https://api.sleeper.app"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
                resp = await client.get("/v1/players/nfl")
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        # Snapshot existing IDs for active-toggling.
        existing_rows = (await db.scalars(select(Player))).all()
        existing_by_id = {p.id: p for p in existing_rows}
        seen_ids: set[str] = set()

        upserted = 0
        for sleeper_id, raw in payload.items():
            position = raw.get("position")
            team = raw.get("team")
            if position not in _FANTASY_POSITIONS or team is None:
                continue

            seen_ids.add(sleeper_id)
            existing = existing_by_id.get(sleeper_id)
            if existing is None:
                existing = Player(id=sleeper_id)
                db.add(existing)

            existing.name = raw.get("full_name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip()
            existing.position = position
            existing.team = team
            existing.age = raw.get("age")
            existing.years_exp = raw.get("years_exp")
            existing.gsis_id = raw.get("gsis_id")
            existing.espn_id = str(raw["espn_id"]) if raw.get("espn_id") is not None else None
            existing.active = True
            upserted += 1

        # Mark anyone not seen as inactive.
        for pid, p in existing_by_id.items():
            if pid not in seen_ids:
                p.active = False

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sources/test_sleeper.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/sources/sleeper.py backend/tests/fixtures/__init__.py backend/tests/fixtures/sleeper_players.json backend/tests/test_sources/test_sleeper.py
git commit -m "feat: Sleeper fetcher — master player list with active toggling and cross-IDs"
```

---

## Task 7: nfl_data_py fetcher — seasonal stats + snap counts (TDD)

**Files:**
- Create: `backend/app/data/sources/nfl_data.py`
- Create: `backend/tests/fixtures/nfl_data_seasonal.csv` (NEW)
- Create: `backend/tests/fixtures/nfl_data_snap_counts.csv` (NEW)
- Create: `backend/tests/test_sources/test_nfl_data.py` (NEW)

- [ ] **Step 1: Create fixture CSVs**

`backend/tests/fixtures/nfl_data_seasonal.csv`:

```csv
player_id,season,player_display_name,position,recent_team,attempts,completions,passing_yards,passing_tds,interceptions,carries,rushing_yards,rushing_tds,targets,receptions,receiving_yards,receiving_tds,games
00-0034796,2025,Josh Allen,QB,BUF,525,360,4180,33,12,95,520,8,0,0,0,0,17
00-0036900,2025,Ja'Marr Chase,WR,CIN,0,0,0,0,0,0,0,0,175,127,1708,17,17
00-0036322,2025,Justin Jefferson,WR,MIN,0,0,0,0,0,0,0,0,154,103,1533,10,17
00-0039169,2025,Bijan Robinson,RB,ATL,0,0,0,0,0,245,1226,11,70,58,431,1,17
00-0034844,2025,Saquon Barkley,RB,PHI,0,0,0,0,0,290,1610,16,45,36,271,0,16
```

`backend/tests/fixtures/nfl_data_snap_counts.csv`:

```csv
player,gsis_id,team,position,offense_snaps,offense_pct
Josh Allen,00-0034796,BUF,QB,1100,1.00
Ja'Marr Chase,00-0036900,CIN,WR,1015,0.92
Justin Jefferson,00-0036322,MIN,WR,1039,0.94
Bijan Robinson,00-0039169,ATL,RB,906,0.82
Saquon Barkley,00-0034844,PHI,RB,818,0.74
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_sources/test_nfl_data.py`:

```python
import pytest
from pathlib import Path
from datetime import date
import pandas as pd

from sqlalchemy import select
from app.models import Player, PlayerStat
from app.data.sources.nfl_data import NflDataFetcher


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def mock_nfl_data(monkeypatch):
    """Make nfl_data_py.import_seasonal_data and import_snap_counts read local CSVs."""
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")

    import app.data.sources.nfl_data as mod
    monkeypatch.setattr(mod, "import_seasonal_data", lambda years: seasonal_df.copy())
    monkeypatch.setattr(mod, "import_snap_counts", lambda years: snap_df.copy())
    # PBP not required for these tests — return empty DataFrame.
    monkeypatch.setattr(mod, "import_pbp_data", lambda years: pd.DataFrame())


@pytest.mark.asyncio
async def test_nfl_data_upserts_seasonal_stats(test_db, mock_nfl_data):
    # Seed a Player so the fetcher has a gsis_id → Player.id mapping.
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", gsis_id="00-0034796"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", gsis_id="00-0036900"))
    await test_db.commit()

    fetcher = NflDataFetcher(season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 2  # only the 2 players we seeded

    allen_stat = await test_db.scalar(
        select(PlayerStat).where(PlayerStat.player_id == "4017", PlayerStat.season == 2025)
    )
    assert allen_stat.pass_yards == 4180.0
    assert allen_stat.pass_tds == 33
    assert allen_stat.rush_tds == 8

    chase_stat = await test_db.scalar(
        select(PlayerStat).where(PlayerStat.player_id == "6794", PlayerStat.season == 2025)
    )
    assert chase_stat.receptions == 127
    assert chase_stat.rec_tds == 17
    assert chase_stat.snap_pct == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_nfl_data_idempotent_on_rerun(test_db, mock_nfl_data):
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", gsis_id="00-0034796"))
    await test_db.commit()

    fetcher = NflDataFetcher(season=2025)
    await fetcher.fetch(test_db)
    await fetcher.fetch(test_db)  # second call

    stats = (await test_db.scalars(
        select(PlayerStat).where(PlayerStat.player_id == "4017", PlayerStat.season == 2025)
    )).all()
    assert len(stats) == 1  # unique constraint holds; one upserted row
    assert stats[0].pass_yards == 4180.0


@pytest.mark.asyncio
async def test_nfl_data_skips_unknown_gsis(test_db, mock_nfl_data):
    """If a CSV row's gsis_id doesn't match any Player.gsis_id, skip silently."""
    # No players seeded
    fetcher = NflDataFetcher(season=2025)
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_sources/test_nfl_data.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Implement the fetcher**

Create `backend/app/data/sources/nfl_data.py`:

```python
"""nfl_data_py fetcher — seasonal stats, snap counts, and PBP-derived fields."""
from __future__ import annotations

from datetime import datetime, date
from typing import ClassVar

from nfl_data_py import import_seasonal_data, import_snap_counts, import_pbp_data
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player, PlayerStat


class NflDataFetcher:
    name: ClassVar[str] = "nfl_data_py"

    def __init__(self, season: int):
        self.season = season

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        try:
            seasonal_df = import_seasonal_data([self.season])
            snap_df = import_snap_counts([self.season])
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        # Build gsis_id → Player.id map.
        players = (await db.scalars(select(Player).where(Player.gsis_id.is_not(None)))).all()
        gsis_to_pid = {p.gsis_id: p.id for p in players}

        # Build gsis_id → snap_pct map from snap_df.
        snap_by_gsis: dict[str, float] = {}
        if not snap_df.empty:
            # snap_df has multiple rows per player (one per game). Aggregate to season pct.
            aggregated = snap_df.groupby("gsis_id")["offense_pct"].mean()
            snap_by_gsis = aggregated.to_dict()

        # Index existing stats by (player_id, season) to allow upsert.
        existing_stats = (await db.scalars(
            select(PlayerStat).where(PlayerStat.season == self.season)
        )).all()
        stats_by_pid = {s.player_id: s for s in existing_stats}

        upserted = 0
        for _, row in seasonal_df.iterrows():
            gsis = row.get("player_id")
            pid = gsis_to_pid.get(gsis)
            if pid is None:
                continue

            stat = stats_by_pid.get(pid)
            if stat is None:
                stat = PlayerStat(player_id=pid, season=self.season)
                db.add(stat)
                stats_by_pid[pid] = stat

            stat.targets = int(row.get("targets") or 0)
            stat.receptions = int(row.get("receptions") or 0)
            stat.rec_yards = float(row.get("receiving_yards") or 0)
            stat.rec_tds = int(row.get("receiving_tds") or 0)
            stat.rush_att = int(row.get("carries") or 0)
            stat.rush_yards = float(row.get("rushing_yards") or 0)
            stat.rush_tds = int(row.get("rushing_tds") or 0)
            stat.pass_att = int(row.get("attempts") or 0)
            stat.pass_yards = float(row.get("passing_yards") or 0)
            stat.pass_tds = int(row.get("passing_tds") or 0)
            stat.interceptions = int(row.get("interceptions") or 0)
            stat.games_played = int(row.get("games") or 0)
            stat.actual_tds = stat.rec_tds + stat.rush_tds + stat.pass_tds

            if gsis in snap_by_gsis:
                stat.snap_pct = float(snap_by_gsis[gsis])

            upserted += 1

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sources/test_nfl_data.py -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/sources/nfl_data.py backend/tests/fixtures/nfl_data_seasonal.csv backend/tests/fixtures/nfl_data_snap_counts.csv backend/tests/test_sources/test_nfl_data.py
git commit -m "feat: nfl_data_py fetcher — seasonal stats and snap counts"
```

---

## Task 8: nfl_data_py PBP-derived stats (TDD)

**Files:**
- Modify: `backend/app/data/sources/nfl_data.py`
- Create: `backend/tests/fixtures/nfl_data_pbp.csv` (NEW)
- Modify: `backend/tests/test_sources/test_nfl_data.py` (add tests)

- [ ] **Step 1: Create PBP fixture**

`backend/tests/fixtures/nfl_data_pbp.csv` — minimum columns to compute expected_tds and red_zone_looks:

```csv
play_id,game_id,season,yardline_100,play_type,td_prob,rusher_player_id,receiver_player_id,touchdown,rush_touchdown,pass_touchdown
1,1,2025,15,run,0.18,00-0039169,,1,1,0
2,1,2025,18,pass,0.22,,00-0036900,1,0,1
3,1,2025,80,run,0.01,00-0039169,,0,0,0
4,1,2025,10,pass,0.45,,00-0036900,0,0,0
5,1,2025,5,run,0.62,00-0039169,,1,1,0
6,1,2025,2,pass,0.71,,00-0036900,1,0,1
7,1,2025,12,run,0.20,00-0034844,,0,0,0
8,1,2025,15,run,0.18,00-0034844,,1,1,0
9,2,2025,8,pass,0.50,,00-0036322,0,0,0
10,2,2025,4,pass,0.65,,00-0036322,1,0,1
```

Expected after processing (red zone = yardline_100 ≤ 20):
- `00-0039169` (Robinson): red_zone_looks = 3 (rows 1, 3 excluded — 3 is outside RZ, so actually rows 1, 5, 8 → wait, let me recount. Rows where rusher_player_id=`00-0039169` AND yardline_100<=20: row 1 (yard 15), row 5 (yard 5) → 2 plays. Hmm. Let me redo:

Actually I need this cleaner. Let me restructure mentally:
- Robinson rushes: row 1 (y=15, td_prob=0.18, TD), row 3 (y=80, not RZ), row 5 (y=5, td_prob=0.62, TD)
- Robinson RZ looks: 2 (rows 1, 5)
- Robinson expected_tds: 0.18 + 0.62 = 0.80
- Robinson actual_tds (from rush_touchdown col): 1 + 0 + 1 = 2 (but we already compute this from seasonal data)

- Chase pass targets: row 2 (y=18, td_prob=0.22, TD), row 4 (y=10, td_prob=0.45, no TD), row 6 (y=2, td_prob=0.71, TD)
- Chase RZ looks: 3
- Chase expected_tds: 0.22 + 0.45 + 0.71 = 1.38

- Barkley rushes: row 7 (y=12, td_prob=0.20), row 8 (y=15, td_prob=0.18, TD)
- Barkley RZ looks: 2
- Barkley expected_tds: 0.20 + 0.18 = 0.38

- Jefferson targets: row 9 (y=8, td_prob=0.50), row 10 (y=4, td_prob=0.65, TD)
- Jefferson RZ looks: 2
- Jefferson expected_tds: 0.50 + 0.65 = 1.15

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_sources/test_nfl_data.py`:

```python
@pytest.fixture
def mock_nfl_data_with_pbp(monkeypatch):
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")

    import app.data.sources.nfl_data as mod
    monkeypatch.setattr(mod, "import_seasonal_data", lambda years: seasonal_df.copy())
    monkeypatch.setattr(mod, "import_snap_counts", lambda years: snap_df.copy())
    monkeypatch.setattr(mod, "import_pbp_data", lambda years: pbp_df.copy())


@pytest.mark.asyncio
async def test_nfl_data_computes_pbp_derived_fields(test_db, mock_nfl_data_with_pbp):
    test_db.add(Player(id="8112", name="Bijan Robinson", position="RB", team="ATL", gsis_id="00-0039169"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", gsis_id="00-0036900"))
    test_db.add(Player(id="4866", name="Saquon Barkley", position="RB", team="PHI", gsis_id="00-0034844"))
    test_db.add(Player(id="6786", name="Justin Jefferson", position="WR", team="MIN", gsis_id="00-0036322"))
    await test_db.commit()

    fetcher = NflDataFetcher(season=2025)
    await fetcher.fetch(test_db)

    bijan = await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "8112"))
    assert bijan.red_zone_looks == 2
    assert bijan.expected_tds == pytest.approx(0.80, abs=0.01)

    chase = await test_db.scalar(select(PlayerStat).where(PlayerStat.player_id == "6794"))
    assert chase.red_zone_looks == 3
    assert chase.expected_tds == pytest.approx(1.38, abs=0.01)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_sources/test_nfl_data.py::test_nfl_data_computes_pbp_derived_fields -v
```

Expected: FAIL — PBP processing not implemented yet (expected_tds and red_zone_looks are None).

- [ ] **Step 4: Add PBP processing to `nfl_data.py`**

In `backend/app/data/sources/nfl_data.py`, between the existing snap_pct loop and `await db.commit()`, add PBP processing. The full updated `fetch` method:

```python
    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        try:
            seasonal_df = import_seasonal_data([self.season])
            snap_df = import_snap_counts([self.season])
            pbp_df = import_pbp_data([self.season])
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        players = (await db.scalars(select(Player).where(Player.gsis_id.is_not(None)))).all()
        gsis_to_pid = {p.gsis_id: p.id for p in players}

        snap_by_gsis: dict[str, float] = {}
        if not snap_df.empty:
            aggregated = snap_df.groupby("gsis_id")["offense_pct"].mean()
            snap_by_gsis = aggregated.to_dict()

        # PBP-derived: red_zone_looks and expected_tds per gsis_id.
        rz_looks: dict[str, int] = {}
        xtds: dict[str, float] = {}
        if not pbp_df.empty:
            rz = pbp_df[pbp_df["yardline_100"] <= 20]
            for _, play in rz.iterrows():
                td_prob = float(play.get("td_prob") or 0)
                rusher = play.get("rusher_player_id")
                receiver = play.get("receiver_player_id")
                if isinstance(rusher, str) and rusher:
                    rz_looks[rusher] = rz_looks.get(rusher, 0) + 1
                    xtds[rusher] = xtds.get(rusher, 0.0) + td_prob
                if isinstance(receiver, str) and receiver:
                    rz_looks[receiver] = rz_looks.get(receiver, 0) + 1
                    xtds[receiver] = xtds.get(receiver, 0.0) + td_prob

        existing_stats = (await db.scalars(
            select(PlayerStat).where(PlayerStat.season == self.season)
        )).all()
        stats_by_pid = {s.player_id: s for s in existing_stats}

        upserted = 0
        for _, row in seasonal_df.iterrows():
            gsis = row.get("player_id")
            pid = gsis_to_pid.get(gsis)
            if pid is None:
                continue

            stat = stats_by_pid.get(pid)
            if stat is None:
                stat = PlayerStat(player_id=pid, season=self.season)
                db.add(stat)
                stats_by_pid[pid] = stat

            stat.targets = int(row.get("targets") or 0)
            stat.receptions = int(row.get("receptions") or 0)
            stat.rec_yards = float(row.get("receiving_yards") or 0)
            stat.rec_tds = int(row.get("receiving_tds") or 0)
            stat.rush_att = int(row.get("carries") or 0)
            stat.rush_yards = float(row.get("rushing_yards") or 0)
            stat.rush_tds = int(row.get("rushing_tds") or 0)
            stat.pass_att = int(row.get("attempts") or 0)
            stat.pass_yards = float(row.get("passing_yards") or 0)
            stat.pass_tds = int(row.get("passing_tds") or 0)
            stat.interceptions = int(row.get("interceptions") or 0)
            stat.games_played = int(row.get("games") or 0)
            stat.actual_tds = stat.rec_tds + stat.rush_tds + stat.pass_tds

            if gsis in snap_by_gsis:
                stat.snap_pct = float(snap_by_gsis[gsis])
            if gsis in rz_looks:
                stat.red_zone_looks = rz_looks[gsis]
            if gsis in xtds:
                stat.expected_tds = round(xtds[gsis], 3)

            upserted += 1

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sources/test_nfl_data.py -v
```

Expected: all 4 tests pass (3 from Task 7 + 1 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/sources/nfl_data.py backend/tests/fixtures/nfl_data_pbp.csv backend/tests/test_sources/test_nfl_data.py
git commit -m "feat: nfl_data_py PBP — compute expected_tds and red_zone_looks"
```

---

## Task 9: ESPN fetcher (TDD)

**Files:**
- Create: `backend/app/data/sources/espn.py`
- Create: `backend/tests/fixtures/espn_projections.json` (NEW)
- Create: `backend/tests/test_sources/test_espn.py` (NEW)

> NOTE: ESPN's public-but-unofficial fantasy API is keyed on internal stat IDs. The relevant ones for season projections in 2026 are:
> - `appliedStatTotal` under each player's `playerPoolEntry.player.stats` array
> - Each stat entry has `statSourceId` (0 = actuals, **1 = projections**) and `scoringPeriodId` (0 = full season)
> - Scoring format selection isn't a separate query — ESPN returns one "default" projection and we compute PPR/half/standard adjustments client-side using receptions
>
> For this plan, we adopt this simplification: ESPN returns a single `projected_points` (whatever ESPN's default scoring is — typically PPR), and the fetcher records it under all three formats (`standard`, `half_ppr`, `ppr`). Real-world correction (subtracting 0.5/1.0 receptions for non-PPR) is a follow-up; this matches the spec's note "TE Premium not supported by ESPN → write to ppr only".
>
> Pragmatic implementation: write the same value to all three formats per ESPN row. The blend layer can refine later.

- [ ] **Step 1: Create the fixture**

`backend/tests/fixtures/espn_projections.json`:

```json
{
  "players": [
    {
      "id": 3918298,
      "player": {
        "fullName": "Josh Allen",
        "defaultPositionId": 1,
        "stats": [
          {"statSourceId": 1, "scoringPeriodId": 0, "seasonId": 2026, "appliedTotal": 388.5}
        ]
      }
    },
    {
      "id": 4362628,
      "player": {
        "fullName": "Ja'Marr Chase",
        "defaultPositionId": 4,
        "stats": [
          {"statSourceId": 1, "scoringPeriodId": 0, "seasonId": 2026, "appliedTotal": 346.0}
        ]
      }
    },
    {
      "id": 4262921,
      "player": {
        "fullName": "Justin Jefferson",
        "defaultPositionId": 4,
        "stats": [
          {"statSourceId": 1, "scoringPeriodId": 0, "seasonId": 2026, "appliedTotal": 318.0}
        ]
      }
    },
    {
      "id": 4430807,
      "player": {
        "fullName": "Bijan Robinson",
        "defaultPositionId": 2,
        "stats": [
          {"statSourceId": 1, "scoringPeriodId": 0, "seasonId": 2026, "appliedTotal": 308.0}
        ]
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_sources/test_espn.py`:

```python
import json
import pytest
import respx
from httpx import Response
from pathlib import Path

from sqlalchemy import select
from app.models import Player, Projection
from app.data.sources.espn import EspnFetcher


FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "espn_projections.json").read_text())


@pytest.fixture
def mock_espn():
    with respx.mock(base_url="https://fantasy.espn.com") as router:
        router.get(url__regex=r"/apis/v3/games/ffl/seasons/.*/segments/0/leaguedefaults/3.*").mock(
            return_value=Response(200, json=FIXTURE)
        )
        yield router


@pytest.mark.asyncio
async def test_espn_upserts_projections(test_db, mock_espn):
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", espn_id="3918298"))
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN", espn_id="4362628"))
    await test_db.commit()

    fetcher = EspnFetcher(season=2026)
    result = await fetcher.fetch(test_db)
    assert result.success

    # Each matched player gets 3 projection rows (standard, half_ppr, ppr).
    # 2 matched players × 3 formats = 6 rows.
    assert result.rows_upserted == 6

    rows = (await test_db.scalars(
        select(Projection).where(Projection.player_id == "4017", Projection.source == "espn")
    )).all()
    formats = {r.scoring_format for r in rows}
    assert formats == {"standard", "half_ppr", "ppr"}
    for r in rows:
        assert r.projected_points == pytest.approx(388.5)


@pytest.mark.asyncio
async def test_espn_skips_unknown_espn_id(test_db, mock_espn):
    # No players seeded
    fetcher = EspnFetcher(season=2026)
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_espn_idempotent(test_db, mock_espn):
    test_db.add(Player(id="4017", name="Josh Allen", position="QB", team="BUF", espn_id="3918298"))
    await test_db.commit()

    fetcher = EspnFetcher(season=2026)
    await fetcher.fetch(test_db)
    await fetcher.fetch(test_db)

    rows = (await test_db.scalars(
        select(Projection).where(Projection.player_id == "4017", Projection.source == "espn")
    )).all()
    assert len(rows) == 3  # one per format, not 6


@pytest.mark.asyncio
async def test_espn_handles_http_error(test_db):
    with respx.mock(base_url="https://fantasy.espn.com") as router:
        router.get(url__regex=r"/apis/v3/games/ffl/.*").mock(return_value=Response(503))
        fetcher = EspnFetcher(season=2026)
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "503" in (result.error or "")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_sources/test_espn.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Implement the fetcher**

Create `backend/app/data/sources/espn.py`:

```python
"""ESPN unofficial fantasy API fetcher — current-season projections."""
from __future__ import annotations

from datetime import datetime, date
from typing import ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player, Projection


_ESPN_FORMATS = ("standard", "half_ppr", "ppr")  # we write the same projection to all three


class EspnFetcher:
    name: ClassVar[str] = "espn"
    base_url: ClassVar[str] = "https://fantasy.espn.com"

    def __init__(self, season: int):
        self.season = season

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        url = f"/apis/v3/games/ffl/seasons/{self.season}/segments/0/leaguedefaults/3"
        params = {"view": "kona_player_info"}
        headers = {"x-fantasy-filter": '{"players":{"limit":1500,"sortPercOwned":{"sortAsc":false,"sortPriority":1}}}'}

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        players_in = payload.get("players") or []

        # Build espn_id → Player map.
        all_players = (await db.scalars(select(Player).where(Player.espn_id.is_not(None)))).all()
        espn_to_pid = {p.espn_id: p.id for p in all_players}

        # Index existing ESPN projections.
        existing = (await db.scalars(
            select(Projection).where(Projection.source == "espn")
        )).all()
        existing_key = {(p.player_id, p.scoring_format): p for p in existing}

        today = date.today()
        upserted = 0
        for entry in players_in:
            espn_id = str(entry.get("id"))
            pid = espn_to_pid.get(espn_id)
            if pid is None:
                continue

            stats = entry.get("player", {}).get("stats") or []
            projection_pts = None
            for s in stats:
                if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0 and s.get("seasonId") == self.season:
                    projection_pts = float(s.get("appliedTotal") or 0)
                    break
            if projection_pts is None:
                continue

            for fmt in _ESPN_FORMATS:
                row = existing_key.get((pid, fmt))
                if row is None:
                    row = Projection(player_id=pid, source="espn", scoring_format=fmt,
                                     projected_points=projection_pts, last_updated=today)
                    db.add(row)
                    existing_key[(pid, fmt)] = row
                else:
                    row.projected_points = projection_pts
                    row.last_updated = today
                upserted += 1

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sources/test_espn.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/sources/espn.py backend/tests/fixtures/espn_projections.json backend/tests/test_sources/test_espn.py
git commit -m "feat: ESPN unofficial API fetcher — current-season projections"
```

---

## Task 10: FantasyPros fetcher (TDD)

**Files:**
- Create: `backend/app/data/sources/fantasypros.py`
- Create: `backend/tests/fixtures/fantasypros_projections_wr.html` (NEW)
- Create: `backend/tests/fixtures/fantasypros_adp_ppr.html` (NEW)
- Create: `backend/tests/test_sources/test_fantasypros.py` (NEW)

- [ ] **Step 1: Create fixture HTML**

`backend/tests/fixtures/fantasypros_projections_wr.html` — minimal HTML matching FantasyPros's structure (a `<table id="data">` with player rows):

```html
<!DOCTYPE html>
<html>
<body>
<table id="data">
  <thead><tr><th>Player</th><th>REC</th><th>YDS</th><th>TDS</th><th>FPTS</th></tr></thead>
  <tbody>
    <tr><td><a>Ja'Marr Chase</a> <small>CIN</small></td><td>108</td><td>1450</td><td>11</td><td>340.5</td></tr>
    <tr><td><a>Justin Jefferson</a> <small>MIN</small></td><td>105</td><td>1410</td><td>9</td><td>312.0</td></tr>
    <tr><td><a>Mystery Player</a> <small>XXX</small></td><td>50</td><td>600</td><td>3</td><td>120.0</td></tr>
  </tbody>
</table>
</body>
</html>
```

`backend/tests/fixtures/fantasypros_adp_ppr.html`:

```html
<!DOCTYPE html>
<html>
<body>
<table id="data">
  <thead><tr><th>Rank</th><th>Player</th><th>POS</th><th>ADP</th></tr></thead>
  <tbody>
    <tr><td>1</td><td><a>Ja'Marr Chase</a> <small>CIN</small></td><td>WR1</td><td>1.5</td></tr>
    <tr><td>2</td><td><a>Justin Jefferson</a> <small>MIN</small></td><td>WR2</td><td>2.5</td></tr>
  </tbody>
</table>
</body>
</html>
```

> NOTE: real FantasyPros HTML has substantially more markup and dynamic attribution. The implementer should refresh these fixtures with real responses (saved via `curl`) once the parser stabilizes; for the plan we only need a representative shape.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_sources/test_fantasypros.py`:

```python
import pytest
import respx
from httpx import Response
from pathlib import Path

from sqlalchemy import select
from app.models import Player, Projection, ADPData
from app.data.sources.fantasypros import FantasyProsFetcher


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def mock_fantasypros():
    with respx.mock(base_url="https://www.fantasypros.com") as router:
        # Only WR projections + PPR ADP for this minimal fixture set.
        router.get(url__regex=r"/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_projections_wr.html").read_text())
        )
        router.get(url__regex=r"/nfl/projections/(qb|rb|te)\.php.*").mock(
            return_value=Response(200, text="<html><body><table id='data'><tbody></tbody></table></body></html>")
        )
        router.get(url__regex=r"/nfl/adp/ppr\.php").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_adp_ppr.html").read_text())
        )
        router.get(url__regex=r"/nfl/adp/(overall|half-point-ppr)\.php").mock(
            return_value=Response(200, text="<html><body><table id='data'><tbody></tbody></table></body></html>")
        )
        yield router


@pytest.mark.asyncio
async def test_fantasypros_matches_players_and_upserts_projections(test_db, mock_fantasypros):
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    test_db.add(Player(id="6786", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()

    fetcher = FantasyProsFetcher()
    result = await fetcher.fetch(test_db)
    assert result.success

    # 2 matched WR projections (Chase, Jefferson) + 2 ADP rows = 4 upserts.
    # Mystery Player doesn't match → not upserted.
    assert result.rows_upserted >= 4

    chase_proj = await test_db.scalar(
        select(Projection).where(
            Projection.player_id == "6794",
            Projection.source == "fantasypros",
            Projection.scoring_format == "ppr",
        )
    )
    assert chase_proj.projected_points == pytest.approx(340.5)

    chase_adp = await test_db.scalar(
        select(ADPData).where(
            ADPData.player_id == "6794",
            ADPData.format == "ppr",
            ADPData.adp_source == "fantasypros",
        )
    )
    assert chase_adp.adp == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_fantasypros_logs_unmatched(test_db, mock_fantasypros, caplog):
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    # Don't add Jefferson — both Jefferson and "Mystery Player" should be unmatched.
    await test_db.commit()

    fetcher = FantasyProsFetcher()
    with caplog.at_level("WARNING"):
        await fetcher.fetch(test_db)
    log_text = caplog.text
    assert "Justin Jefferson" in log_text or "Mystery Player" in log_text
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_sources/test_fantasypros.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Implement the fetcher**

Create `backend/app/data/sources/fantasypros.py`:

```python
"""FantasyPros scraper — consensus projections + ADP. Resolves players via fuzzy match."""
from __future__ import annotations

import logging
import re
from datetime import datetime, date
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.matching import fuzzy_match
from app.data.sources.base import SourceResult
from app.models import Player, Projection, ADPData


logger = logging.getLogger(__name__)

# Position → scraping URL slug; FantasyPros uses "wr.php", "rb.php" etc.
_POSITIONS = ("qb", "rb", "wr", "te")
# Format → URL slug
_ADP_FORMATS = {"standard": "overall", "half_ppr": "half-point-ppr", "ppr": "ppr"}


class FantasyProsFetcher:
    name: ClassVar[str] = "fantasypros"
    base_url: ClassVar[str] = "https://www.fantasypros.com"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        today = date.today()
        upserted = 0

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0,
                                          headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"}) as client:
                # Pull projections for each position × each scoring format.
                # FantasyPros has one URL per (position, scoring_format=STD|HALF|PPR).
                # The query param is "scoring".
                for position in _POSITIONS:
                    for ff_format, ff_param in [("standard", "STD"), ("half_ppr", "HALF"), ("ppr", "PPR")]:
                        resp = await client.get(f"/nfl/projections/{position}.php", params={"scoring": ff_param})
                        resp.raise_for_status()
                        upserted += await self._parse_projections(
                            db, resp.text, position.upper(), ff_format, today
                        )

                # ADP per format
                for adp_format, slug in _ADP_FORMATS.items():
                    resp = await client.get(f"/nfl/adp/{slug}.php")
                    resp.raise_for_status()
                    upserted += await self._parse_adp(db, resp.text, adp_format, today)
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)

    async def _parse_projections(
        self, db: AsyncSession, html: str, position: str, scoring_format: str, today: date,
    ) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="data")
        if table is None:
            return 0

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            name, team = self._parse_player_cell(cells[0])
            if not name:
                continue
            # Last cell is the points total (FPTS).
            try:
                points = float(cells[-1].get_text(strip=True).replace(",", ""))
            except (ValueError, IndexError):
                continue

            player = await fuzzy_match(db, name, team, position)
            if player is None:
                logger.warning("[fantasypros] unmatched %s | %s %s", position, name, team or "?")
                continue

            existing = await db.scalar(
                select(Projection).where(
                    Projection.player_id == player.id,
                    Projection.source == "fantasypros",
                    Projection.scoring_format == scoring_format,
                )
            )
            if existing is None:
                db.add(Projection(player_id=player.id, source="fantasypros",
                                  scoring_format=scoring_format, projected_points=points,
                                  last_updated=today))
            else:
                existing.projected_points = points
                existing.last_updated = today
            upserted += 1
        return upserted

    async def _parse_adp(self, db: AsyncSession, html: str, fmt: str, today: date) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="data")
        if table is None:
            return 0

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            name, team = self._parse_player_cell(cells[1])
            pos_text = cells[2].get_text(strip=True)
            # Strip trailing tier digits, e.g. "WR1" → "WR"
            position = re.sub(r"\d+$", "", pos_text)
            try:
                adp_val = float(cells[3].get_text(strip=True))
            except ValueError:
                continue
            if not name:
                continue

            player = await fuzzy_match(db, name, team, position)
            if player is None:
                logger.warning("[fantasypros adp] unmatched %s %s | %s", fmt, name, team or "?")
                continue

            existing = await db.scalar(
                select(ADPData).where(
                    ADPData.player_id == player.id,
                    ADPData.format == fmt,
                    ADPData.adp_source == "fantasypros",
                )
            )
            if existing is None:
                db.add(ADPData(player_id=player.id, format=fmt, adp=adp_val,
                               adp_source="fantasypros", last_updated=today))
            else:
                existing.adp = adp_val
                existing.last_updated = today
            upserted += 1
        return upserted

    @staticmethod
    def _parse_player_cell(cell) -> tuple[str, str]:
        """Pull (name, team) from a FantasyPros player cell. Name is the <a> text, team is the <small>."""
        a = cell.find("a")
        small = cell.find("small")
        name = a.get_text(strip=True) if a else cell.get_text(strip=True)
        team = small.get_text(strip=True) if small else ""
        return name, team
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sources/test_fantasypros.py -v
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/sources/fantasypros.py backend/tests/fixtures/fantasypros_projections_wr.html backend/tests/fixtures/fantasypros_adp_ppr.html backend/tests/test_sources/test_fantasypros.py
git commit -m "feat: FantasyPros scraper — projections + ADP via fuzzy match"
```

---

## Task 11: Refresh orchestrator (TDD)

**Files:**
- Modify: `backend/app/data/fetcher.py` (replaces existing stub)
- Create: `backend/tests/test_refresh.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_refresh.py`:

```python
import json
import pytest
import respx
import pandas as pd
from httpx import Response
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from app.models import Player, PlayerStat, Projection, DataSourceStatus
from app.data.fetcher import DataFetcher


FIXTURES = Path(__file__).parent / "fixtures"
SLEEPER_FIXTURE = json.loads((FIXTURES / "sleeper_players.json").read_text())
ESPN_FIXTURE = json.loads((FIXTURES / "espn_projections.json").read_text())


@pytest.fixture
def mock_all_sources(monkeypatch):
    """Wire all 4 sources to fixture data."""
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")

    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/v1/players/nfl").mock(
            return_value=Response(200, json=SLEEPER_FIXTURE)
        )
        router.get(url__regex=r"https://fantasy\.espn\.com/apis/v3/games/ffl/.*").mock(
            return_value=Response(200, json=ESPN_FIXTURE)
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_projections_wr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/(qb|rb|te)\.php.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/adp/ppr\.php").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_adp_ppr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/adp/(overall|half-point-ppr)\.php").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        yield router


@pytest.mark.asyncio
async def test_refresh_runs_all_sources(test_db, mock_all_sources):
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)

    assert set(results.keys()) == {"sleeper", "nfl_data_py", "espn", "fantasypros"}
    for src, r in results.items():
        assert r["last_error"] is None, f"{src} unexpectedly failed: {r['last_error']}"

    # Sanity: Sleeper inserted players, nfl_data populated stats, ESPN+FP populated projections.
    players = (await test_db.scalars(select(Player))).all()
    assert len(players) >= 5

    stats = (await test_db.scalars(select(PlayerStat))).all()
    assert len(stats) >= 2

    projections = (await test_db.scalars(select(Projection))).all()
    assert len(projections) >= 2


@pytest.mark.asyncio
async def test_refresh_persists_status_rows(test_db, mock_all_sources):
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    await fetcher.refresh_all(test_db)

    statuses = (await test_db.scalars(select(DataSourceStatus))).all()
    sources = {s.source for s in statuses}
    assert sources == {"sleeper", "nfl_data_py", "espn", "fantasypros"}
    for s in statuses:
        assert s.last_attempted is not None
        assert s.last_updated is not None  # all succeeded
        assert s.last_error is None


@pytest.mark.asyncio
async def test_refresh_continues_when_one_source_fails(test_db, monkeypatch):
    # Sleeper succeeds, ESPN fails, others get fixtures.
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")
    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(200, json=SLEEPER_FIXTURE))
        router.get(url__regex=r"https://fantasy\.espn\.com/.*").mock(return_value=Response(503))
        router.get(url__regex=r"https://www\.fantasypros\.com/.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )

        fetcher = DataFetcher(prior_season=2025, current_season=2026)
        results = await fetcher.refresh_all(test_db)

    # Sleeper, nfl_data, fantasypros succeed; ESPN fails.
    assert results["sleeper"]["last_error"] is None
    assert results["nfl_data_py"]["last_error"] is None
    assert results["fantasypros"]["last_error"] is None
    assert results["espn"]["last_error"] is not None and "503" in results["espn"]["last_error"]

    # ESPN status row has last_error set but last_updated is None.
    espn_status = await test_db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == "espn"))
    assert espn_status.last_updated is None
    assert "503" in espn_status.last_error


@pytest.mark.asyncio
async def test_refresh_returns_skipped_when_sleeper_fails(test_db):
    """If Sleeper fails, downstream sources need its player map — they're skipped."""
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(503))

        fetcher = DataFetcher(prior_season=2025, current_season=2026)
        results = await fetcher.refresh_all(test_db)

    assert "503" in results["sleeper"]["last_error"]
    for src in ("nfl_data_py", "espn", "fantasypros"):
        assert "skipped" in (results[src]["last_error"] or "").lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_refresh.py -v
```

Expected: FAIL — current `DataFetcher.refresh_all` is a stub returning dict literals.

- [ ] **Step 3: Implement the orchestrator**

Replace `backend/app/data/fetcher.py` entirely:

```python
"""Top-level data refresh orchestrator. Wires the four source fetchers together."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.data.sources.sleeper import SleeperFetcher
from app.data.sources.nfl_data import NflDataFetcher
from app.data.sources.espn import EspnFetcher
from app.data.sources.fantasypros import FantasyProsFetcher
from app.data.status import upsert_status, get_all_status


logger = logging.getLogger(__name__)


class DataFetcher:
    """Orchestrates all four sources. Sleeper runs first; downstream sources run in parallel."""

    def __init__(self, prior_season: int, current_season: int):
        self.prior_season = prior_season
        self.current_season = current_season

    async def refresh_all(self, db: AsyncSession) -> dict[str, dict]:
        # 1. Sleeper first — provides the player table and cross-IDs that all downstream sources need.
        sleeper_result = await SleeperFetcher().fetch(db)
        await self._persist(db, sleeper_result)

        if not sleeper_result.success:
            # Downstream sources can't run without the player table.
            skipped_at = datetime.utcnow()
            for name in ("nfl_data_py", "espn", "fantasypros"):
                skipped = SourceResult(
                    source=name, rows_upserted=0, last_attempted=skipped_at,
                    success=False, error="skipped — sleeper refresh failed",
                )
                await self._persist(db, skipped)
            await db.commit()
            return await get_all_status(db)

        # 2. Downstream sources in parallel.
        nfl_task = NflDataFetcher(self.prior_season).fetch(db)
        espn_task = EspnFetcher(self.current_season).fetch(db)
        fp_task = FantasyProsFetcher().fetch(db)

        results = await asyncio.gather(nfl_task, espn_task, fp_task, return_exceptions=True)

        names = ("nfl_data_py", "espn", "fantasypros")
        for name, r in zip(names, results):
            if isinstance(r, BaseException):
                wrapped = SourceResult(
                    source=name, rows_upserted=0, last_attempted=datetime.utcnow(),
                    success=False, error=str(r),
                )
                await self._persist(db, wrapped)
            else:
                await self._persist(db, r)

        await db.commit()
        return await get_all_status(db)

    @staticmethod
    async def _persist(db: AsyncSession, result: SourceResult) -> None:
        await upsert_status(
            db,
            source=result.source,
            last_attempted=result.last_attempted,
            success=result.success,
            rows_upserted=result.rows_upserted,
            error=result.error,
        )


# Singleton consumed by the API + scheduler. Wraps with sensible default seasons.
class _DefaultFetcher(DataFetcher):
    def __init__(self):
        # Prior season = current year - 1. The API layer can override via /api/data/refresh body.
        now = datetime.utcnow()
        super().__init__(prior_season=now.year - 1, current_season=now.year)

    async def last_updated(self, db: AsyncSession) -> dict:
        return await get_all_status(db)


fetcher = _DefaultFetcher()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_refresh.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
pytest -v 2>&1 | tail -10
```

Expected: all tests pass (Plan 1 + new Plan 2).

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/fetcher.py backend/tests/test_refresh.py
git commit -m "feat: DataFetcher orchestrator — Sleeper-first, then parallel downstream sources"
```

---

## Task 12: PlayerContext.actual_tds_above_expected + 2 new built-in rules (TDD)

**Files:**
- Modify: `backend/app/engine/rules.py`
- Modify: `backend/app/engine/builtin_rules.py`
- Modify: `backend/app/api/generate.py`
- Modify: `backend/tests/test_rules.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_rules.py`:

```python
from app.engine.builtin_rules import BUILTIN_RULES


def test_builtin_rules_count_is_18():
    """Spec calls for 18 built-in rules at launch."""
    assert len(BUILTIN_RULES) == 18


def test_td_regression_positive_fires_above_threshold():
    rule = next(r for r in BUILTIN_RULES if r.name == "TD Regression (positive)")
    ctx = make_ctx(actual_tds_above_expected=4.0)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score < 100.0  # multiplier < 1.0


def test_td_regression_positive_does_not_fire_below_threshold():
    rule = next(r for r in BUILTIN_RULES if r.name == "TD Regression (positive)")
    ctx = make_ctx(actual_tds_above_expected=2.0)  # below threshold of 3.0
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "TD Regression (positive)" not in result.rules_applied


def test_red_zone_premium_fires_above_25():
    rule = next(r for r in BUILTIN_RULES if r.name == "Red Zone Usage Premium")
    ctx = make_ctx(red_zone_looks=30)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score > 100.0


def test_red_zone_premium_skipped_when_none():
    rule = next(r for r in BUILTIN_RULES if r.name == "Red Zone Usage Premium")
    ctx = make_ctx(red_zone_looks=None)
    result = apply_rules(100.0, ctx, [rule])
    assert result.adjusted_score == 100.0
    assert "Red Zone Usage Premium" not in result.rules_applied
```

> NOTE: this assumes `tests/test_rules.py` already has a `make_ctx(**overrides)` helper that builds a `PlayerContext` with sensible defaults. If it doesn't, add this near the top of the file:
>
> ```python
> def make_ctx(**overrides) -> PlayerContext:
>     defaults = dict(
>         player_id="p1", position="WR", age=27,
>         snap_pct=None, carry_share=None, target_share=None,
>         games_played=17, years_exp=4, adp=None,
>         projected_score=100.0, new_team=False, new_coach=False,
>         actual_tds=None, expected_tds=None, actual_tds_above_expected=None,
>         red_zone_looks=None,
>     )
>     defaults.update(overrides)
>     return PlayerContext(**defaults)
> ```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_rules.py -v -k "td_regression or red_zone_premium or builtin_rules_count"
```

Expected: FAIL — `PlayerContext` has no `actual_tds_above_expected` or `red_zone_looks` field, and the new rules don't exist.

- [ ] **Step 3: Add fields to `PlayerContext`**

In `backend/app/engine/rules.py`, the updated `PlayerContext` dataclass:

```python
@dataclass
class PlayerContext:
    player_id: str
    position: str
    age: Optional[int]
    snap_pct: Optional[float]
    carry_share: Optional[float]
    target_share: Optional[float]
    games_played: Optional[int]
    years_exp: int
    adp: Optional[float]
    projected_score: float
    new_team: bool
    new_coach: bool
    actual_tds: Optional[int]
    expected_tds: Optional[float]
    actual_tds_above_expected: Optional[float]  # NEW
    red_zone_looks: Optional[int]  # NEW
```

- [ ] **Step 4: Add the 2 new rules**

Plan 1 ended with 16 rules. Adding these 2 brings the total to 18, matching the design spec.

In `backend/app/engine/builtin_rules.py`, append to the `BUILTIN_RULES` list:

```python
Rule(
    name="TD Regression (positive)",
    conditions=[RuleCondition(field="actual_tds_above_expected", operator=">=", value=3.0)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.90),
),
Rule(
    name="Red Zone Usage Premium",
    conditions=[RuleCondition(field="red_zone_looks", operator=">=", value=25)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.07),
),
```

Rationale: positive TD regression catches the players who scored more TDs than their red-zone opportunity implied last year (luck-driven, mean-reverts down). The symmetric "negative TD regression" boost is intentionally deferred — fantasy projections from ESPN/FantasyPros already implicitly correct for under-scoring, so doubling the boost would over-weight that signal. Can be added later as a 19th rule if desired.

- [ ] **Step 5: Update existing rules tests that use `PlayerContext`**

Find anywhere in `backend/tests/test_rules.py` and `backend/app/api/generate.py` that constructs `PlayerContext` directly. Add the two new fields with `None` defaults wherever found.

Specifically in `backend/app/api/generate.py`, find the `ctx = PlayerContext(...)` block inside `_run_generate` and update it:

```python
        ctx = PlayerContext(
            player_id=player.id,
            position=player.position,
            age=player.age,
            snap_pct=stat.snap_pct if stat else None,
            carry_share=stat.carry_share if stat else None,
            target_share=stat.target_share if stat else None,
            games_played=stat.games_played if stat else None,
            years_exp=player.years_exp or 0,
            adp=_get_adp(player.adp_entries, scoring_fmt, league_type_val),
            projected_score=blended,
            new_team=False,
            new_coach=False,
            actual_tds=stat.actual_tds if stat else None,
            expected_tds=stat.expected_tds if stat else None,
            actual_tds_above_expected=(
                stat.actual_tds - stat.expected_tds
                if stat and stat.actual_tds is not None and stat.expected_tds is not None
                else None
            ),
            red_zone_looks=stat.red_zone_looks if stat else None,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_rules.py -v
```

Expected: all rules tests pass, including the new ones for TD regression and red zone premium. `BUILTIN_RULES` count is 18.

- [ ] **Step 7: Run the full suite**

```bash
pytest -v 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/engine/rules.py backend/app/engine/builtin_rules.py backend/app/api/generate.py backend/tests/test_rules.py
git commit -m "feat: add TD regression and red zone premium rules (18 built-ins total)"
```

---

## Task 13: Richer /api/data/status response + data_as_of from real freshness (TDD)

**Files:**
- Modify: `backend/app/api/data.py`
- Modify: `backend/app/api/generate.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api.py`:

```python
from datetime import datetime
from app.models import DataSourceStatus


@pytest.mark.asyncio
async def test_data_status_returns_per_source_dict(async_client, test_db):
    # Seed two status rows directly.
    test_db.add(DataSourceStatus(
        source="sleeper",
        last_updated=datetime(2026, 5, 20, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=1500,
    ))
    test_db.add(DataSourceStatus(
        source="espn",
        last_updated=datetime(2026, 5, 19, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error="HTTP 503", rows_upserted=0,
    ))
    await test_db.commit()

    resp = await async_client.get("/api/data/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"sleeper", "espn"}
    assert body["sleeper"]["rows_upserted"] == 1500
    assert body["sleeper"]["last_error"] is None
    assert body["espn"]["last_error"] == "HTTP 503"
    assert body["espn"]["last_updated"].startswith("2026-05-19")


@pytest.mark.asyncio
async def test_generate_data_as_of_uses_minimum_last_updated(async_client, test_db, seed_players):
    """data_as_of should reflect the oldest source's last successful update, not request time."""
    test_db.add(DataSourceStatus(
        source="sleeper",
        last_updated=datetime(2026, 5, 20, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=1500,
    ))
    test_db.add(DataSourceStatus(
        source="espn",
        last_updated=datetime(2026, 5, 15, 3, 0, 0),  # oldest
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=600,
    ))
    test_db.add(DataSourceStatus(
        source="fantasypros",
        last_updated=datetime(2026, 5, 18, 3, 0, 0),
        last_attempted=datetime(2026, 5, 18, 3, 0, 0),
        last_error=None, rows_upserted=580,
    ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.4, "weight_espn": 0.3,
        "weight_consensus": 0.3, "rules": [],
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_as_of"].startswith("2026-05-15")  # the espn last_updated
```

> NOTE: this assumes a `seed_players` fixture exists in `conftest.py`. If not, inline the seed-players logic from existing `test_generate_*` tests at the top of the new test.

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::test_data_status_returns_per_source_dict tests/test_api.py::test_generate_data_as_of_uses_minimum_last_updated -v
```

Expected: FAIL — `/api/data/status` returns the stub `{"nfl_data_py": "stub", ...}` shape; `data_as_of` is today's date.

- [ ] **Step 3: Update `/api/data/status`**

In `backend/app/api/data.py`, the updated status route reads from `data_source_status` directly via the helper:

```python
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.data.fetcher import fetcher
from app.data.status import get_all_status
from app.config import settings


router = APIRouter()


async def require_admin(x_api_key: str = Header(default="")):
    if settings.admin_api_key and x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/data/status")
async def data_status(db: AsyncSession = Depends(get_db)) -> dict:
    return await get_all_status(db)


@router.post("/data/refresh")
async def refresh_data(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    return await fetcher.refresh_all(db)
```

- [ ] **Step 4: Update `data_as_of` in `/api/generate`**

In `backend/app/api/generate.py`, the `/api/generate` route changes from `today = str(date.today())` to computing the minimum `last_updated`. Add this helper near the top of the file:

```python
async def _compute_data_as_of(db: AsyncSession) -> Optional[str]:
    """Return ISO date of the oldest successful source refresh, or None if no source has succeeded."""
    from app.models import DataSourceStatus
    rows = (await db.scalars(select(DataSourceStatus).where(DataSourceStatus.last_updated.is_not(None)))).all()
    if not rows:
        return None
    oldest = min(r.last_updated for r in rows)
    return oldest.date().isoformat()
```

Then update the `/api/generate` route to call it:

```python
@router.post("/generate", response_model=GenerateResponse)
async def generate_tiers(req: GenerateRequest, db: AsyncSession = Depends(get_db)) -> GenerateResponse:
    ranked = await _run_generate(req, db)
    data_as_of = await _compute_data_as_of(db)
    return GenerateResponse(
        players=[TieredPlayerOut(**p.__dict__) for p in ranked],
        total=len(ranked),
        data_as_of=data_as_of,
    )
```

(Remove the old `today = str(date.today())` line if it's still hanging around.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected: all API tests pass, including the 2 new ones.

- [ ] **Step 6: Run the full suite**

```bash
pytest -v 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/data.py backend/app/api/generate.py backend/tests/test_api.py
git commit -m "feat: /api/data/status returns per-source dict; data_as_of reflects real freshness"
```

---

## Task 14: End-to-end refresh → generate smoke test

**Files:**
- Create: `backend/tests/test_e2e_refresh.py` (NEW)

- [ ] **Step 1: Write the e2e test**

Create `backend/tests/test_e2e_refresh.py`:

```python
"""End-to-end: run refresh against fixtures, then call /api/generate and verify real output."""
import json
import pytest
import respx
import pandas as pd
from httpx import Response
from pathlib import Path

from app.data.fetcher import DataFetcher


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def all_mocks(monkeypatch):
    seasonal_df = pd.read_csv(FIXTURES / "nfl_data_seasonal.csv")
    snap_df = pd.read_csv(FIXTURES / "nfl_data_snap_counts.csv")
    pbp_df = pd.read_csv(FIXTURES / "nfl_data_pbp.csv")
    import app.data.sources.nfl_data as nfl_mod
    monkeypatch.setattr(nfl_mod, "import_seasonal_data", lambda y: seasonal_df.copy())
    monkeypatch.setattr(nfl_mod, "import_snap_counts", lambda y: snap_df.copy())
    monkeypatch.setattr(nfl_mod, "import_pbp_data", lambda y: pbp_df.copy())

    sleeper_fix = json.loads((FIXTURES / "sleeper_players.json").read_text())
    espn_fix = json.loads((FIXTURES / "espn_projections.json").read_text())

    with respx.mock() as router:
        router.get(url__regex=r"https://api\.sleeper\.app/.*").mock(return_value=Response(200, json=sleeper_fix))
        router.get(url__regex=r"https://fantasy\.espn\.com/.*").mock(return_value=Response(200, json=espn_fix))
        router.get(url__regex=r"https://www\.fantasypros\.com/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=(FIXTURES / "fantasypros_projections_wr.html").read_text())
        )
        router.get(url__regex=r"https://www\.fantasypros\.com/.*").mock(
            return_value=Response(200, text="<table id='data'><tbody></tbody></table>")
        )
        yield router


@pytest.mark.asyncio
async def test_refresh_then_generate_returns_real_players(async_client, test_db, all_mocks):
    # Refresh
    fetcher = DataFetcher(prior_season=2025, current_season=2026)
    results = await fetcher.refresh_all(test_db)
    assert all(r["last_error"] is None for r in results.values()), results

    # Generate
    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.4, "weight_espn": 0.3,
        "weight_consensus": 0.3, "rules": [],
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    # We seeded Chase (WR) and Jefferson (WR) via Sleeper, both have real projections.
    names = {p["name"] for p in body["players"]}
    assert "Ja'Marr Chase" in names
    assert "Justin Jefferson" in names

    # data_as_of is now today (all sources just refreshed).
    from datetime import date
    assert body["data_as_of"] == date.today().isoformat()

    # At least one player should have rules_applied (from PBP-derived rules firing).
    any_rules = any(p["rules_applied"] for p in body["players"])
    assert any_rules, "expected at least one rule to apply after PBP data loaded"
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/test_e2e_refresh.py -v
```

Expected: PASS.

- [ ] **Step 3: Run the full suite one final time**

```bash
pytest -v 2>&1 | tail -10
```

Expected: all tests pass. Roughly 50+ tests total (Plan 1's 40 + ~12-15 from Plan 2).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_e2e_refresh.py
git commit -m "test: end-to-end refresh → generate verifies real pipeline output"
```

---

## Task 15: Push branch and open PR

- [ ] **Step 1: Push**

```bash
git push -u origin data-pipeline
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "feat: AutoTiers data pipeline (Plan 2)" --body "$(cat <<'EOF'
## Summary

Replaces the stub DataFetcher with a real pipeline pulling from Sleeper (master player list + dynasty ADP), nfl_data_py (historical stats + PBP-derived expected_tds/red_zone_looks), ESPN unofficial API (current-season projections), and FantasyPros (consensus projections + redraft ADP via HTML scrape + fuzzy match).

Closes the 16→18 BUILTIN_RULES gap from Plan 1 by adding TD Regression and Red Zone Usage Premium rules that depend on the PBP-derived fields now being populated.

## Architecture

- **Sleeper is the master.** Provides player ID, gsis_id, and espn_id cross-references for downstream sources. Sleeper runs serially first; the other three sources run in parallel.
- **Per-source transactions.** A failure in one source doesn't roll back the others. Errors are persisted to a new `data_source_status` table that the `/api/data/status` endpoint now reads from.
- **`data_as_of` now means real freshness** (minimum `last_updated` across sources), not request time.
- **Test isolation:** all HTTP traffic mocked via `respx`; `nfl_data_py` monkey-patched to read fixture CSVs.

## Test plan

- [ ] `pytest -v` — all tests pass (~50 total)
- [ ] `docker compose down -v && docker compose up --build` — fresh start works
- [ ] `curl -X POST http://localhost:8000/api/data/refresh -H "X-Api-Key: ..."` — populates DB from real sources (or returns the per-source errors if a source is down)
- [ ] `curl http://localhost:8000/api/data/status` — returns per-source dict with timestamps and any errors
- [ ] `curl -X POST http://localhost:8000/api/generate -H "Content-Type: application/json" -d @example.json` — returns real player rankings with TD regression and red zone rules applied where applicable

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Notes

After all tasks complete:

1. **Spec coverage** — every section of `2026-05-20-autotiers-data-pipeline-design.md` has a corresponding task:
   - Sleeper fetcher → Task 6
   - nfl_data_py seasonal → Task 7; PBP → Task 8
   - ESPN → Task 9; FantasyPros → Task 10
   - Fuzzy matching → Task 4
   - Source protocol + status helpers → Task 5
   - Schema changes + migration → Tasks 2 + 3
   - Orchestrator + failure semantics → Task 11
   - 18 BUILTIN_RULES + PlayerContext fields → Task 12
   - Richer `/api/data/status` + `data_as_of` → Task 13
   - E2E verification → Task 14
   - New deps → Task 1

2. **Out of scope** — TeamContext (PFF data), real-time injury news, validation/anomaly detection. Spec explicitly defers these.

3. **Operational follow-up** — after merge, deploy + trigger `POST /api/data/refresh` once manually to populate the DB. The scheduler picks up subsequent refreshes per the existing cron (weekly June-July, daily August-September).
