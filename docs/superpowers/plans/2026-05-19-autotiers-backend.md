# AutoTiers Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python FastAPI backend for AutoTiers — database models, scoring engine, rules engine, tier clustering algorithm, and REST API — with all data fetchers stubbed. Real scrapers and the React frontend are separate plans.

**Architecture:** FastAPI + SQLAlchemy 2.0 async (asyncpg in production, aiosqlite in tests). Three pure-Python engines (scoring → rules → tiers) are composed by a single `POST /api/generate` endpoint. Player data lives in PostgreSQL, pre-fetched by background jobs (stubbed here, implemented in Plan 2).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, asyncpg, pydantic-settings v2, jenkspy, pandas, pytest, pytest-asyncio, aiosqlite (tests only), APScheduler

---

## File Map

```
backend/
├── pyproject.toml
├── .env.example
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/001_initial.py
├── app/
│   ├── __init__.py
│   ├── main.py               — FastAPI app + router registration
│   ├── config.py             — pydantic-settings (env vars)
│   ├── database.py           — async engine, session factory, Base, get_db()
│   ├── models/
│   │   ├── __init__.py       — re-exports all models (required by Alembic)
│   │   ├── player.py         — Player + PlayerStat ORM models
│   │   ├── projection.py     — Projection ORM model
│   │   ├── adp.py            — ADPData ORM model
│   │   └── team.py           — TeamContext ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── generate.py       — GenerateRequest, TieredPlayerOut, GenerateResponse
│   │   └── rules.py          — RuleConditionSchema, RuleEffectSchema, RuleSchema
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── scoring.py        — LeagueSettings, PlayerStats, calculate_fantasy_points, blend_scores
│   │   ├── rules.py          — Rule, PlayerContext, RuleResult, apply_rules
│   │   ├── builtin_rules.py  — BUILTIN_RULES: list[Rule] (18 built-in rules)
│   │   └── tiers.py          — TieredPlayer, assign_tiers
│   ├── api/
│   │   ├── __init__.py
│   │   ├── generate.py       — POST /api/generate
│   │   ├── rules.py          — GET /api/rules
│   │   ├── players.py        — GET /api/players
│   │   └── data.py           — GET /api/data/status, POST /api/data/refresh
│   └── data/
│       ├── __init__.py
│       └── fetcher.py        — stub DataFetcher (real impl in Plan 2)
└── tests/
    ├── conftest.py           — async fixtures: test_engine, test_db, async_client
    ├── test_scoring.py
    ├── test_rules.py
    ├── test_tiers.py
    └── test_api.py
```

---

## Task 1: Python Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: all `__init__.py` files and empty directories

- [ ] **Step 1: Create the backend directory structure**

```bash
cd /path/to/AutoTiers
mkdir -p backend/app/{models,schemas,engine,api,data}
mkdir -p backend/tests
mkdir -p backend/alembic/versions
touch backend/app/__init__.py
touch backend/app/models/__init__.py
touch backend/app/schemas/__init__.py
touch backend/app/engine/__init__.py
touch backend/app/api/__init__.py
touch backend/app/data/__init__.py
touch backend/tests/__init__.py
```

- [ ] **Step 2: Write `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "autotiers-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "alembic>=1.13",
    "asyncpg>=0.29",
    "psycopg2-binary>=2.9",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "pandas>=2.2",
    "jenkspy>=0.3",
    "httpx>=0.27",
    "apscheduler>=3.10",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5",
    "aiosqlite>=0.20",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 3: Write `backend/.env.example`**

```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/autotiers
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:password@localhost:5432/autotiers
DEBUG=false
```

- [ ] **Step 4: Install dependencies**

```bash
cd backend
pip install -e ".[dev]"
```

Expected: no errors, `fastapi`, `sqlalchemy`, `jenkspy`, `pytest` all importable.

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend Python project"
```

---

## Task 2: App Config + Database

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`

- [ ] **Step 1: Write `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://localhost/autotiers"
    database_url_sync: str = "postgresql+psycopg2://localhost/autotiers"
    debug: bool = False


settings = Settings()
```

- [ ] **Step 2: Write `backend/app/database.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 3: Verify imports work**

```bash
cd backend
python -c "from app.database import Base, get_db; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/app/database.py
git commit -m "feat: add config and database session setup"
```

---

## Task 3: ORM Models

**Files:**
- Create: `backend/app/models/player.py`
- Create: `backend/app/models/projection.py`
- Create: `backend/app/models/adp.py`
- Create: `backend/app/models/team.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write `backend/app/models/player.py`**

```python
from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str] = mapped_column(String(10), nullable=False)
    team: Mapped[Optional[str]] = mapped_column(String(5))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    years_exp: Mapped[Optional[int]] = mapped_column(Integer)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)

    stats: Mapped[list["PlayerStat"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    projections: Mapped[list["Projection"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    adp_entries: Mapped[list["ADPData"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class PlayerStat(Base):
    __tablename__ = "player_stats"
    __table_args__ = (UniqueConstraint("player_id", "season", name="uq_player_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)

    targets: Mapped[Optional[int]] = mapped_column(Integer)
    receptions: Mapped[Optional[int]] = mapped_column(Integer)
    rec_yards: Mapped[Optional[float]] = mapped_column(Float)
    rec_tds: Mapped[Optional[int]] = mapped_column(Integer)
    rush_att: Mapped[Optional[int]] = mapped_column(Integer)
    rush_yards: Mapped[Optional[float]] = mapped_column(Float)
    rush_tds: Mapped[Optional[int]] = mapped_column(Integer)
    pass_att: Mapped[Optional[int]] = mapped_column(Integer)
    pass_yards: Mapped[Optional[float]] = mapped_column(Float)
    pass_tds: Mapped[Optional[int]] = mapped_column(Integer)
    interceptions: Mapped[Optional[int]] = mapped_column(Integer)
    snaps: Mapped[Optional[int]] = mapped_column(Integer)
    snap_pct: Mapped[Optional[float]] = mapped_column(Float)
    carry_share: Mapped[Optional[float]] = mapped_column(Float)
    target_share: Mapped[Optional[float]] = mapped_column(Float)
    games_played: Mapped[Optional[int]] = mapped_column(Integer)
    red_zone_looks: Mapped[Optional[int]] = mapped_column(Integer)
    actual_tds: Mapped[Optional[int]] = mapped_column(Integer)
    expected_tds: Mapped[Optional[float]] = mapped_column(Float)

    player: Mapped["Player"] = relationship(back_populates="stats")
```

- [ ] **Step 2: Write `backend/app/models/projection.py`**

```python
from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Projection(Base):
    __tablename__ = "projections"
    __table_args__ = (
        UniqueConstraint("player_id", "source", "scoring_format", name="uq_projection"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # espn | fantasypros
    scoring_format: Mapped[str] = mapped_column(String(20), nullable=False)
    projected_points: Mapped[float] = mapped_column(Float, nullable=False)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)

    player: Mapped["Player"] = relationship(back_populates="projections")
```

- [ ] **Step 3: Write `backend/app/models/adp.py`**

```python
from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ADPData(Base):
    __tablename__ = "adp_data"
    __table_args__ = (
        UniqueConstraint("player_id", "format", "adp_source", name="uq_adp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)  # standard | half_ppr | ppr | dynasty
    adp: Mapped[float] = mapped_column(Float, nullable=False)
    adp_source: Mapped[str] = mapped_column(String(30), nullable=False)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)

    player: Mapped["Player"] = relationship(back_populates="adp_entries")
```

- [ ] **Step 4: Write `backend/app/models/team.py`**

```python
from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TeamContext(Base):
    __tablename__ = "team_context"
    __table_args__ = (UniqueConstraint("team", "season", name="uq_team_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team: Mapped[str] = mapped_column(String(5), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    off_line_grade: Mapped[Optional[float]] = mapped_column(Float)
    new_head_coach: Mapped[bool] = mapped_column(Boolean, default=False)
    coaching_scheme: Mapped[Optional[str]] = mapped_column(String(50))
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
```

- [ ] **Step 5: Update `backend/app/models/__init__.py`**

```python
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models.adp import ADPData
from app.models.team import TeamContext

__all__ = ["Player", "PlayerStat", "Projection", "ADPData", "TeamContext"]
```

- [ ] **Step 6: Verify all models import cleanly**

```bash
cd backend
python -c "from app.models import Player, PlayerStat, Projection, ADPData, TeamContext; print('OK')"
```

Expected output: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add SQLAlchemy ORM models"
```

---

## Task 4: Alembic Initial Migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/001_initial.py`

- [ ] **Step 1: Initialize Alembic**

```bash
cd backend
alembic init alembic
```

Expected: `alembic/` directory created with `env.py`, `script.py.mako`, `versions/`.

- [ ] **Step 2: Update `backend/alembic/env.py`**

Replace the generated file entirely:

```python
import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — side effect: registers all models with Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Generate the initial migration**

```bash
cd backend
alembic revision --autogenerate -m "initial"
```

Expected: a new file appears in `alembic/versions/` named something like `abc123_initial.py`. Rename it to `001_initial.py` for clarity.

- [ ] **Step 4: Verify the migration looks correct**

Open the generated file and confirm it creates tables: `players`, `player_stats`, `projections`, `adp_data`, `team_context` with the expected columns and constraints.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/
git commit -m "feat: add Alembic initial migration"
```

---

## Task 5: Scoring Engine (TDD)

**Files:**
- Create: `backend/tests/test_scoring.py`
- Create: `backend/app/engine/scoring.py`

- [ ] **Step 1: Write the failing tests in `backend/tests/test_scoring.py`**

```python
import pytest
from app.engine.scoring import (
    ScoringFormat, LeagueType, LeagueSettings, PlayerStats,
    calculate_fantasy_points, blend_scores,
)


def _settings(**overrides) -> LeagueSettings:
    defaults = dict(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.40,
        weight_espn=0.30,
        weight_consensus=0.30,
    )
    defaults.update(overrides)
    return LeagueSettings(**defaults)


def _stats(**overrides) -> PlayerStats:
    defaults = dict(
        targets=0, receptions=0, rec_yards=0.0, rec_tds=0,
        rush_att=0, rush_yards=0.0, rush_tds=0,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
        games_played=17,
    )
    defaults.update(overrides)
    return PlayerStats(**defaults)


def test_ppr_receptions_score_one_point_each():
    stats = _stats(receptions=8, rec_yards=100.0, rec_tds=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.PPR), position="WR")
    # 8*1 + 100*0.1 + 1*6 = 8 + 10 + 6 = 24
    assert pts == pytest.approx(24.0)


def test_standard_no_reception_points():
    stats = _stats(receptions=8, rec_yards=100.0, rec_tds=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.STANDARD), position="WR")
    # 100*0.1 + 1*6 = 16
    assert pts == pytest.approx(16.0)


def test_half_ppr_receptions_score_half_point():
    stats = _stats(receptions=8)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.HALF_PPR), position="WR")
    assert pts == pytest.approx(4.0)


def test_te_premium_gives_te_extra_half_point_per_reception():
    stats = _stats(receptions=6, rec_yards=60.0)
    te_pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.TE_PREMIUM), position="TE")
    wr_pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.TE_PREMIUM), position="WR")
    # TE gets 1.5/rec, WR gets 1.0/rec; difference = 6 * 0.5 = 3
    assert te_pts == pytest.approx(wr_pts + 3.0)


def test_rushing_yards_and_td():
    stats = _stats(rush_att=20, rush_yards=105.0, rush_tds=1)
    pts = calculate_fantasy_points(stats, _settings(scoring_format=ScoringFormat.STANDARD, bonus_100yd_rushing=True), position="RB")
    # 105*0.1 + 1*6 + 3 bonus = 10.5 + 6 + 3 = 19.5
    assert pts == pytest.approx(19.5)


def test_100yd_bonus_not_awarded_under_threshold():
    stats = _stats(rush_yards=99.0)
    pts = calculate_fantasy_points(stats, _settings(bonus_100yd_rushing=True), position="RB")
    assert pts == pytest.approx(9.9)


def test_six_point_passing_tds():
    stats = _stats(pass_yards=300.0, pass_tds=3)
    pts = calculate_fantasy_points(stats, _settings(qb_td_points=6.0), position="QB")
    # 300*0.04 + 3*6 = 12 + 18 = 30
    assert pts == pytest.approx(30.0)


def test_interception_penalty():
    stats = _stats(interceptions=2)
    pts = calculate_fantasy_points(stats, _settings(), position="QB")
    assert pts == pytest.approx(-4.0)


def test_blend_all_sources():
    s = _settings(weight_prior_year=0.4, weight_espn=0.3, weight_consensus=0.3)
    result = blend_scores(prior_year_actual=300.0, espn_projection=350.0, consensus_projection=340.0, settings=s)
    expected = 300.0 * 0.4 + 350.0 * 0.3 + 340.0 * 0.3
    assert result == pytest.approx(expected)


def test_blend_redistributes_weight_when_source_missing():
    s = _settings(weight_prior_year=0.4, weight_espn=0.3, weight_consensus=0.3)
    result = blend_scores(prior_year_actual=None, espn_projection=300.0, consensus_projection=280.0, settings=s)
    # espn + consensus weights = 0.6; redistribute to 0.3/0.6 and 0.3/0.6
    expected = (300.0 * 0.3 + 280.0 * 0.3) / 0.6
    assert result == pytest.approx(expected)


def test_blend_all_missing_returns_zero():
    result = blend_scores(None, None, None, settings=_settings())
    assert result == 0.0
```

- [ ] **Step 2: Run and confirm tests fail**

```bash
cd backend
pytest tests/test_scoring.py -v
```

Expected: `ImportError` — `app.engine.scoring` doesn't exist yet.

- [ ] **Step 3: Implement `backend/app/engine/scoring.py`**

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ScoringFormat(str, Enum):
    STANDARD = "standard"
    HALF_PPR = "half_ppr"
    PPR = "ppr"
    TE_PREMIUM = "te_premium"


class LeagueType(str, Enum):
    STANDARD = "standard"
    DYNASTY = "dynasty"
    KEEPER = "keeper"


@dataclass
class LeagueSettings:
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_td_points: float
    bonus_100yd_rushing: bool
    bonus_100yd_receiving: bool
    bonus_first_downs: bool
    weight_prior_year: float
    weight_espn: float
    weight_consensus: float


@dataclass
class PlayerStats:
    targets: int
    receptions: int
    rec_yards: float
    rec_tds: int
    rush_att: int
    rush_yards: float
    rush_tds: int
    pass_att: int
    pass_yards: float
    pass_tds: int
    interceptions: int
    games_played: int


def calculate_fantasy_points(stats: PlayerStats, settings: LeagueSettings, position: str = "") -> float:
    pts = 0.0

    # Passing
    pts += stats.pass_yards * 0.04
    pts += stats.pass_tds * settings.qb_td_points
    pts -= stats.interceptions * 2.0

    # Rushing
    pts += stats.rush_yards * 0.1
    pts += stats.rush_tds * 6.0
    if settings.bonus_100yd_rushing and stats.rush_yards >= 100:
        pts += 3.0

    # Receiving — reception points depend on format and position
    if settings.scoring_format == ScoringFormat.PPR:
        rec_pts = 1.0
    elif settings.scoring_format == ScoringFormat.HALF_PPR:
        rec_pts = 0.5
    elif settings.scoring_format == ScoringFormat.TE_PREMIUM:
        rec_pts = 1.5 if position == "TE" else 1.0
    else:
        rec_pts = 0.0

    pts += stats.receptions * rec_pts
    pts += stats.rec_yards * 0.1
    pts += stats.rec_tds * 6.0
    if settings.bonus_100yd_receiving and stats.rec_yards >= 100:
        pts += 3.0

    return round(pts, 2)


def blend_scores(
    prior_year_actual: Optional[float],
    espn_projection: Optional[float],
    consensus_projection: Optional[float],
    settings: LeagueSettings,
) -> float:
    sources = [
        (prior_year_actual, settings.weight_prior_year),
        (espn_projection, settings.weight_espn),
        (consensus_projection, settings.weight_consensus),
    ]
    available = [(score, weight) for score, weight in sources if score is not None]
    if not available:
        return 0.0
    total_weight = sum(w for _, w in available)
    return round(sum(score * (weight / total_weight) for score, weight in available), 2)
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_scoring.py -v
```

Expected: all 11 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/scoring.py backend/tests/test_scoring.py
git commit -m "feat: implement scoring engine with TDD"
```

---

## Task 6: Rules Engine (TDD)

**Files:**
- Create: `backend/app/engine/rules.py`
- Create: `backend/app/engine/builtin_rules.py`
- Create: `backend/tests/test_rules.py`

- [ ] **Step 1: Write the failing tests in `backend/tests/test_rules.py`**

```python
import pytest
from app.engine.rules import (
    Rule, RuleCondition, RuleEffect, EffectType, PlayerContext,
    RuleResult, apply_rules,
)
from app.engine.builtin_rules import BUILTIN_RULES


def _ctx(**overrides) -> PlayerContext:
    defaults = dict(
        player_id="p1", position="RB", age=25,
        snap_pct=0.70, carry_share=0.65, target_share=0.15,
        games_played=16, years_exp=3, adp=5.0,
        projected_score=200.0, new_team=False, new_coach=False,
        actual_tds=8, expected_tds=7.0,
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def _rule(field, operator, value, effect_type, effect_value, weight=1.0, enabled=True) -> Rule:
    return Rule(
        name=f"{field}_{operator}_{value}",
        conditions=[RuleCondition(field=field, operator=operator, value=value)],
        effect=RuleEffect(type=effect_type, value=effect_value),
        enabled=enabled,
        weight=weight,
    )


def test_multiplier_applied_when_condition_met():
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92)
    result = apply_rules(200.0, _ctx(age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0 * 0.92)
    assert rule.name in result.rules_applied


def test_condition_not_met_skips_rule():
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92)
    result = apply_rules(200.0, _ctx(age=25), [rule])
    assert result.adjusted_score == pytest.approx(200.0)
    assert result.rules_applied == []


def test_disabled_rule_is_skipped():
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92, enabled=False)
    result = apply_rules(200.0, _ctx(age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0)


def test_flat_bonus():
    rule = _rule("target_share", ">=", 0.25, EffectType.FLAT_BONUS, 20.0)
    result = apply_rules(200.0, _ctx(target_share=0.28), [rule])
    assert result.adjusted_score == pytest.approx(220.0)


def test_flat_penalty():
    rule = _rule("carry_share", "<", 0.50, EffectType.FLAT_PENALTY, 30.0)
    result = apply_rules(200.0, _ctx(carry_share=0.40), [rule])
    assert result.adjusted_score == pytest.approx(170.0)


def test_flag_does_not_change_score():
    rule = _rule("new_team", "==", True, EffectType.FLAG, "New Team")
    result = apply_rules(200.0, _ctx(new_team=True), [rule])
    assert result.adjusted_score == pytest.approx(200.0)
    assert "New Team" in result.flags


def test_weight_scales_multiplier_distance():
    # weight=2.0 doubles the distance from 1.0: 0.92 → distance=-0.08 → actual=1.0+(-0.08*2)=0.84
    rule = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92, weight=2.0)
    result = apply_rules(200.0, _ctx(age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0 * 0.84)


def test_weight_scales_flat_bonus():
    rule = _rule("target_share", ">=", 0.25, EffectType.FLAT_BONUS, 20.0, weight=2.0)
    result = apply_rules(200.0, _ctx(target_share=0.28), [rule])
    assert result.adjusted_score == pytest.approx(240.0)


def test_multiple_rules_compound_in_order():
    rule1 = _rule("age", ">=", 28, EffectType.MULTIPLIER, 0.92)
    rule2 = _rule("carry_share", "<", 0.50, EffectType.FLAT_PENALTY, 30.0)
    result = apply_rules(200.0, _ctx(age=30, carry_share=0.40), [rule1, rule2])
    # 200 * 0.92 = 184; 184 - 30 = 154
    assert result.adjusted_score == pytest.approx(154.0)
    assert len(result.rules_applied) == 2


def test_null_field_causes_condition_to_be_false():
    rule = _rule("snap_pct", "<", 0.50, EffectType.MULTIPLIER, 0.90)
    result = apply_rules(200.0, _ctx(snap_pct=None), [rule])
    assert result.adjusted_score == pytest.approx(200.0)


def test_multi_condition_rule_requires_all_conditions():
    rule = Rule(
        name="rb_age",
        conditions=[
            RuleCondition(field="position", operator="==", value="RB"),
            RuleCondition(field="age", operator=">=", value=28),
        ],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.92),
        enabled=True,
        weight=1.0,
    )
    # Both conditions met
    result = apply_rules(200.0, _ctx(position="RB", age=30), [rule])
    assert result.adjusted_score == pytest.approx(200.0 * 0.92)
    # Only one condition met — rule skipped
    result2 = apply_rules(200.0, _ctx(position="WR", age=30), [rule])
    assert result2.adjusted_score == pytest.approx(200.0)


def test_builtin_rules_is_nonempty_list_of_rules():
    assert isinstance(BUILTIN_RULES, list)
    assert len(BUILTIN_RULES) >= 15
    for rule in BUILTIN_RULES:
        assert isinstance(rule, Rule)
        assert rule.name
        assert rule.conditions
```

- [ ] **Step 2: Run and confirm tests fail**

```bash
pytest tests/test_rules.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `backend/app/engine/rules.py`**

```python
import operator as _op
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EffectType(str, Enum):
    MULTIPLIER = "multiplier"
    FLAT_BONUS = "flat_bonus"
    FLAT_PENALTY = "flat_penalty"
    FLAG = "flag"


@dataclass
class RuleCondition:
    field: str
    operator: str  # ">", ">=", "<", "<=", "==", "!="
    value: Any


@dataclass
class RuleEffect:
    type: EffectType
    value: Any  # float for numeric effects, str for FLAG


@dataclass
class Rule:
    name: str
    conditions: list[RuleCondition]
    effect: RuleEffect
    enabled: bool = True
    weight: float = 1.0


@dataclass
class PlayerContext:
    player_id: str
    position: str
    age: int
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


@dataclass
class RuleResult:
    adjusted_score: float
    flags: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)


_OPS = {
    ">": _op.gt, ">=": _op.ge,
    "<": _op.lt, "<=": _op.le,
    "==": _op.eq, "!=": _op.ne,
}


def _evaluate(condition: RuleCondition, ctx: PlayerContext) -> bool:
    val = getattr(ctx, condition.field, None)
    if val is None:
        return False
    return _OPS[condition.operator](val, condition.value)


def apply_rules(base_score: float, ctx: PlayerContext, rules: list[Rule]) -> RuleResult:
    score = base_score
    flags: list[str] = []
    applied: list[str] = []

    for rule in rules:
        if not rule.enabled:
            continue
        if not all(_evaluate(c, ctx) for c in rule.conditions):
            continue

        effect = rule.effect
        if effect.type == EffectType.MULTIPLIER:
            distance = float(effect.value) - 1.0
            actual_multiplier = 1.0 + (distance * rule.weight)
            score *= actual_multiplier
        elif effect.type == EffectType.FLAT_BONUS:
            score += float(effect.value) * rule.weight
        elif effect.type == EffectType.FLAT_PENALTY:
            score -= float(effect.value) * rule.weight
        elif effect.type == EffectType.FLAG:
            flags.append(str(effect.value))

        applied.append(rule.name)

    return RuleResult(adjusted_score=round(score, 2), flags=flags, rules_applied=applied)
```

- [ ] **Step 4: Implement `backend/app/engine/builtin_rules.py`**

```python
from app.engine.rules import Rule, RuleCondition, RuleEffect, EffectType


def _rule(name: str, conditions: list[tuple], effect_type: EffectType, effect_value) -> Rule:
    return Rule(
        name=name,
        conditions=[RuleCondition(field=f, operator=op, value=v) for f, op, v in conditions],
        effect=RuleEffect(type=effect_type, value=effect_value),
        enabled=True,
        weight=1.0,
    )


BUILTIN_RULES: list[Rule] = [
    # Age / Longevity
    _rule("RB Age 28-29 Penalty", [("position", "==", "RB"), ("age", ">=", 28), ("age", "<", 30)], EffectType.MULTIPLIER, 0.92),
    _rule("RB Age 30-31 Penalty", [("position", "==", "RB"), ("age", ">=", 30), ("age", "<", 32)], EffectType.MULTIPLIER, 0.84),
    _rule("RB Age 32+ Penalty",   [("position", "==", "RB"), ("age", ">=", 32)],                   EffectType.MULTIPLIER, 0.76),
    _rule("WR Age 31-32 Penalty", [("position", "==", "WR"), ("age", ">=", 31), ("age", "<", 33)], EffectType.MULTIPLIER, 0.95),
    _rule("WR Age 33+ Penalty",   [("position", "==", "WR"), ("age", ">=", 33)],                   EffectType.MULTIPLIER, 0.90),
    _rule("Dynasty Youth Premium (<25)", [("age", "<", 25)],                                        EffectType.FLAT_BONUS, 15.0),

    # Usage
    _rule("RB Committee Discount",   [("position", "==", "RB"), ("carry_share", "<", 0.50)],   EffectType.MULTIPLIER, 0.85),
    _rule("Target Share Premium",    [("target_share", ">=", 0.25)],                           EffectType.FLAT_BONUS, 20.0),
    _rule("Red Zone Usage Premium",  [("position", "!=", "QB")],                               EffectType.FLAT_BONUS, 0.0),  # computed dynamically in generate endpoint
    _rule("Declining Snap% Penalty", [("snap_pct", "<", 0.55)],                                EffectType.MULTIPLIER, 0.90),

    # Situation
    _rule("New Team Penalty",    [("new_team", "==", True)],                                    EffectType.MULTIPLIER, 0.90),
    _rule("New Head Coach",      [("new_coach", "==", True)],                                   EffectType.MULTIPLIER, 0.93),
    _rule("Sophomore Leap",      [("years_exp", "==", 1)],                                      EffectType.FLAT_BONUS, 15.0),
    _rule("Contract Year Flag",  [("years_exp", ">", 3)],                                       EffectType.FLAG, "Contract Year"),

    # Regression
    _rule("Injury History Penalty", [("games_played", "<", 12)],                               EffectType.MULTIPLIER, 0.88),

    # Flags
    _rule("Handcuff Flag",          [("position", "==", "RB"), ("carry_share", "<", 0.30)],    EffectType.FLAG, "Handcuff"),
    _rule("Availability Risk Flag", [("games_played", "<", 8)],                                EffectType.FLAG, "Availability Risk"),
]
```

- [ ] **Step 5: Run tests and confirm they pass**

```bash
pytest tests/test_rules.py -v
```

Expected: all 12 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/rules.py backend/app/engine/builtin_rules.py backend/tests/test_rules.py
git commit -m "feat: implement rules engine and built-in rules with TDD"
```

---

## Task 7: Tier Calculation Engine (TDD)

**Files:**
- Create: `backend/tests/test_tiers.py`
- Create: `backend/app/engine/tiers.py`

- [ ] **Step 1: Write the failing tests in `backend/tests/test_tiers.py`**

```python
import pytest
from app.engine.tiers import TieredPlayer, assign_tiers


def _player(pid: str, position: str, score: float, **kwargs) -> TieredPlayer:
    return TieredPlayer(
        player_id=pid, name=f"Player {pid}", position=position,
        team="NE", age=25, adjusted_score=score,
        projected_score_raw=score, prior_year_actual=score,
        adp_standard=None, adp_ppr=None, adp_dynasty=None,
        flags=[], rules_applied=[],
        overall_rank=0, overall_tier=0, positional_tier="",
        **kwargs,
    )


def test_overall_rank_is_sequential_from_one():
    players = [_player(str(i), "RB", float(100 - i)) for i in range(10)]
    result = assign_tiers(players)
    ranks = sorted(p.overall_rank for p in result)
    assert ranks == list(range(1, 11))


def test_highest_score_gets_rank_one():
    players = [
        _player("a", "RB", 300.0),
        _player("b", "WR", 350.0),
        _player("c", "QB", 250.0),
    ]
    result = assign_tiers(players)
    by_rank = {p.overall_rank: p for p in result}
    assert by_rank[1].player_id == "b"
    assert by_rank[2].player_id == "a"
    assert by_rank[3].player_id == "c"


def test_positional_tier_label_uses_correct_position_prefix():
    players = [
        _player("wr1", "WR", 350.0),
        _player("wr2", "WR", 200.0),
        _player("rb1", "RB", 300.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    assert by_id["wr1"].positional_tier.startswith("WR")
    assert by_id["rb1"].positional_tier.startswith("RB")


def test_players_with_similar_scores_share_positional_tier():
    players = [
        _player("a", "WR", 350.0),
        _player("b", "WR", 348.0),
        _player("c", "WR", 150.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    # a and b are close, c is far away — a and b should share a tier
    assert by_id["a"].positional_tier == by_id["b"].positional_tier
    assert by_id["a"].positional_tier != by_id["c"].positional_tier


def test_clear_score_gap_creates_different_overall_tiers():
    players = [
        _player("a", "RB", 400.0),
        _player("b", "WR", 395.0),
        _player("c", "RB", 100.0),
        _player("d", "WR", 95.0),
    ]
    result = assign_tiers(players)
    by_id = {p.player_id: p for p in result}
    assert by_id["a"].overall_tier == by_id["b"].overall_tier
    assert by_id["a"].overall_tier < by_id["c"].overall_tier


def test_single_player_per_position_gets_tier_one():
    players = [_player("q1", "QB", 350.0)]
    result = assign_tiers(players)
    assert result[0].positional_tier == "QB1"


def test_empty_input_returns_empty():
    result = assign_tiers([])
    assert result == []
```

- [ ] **Step 2: Run and confirm tests fail**

```bash
pytest tests/test_tiers.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `backend/app/engine/tiers.py`**

```python
from dataclasses import dataclass
from typing import Optional
import jenkspy


POSITION_MAX_TIERS = {"QB": 3, "RB": 5, "WR": 5, "TE": 3, "K": 2, "DST": 3}


@dataclass
class TieredPlayer:
    player_id: str
    name: str
    position: str
    team: str
    age: int
    adjusted_score: float
    projected_score_raw: float
    prior_year_actual: Optional[float]
    adp_standard: Optional[float]
    adp_ppr: Optional[float]
    adp_dynasty: Optional[float]
    flags: list[str]
    rules_applied: list[str]
    overall_rank: int
    overall_tier: int
    positional_tier: str


def _jenks_interior_breaks(scores: list[float], max_classes: int) -> list[float]:
    unique = sorted(set(scores), reverse=True)
    n_classes = min(max_classes, len(unique))
    if n_classes < 2:
        return []
    breaks = jenkspy.jenks_breaks(scores, n_classes=n_classes)
    return list(breaks[1:-1])  # drop min and max; keep interior breakpoints only


def _assign_tier_from_breaks(score: float, breaks: list[float], descending_scores: bool = True) -> int:
    tier = 1
    for bp in sorted(breaks, reverse=descending_scores):
        if score < bp:
            tier += 1
    return tier


def _cluster_position(players: list[TieredPlayer], position: str) -> None:
    max_tiers = POSITION_MAX_TIERS.get(position, 3)
    scores = [p.adjusted_score for p in players]
    breaks = _jenks_interior_breaks(scores, max_tiers)
    for p in players:
        tier_num = _assign_tier_from_breaks(p.adjusted_score, breaks)
        p.positional_tier = f"{position}{tier_num}"


def assign_tiers(all_players: list[TieredPlayer]) -> list[TieredPlayer]:
    if not all_players:
        return []

    # Step 1: positional clustering
    by_position: dict[str, list[TieredPlayer]] = {}
    for p in all_players:
        by_position.setdefault(p.position, []).append(p)
    for position, group in by_position.items():
        _cluster_position(group, position)

    # Step 2: overall ranking by adjusted score
    ranked = sorted(all_players, key=lambda p: p.adjusted_score, reverse=True)
    for rank, player in enumerate(ranked, start=1):
        player.overall_rank = rank

    # Step 3: overall tier clustering
    all_scores = [p.adjusted_score for p in ranked]
    overall_breaks = _jenks_interior_breaks(all_scores, max_classes=10)
    for p in ranked:
        p.overall_tier = _assign_tier_from_breaks(p.adjusted_score, overall_breaks)

    return ranked
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_tiers.py -v
```

Expected: all 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/tiers.py backend/tests/test_tiers.py
git commit -m "feat: implement tier clustering engine with TDD"
```

---

## Task 8: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/rules.py`
- Create: `backend/app/schemas/generate.py`

- [ ] **Step 1: Write `backend/app/schemas/rules.py`**

```python
from pydantic import BaseModel
from app.engine.rules import EffectType


class RuleConditionSchema(BaseModel):
    field: str
    operator: str
    value: float | int | str | bool


class RuleEffectSchema(BaseModel):
    type: EffectType
    value: float | str


class RuleSchema(BaseModel):
    name: str
    conditions: list[RuleConditionSchema]
    effect: RuleEffectSchema
    enabled: bool = True
    weight: float = 1.0
    is_builtin: bool = False
    category: str = "Custom"
```

- [ ] **Step 2: Write `backend/app/schemas/generate.py`**

```python
from typing import Optional
from pydantic import BaseModel, field_validator
from app.engine.scoring import ScoringFormat, LeagueType
from app.schemas.rules import RuleSchema


class GenerateRequest(BaseModel):
    scoring_format: ScoringFormat
    league_type: LeagueType
    league_size: int
    qb_td_points: float = 4.0
    bonus_100yd_rushing: bool = False
    bonus_100yd_receiving: bool = False
    bonus_first_downs: bool = False
    weight_prior_year: float = 0.40
    weight_espn: float = 0.30
    weight_consensus: float = 0.30
    rules: list[RuleSchema] = []

    @field_validator("league_size")
    @classmethod
    def valid_league_size(cls, v: int) -> int:
        if v not in {8, 10, 12, 14, 16}:
            raise ValueError("league_size must be one of: 8, 10, 12, 14, 16")
        return v

    @field_validator("weight_consensus")
    @classmethod
    def weights_sum_to_one(cls, weight_consensus: float, info) -> float:
        data = info.data
        total = data.get("weight_prior_year", 0) + data.get("weight_espn", 0) + weight_consensus
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Score weights must sum to 1.0, got {total:.2f}")
        return weight_consensus


class TieredPlayerOut(BaseModel):
    overall_rank: int
    player_id: str
    name: str
    position: str
    team: Optional[str]
    age: Optional[int]
    overall_tier: int
    positional_tier: str
    adjusted_score: float
    projected_score_raw: float
    prior_year_actual: Optional[float]
    adp_standard: Optional[float]
    adp_ppr: Optional[float]
    adp_dynasty: Optional[float]
    flags: list[str]
    rules_applied: list[str]


class GenerateResponse(BaseModel):
    players: list[TieredPlayerOut]
    total: int
    data_as_of: Optional[str] = None
```

- [ ] **Step 3: Verify schemas import**

```bash
cd backend
python -c "from app.schemas.generate import GenerateRequest, GenerateResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/
git commit -m "feat: add pydantic request/response schemas"
```

---

## Task 9: Stub Data Fetcher

**Files:**
- Create: `backend/app/data/fetcher.py`

The generate endpoint needs a way to pull player data that can be replaced with real scrapers in Plan 2. This stub returns empty data so the endpoint works end-to-end without real API calls.

- [ ] **Step 1: Write `backend/app/data/fetcher.py`**

```python
"""
Stub DataFetcher — returns no data.
Real implementations for nfl_data_py, FantasyPros, ESPN, and Sleeper
are added in Plan 2 (Data Pipeline).
"""
from sqlalchemy.ext.asyncio import AsyncSession


class DataFetcher:
    async def refresh_all(self, db: AsyncSession) -> dict[str, str]:
        """Fetch all data sources and upsert into the database. Returns status per source."""
        return {
            "nfl_data_py": "stub — not implemented",
            "fantasypros": "stub — not implemented",
            "espn": "stub — not implemented",
            "sleeper": "stub — not implemented",
        }

    async def last_updated(self, db: AsyncSession) -> dict[str, str | None]:
        """Return the most recent last_updated timestamp per data source."""
        from sqlalchemy import select, func
        from app.models.projection import Projection

        result = await db.execute(
            select(Projection.source, func.max(Projection.last_updated))
            .group_by(Projection.source)
        )
        rows = result.all()
        return {source: str(updated) if updated else None for source, updated in rows}


fetcher = DataFetcher()
```

- [ ] **Step 2: Verify import**

```bash
python -c "from app.data.fetcher import fetcher; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/data/fetcher.py
git commit -m "feat: add stub data fetcher (real impl in Plan 2)"
```

---

## Task 10: FastAPI App + API Routes

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/generate.py`
- Create: `backend/app/api/rules.py`
- Create: `backend/app/api/players.py`
- Create: `backend/app/api/data.py`

- [ ] **Step 1: Write `backend/app/api/rules.py`**

```python
from fastapi import APIRouter
from app.schemas.rules import RuleSchema, RuleConditionSchema, RuleEffectSchema
from app.engine.builtin_rules import BUILTIN_RULES

router = APIRouter()

_CATEGORIES = {
    "RB Age": "Age/Longevity",
    "WR Age": "Age/Longevity",
    "Dynasty Youth": "Age/Longevity",
    "RB Committee": "Usage",
    "Target Share": "Usage",
    "Red Zone": "Usage",
    "Declining Snap": "Usage",
    "New Team": "Situation",
    "New Head Coach": "Situation",
    "Sophomore Leap": "Situation",
    "Contract Year": "Situation",
    "Injury History": "Regression",
    "Handcuff": "Flag",
    "Availability Risk": "Flag",
}


def _categorize(name: str) -> str:
    for prefix, cat in _CATEGORIES.items():
        if name.startswith(prefix):
            return cat
    return "Other"


@router.get("/rules", response_model=list[RuleSchema])
async def list_rules() -> list[RuleSchema]:
    return [
        RuleSchema(
            name=rule.name,
            conditions=[
                RuleConditionSchema(field=c.field, operator=c.operator, value=c.value)
                for c in rule.conditions
            ],
            effect=RuleEffectSchema(type=rule.effect.type, value=rule.effect.value),
            enabled=rule.enabled,
            weight=rule.weight,
            is_builtin=True,
            category=_categorize(rule.name),
        )
        for rule in BUILTIN_RULES
    ]
```

- [ ] **Step 2: Write `backend/app/api/players.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.player import Player

router = APIRouter()


@router.get("/players")
async def list_players(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(Player).order_by(Player.name))
    players = result.scalars().all()
    return [
        {"id": p.id, "name": p.name, "position": p.position, "team": p.team, "age": p.age}
        for p in players
    ]
```

- [ ] **Step 3: Write `backend/app/api/data.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.data.fetcher import fetcher

router = APIRouter()


@router.get("/data/status")
async def data_status(db: AsyncSession = Depends(get_db)) -> dict:
    return await fetcher.last_updated(db)


@router.post("/data/refresh")
async def data_refresh(db: AsyncSession = Depends(get_db)) -> dict:
    status = await fetcher.refresh_all(db)
    return {"status": status}
```

- [ ] **Step 4: Write `backend/app/api/generate.py`**

```python
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models.adp import ADPData
from app.engine.scoring import LeagueSettings, PlayerStats, calculate_fantasy_points, blend_scores
from app.engine.rules import Rule, RuleCondition, RuleEffect, PlayerContext, apply_rules
from app.engine.builtin_rules import BUILTIN_RULES
from app.engine.tiers import TieredPlayer, assign_tiers
from app.schemas.generate import GenerateRequest, GenerateResponse, TieredPlayerOut

router = APIRouter()


def _build_league_settings(req: GenerateRequest) -> LeagueSettings:
    return LeagueSettings(
        scoring_format=req.scoring_format,
        league_type=req.league_type,
        league_size=req.league_size,
        qb_td_points=req.qb_td_points,
        bonus_100yd_rushing=req.bonus_100yd_rushing,
        bonus_100yd_receiving=req.bonus_100yd_receiving,
        bonus_first_downs=req.bonus_first_downs,
        weight_prior_year=req.weight_prior_year,
        weight_espn=req.weight_espn,
        weight_consensus=req.weight_consensus,
    )


def _schema_to_rule(schema) -> Rule:
    return Rule(
        name=schema.name,
        conditions=[RuleCondition(field=c.field, operator=c.operator, value=c.value) for c in schema.conditions],
        effect=RuleEffect(type=schema.effect.type, value=schema.effect.value),
        enabled=schema.enabled,
        weight=schema.weight,
    )


def _get_stat(stats: list[PlayerStat]) -> Optional[PlayerStat]:
    if not stats:
        return None
    return max(stats, key=lambda s: s.season)


def _get_projection(projections: list[Projection], source: str, fmt: str) -> Optional[float]:
    for p in projections:
        if p.source == source and p.scoring_format == fmt:
            return p.projected_points
    return None


def _get_adp(adp_entries: list[ADPData], fmt: str) -> Optional[float]:
    for a in adp_entries:
        if a.format == fmt:
            return a.adp
    return None


@router.post("/generate", response_model=GenerateResponse)
async def generate_tiers(req: GenerateRequest, db: AsyncSession = Depends(get_db)) -> GenerateResponse:
    settings = _build_league_settings(req)
    scoring_fmt = req.scoring_format.value

    # Merge built-in + user-provided rules
    builtin_by_name = {r.name: r for r in BUILTIN_RULES}
    rules: list[Rule] = []
    for schema in req.rules:
        if schema.name in builtin_by_name:
            # user can override enabled/weight on built-in rules
            br = builtin_by_name[schema.name]
            br.enabled = schema.enabled
            br.weight = schema.weight
            rules.append(br)
        else:
            rules.append(_schema_to_rule(schema))
    # Add any built-in rules not mentioned by the user (with defaults)
    mentioned = {s.name for s in req.rules}
    for r in BUILTIN_RULES:
        if r.name not in mentioned:
            rules.append(r)

    result = await db.execute(
        select(Player)
        .options(
            selectinload(Player.stats),
            selectinload(Player.projections),
            selectinload(Player.adp_entries),
        )
    )
    players = result.scalars().all()

    tiered: list[TieredPlayer] = []
    for player in players:
        stat = _get_stat(player.stats)
        espn_pts = _get_projection(player.projections, "espn", scoring_fmt)
        fp_pts = _get_projection(player.projections, "fantasypros", scoring_fmt)

        # Prior year actual: compute from raw stats if available
        prior_actual: Optional[float] = None
        if stat:
            ps = PlayerStats(
                targets=stat.targets or 0,
                receptions=stat.receptions or 0,
                rec_yards=stat.rec_yards or 0.0,
                rec_tds=stat.rec_tds or 0,
                rush_att=stat.rush_att or 0,
                rush_yards=stat.rush_yards or 0.0,
                rush_tds=stat.rush_tds or 0,
                pass_att=stat.pass_att or 0,
                pass_yards=stat.pass_yards or 0.0,
                pass_tds=stat.pass_tds or 0,
                interceptions=stat.interceptions or 0,
                games_played=stat.games_played or 1,
            )
            prior_actual = calculate_fantasy_points(ps, settings, position=player.position)

        blended = blend_scores(
            prior_year_actual=prior_actual,
            espn_projection=espn_pts,
            consensus_projection=fp_pts,
            settings=settings,
        )

        flags_list: list[str] = []
        if prior_actual is None and espn_pts is None and fp_pts is None:
            flags_list.append("Rookie — Limited Data")
        elif espn_pts is None and fp_pts is None:
            flags_list.append("Projection Unavailable")

        ctx = PlayerContext(
            player_id=player.id,
            position=player.position,
            age=player.age or 0,
            snap_pct=stat.snap_pct if stat else None,
            carry_share=stat.carry_share if stat else None,
            target_share=stat.target_share if stat else None,
            games_played=stat.games_played if stat else None,
            years_exp=player.years_exp or 0,
            adp=_get_adp(player.adp_entries, scoring_fmt),
            projected_score=blended,
            new_team=False,   # populated by data pipeline in Plan 2
            new_coach=False,  # populated by data pipeline in Plan 2
            actual_tds=stat.actual_tds if stat else None,
            expected_tds=stat.expected_tds if stat else None,
        )

        rule_result = apply_rules(blended, ctx, rules)
        rule_result.flags.extend(flags_list)

        tiered.append(TieredPlayer(
            player_id=player.id,
            name=player.name,
            position=player.position,
            team=player.team,
            age=player.age,
            adjusted_score=rule_result.adjusted_score,
            projected_score_raw=blended,
            prior_year_actual=prior_actual,
            adp_standard=_get_adp(player.adp_entries, "standard"),
            adp_ppr=_get_adp(player.adp_entries, "ppr"),
            adp_dynasty=_get_adp(player.adp_entries, "dynasty"),
            flags=rule_result.flags,
            rules_applied=rule_result.rules_applied,
            overall_rank=0,
            overall_tier=0,
            positional_tier="",
        ))

    ranked = assign_tiers(tiered)
    today = str(date.today())

    return GenerateResponse(
        players=[TieredPlayerOut(**p.__dict__) for p in ranked],
        total=len(ranked),
        data_as_of=today,
    )
```

- [ ] **Step 5: Write `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate, rules, players, data

app = FastAPI(title="AutoTiers API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(data.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Verify the app starts (no DB required for health check)**

```bash
cd backend
uvicorn app.main:app --port 8000 &
sleep 2
curl http://localhost:8000/health
# Expected: {"status":"ok"}
kill %1
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/ backend/app/main.py
git commit -m "feat: add FastAPI app and all API routes"
```

---

## Task 11: Integration Tests (generate endpoint)

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Write `backend/tests/conftest.py`**

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport
from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Write `backend/tests/test_api.py`**

```python
import pytest
from datetime import date
from app.models.player import Player, PlayerStat
from app.models.projection import Projection


async def _seed(db):
    players = [
        Player(id="wr1", name="Chase",     position="WR", team="CIN", age=25, years_exp=4),
        Player(id="rb1", name="Henry",     position="RB", team="TEN", age=30, years_exp=9),
        Player(id="qb1", name="Allen",     position="QB", team="BUF", age=28, years_exp=6),
    ]
    for p in players:
        db.add(p)

    stats = [
        PlayerStat(player_id="wr1", season=2025, receptions=100, rec_yards=1400.0, rec_tds=10,
                   targets=120, rush_att=0, rush_yards=0.0, rush_tds=0,
                   pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
                   games_played=17, carry_share=None, target_share=0.30,
                   snap_pct=0.95, red_zone_looks=12, actual_tds=10, expected_tds=9.0),
        PlayerStat(player_id="rb1", season=2025, rush_att=280, rush_yards=1600.0, rush_tds=16,
                   receptions=30, rec_yards=200.0, rec_tds=1, targets=40,
                   pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
                   games_played=17, carry_share=0.72, target_share=None,
                   snap_pct=0.70, red_zone_looks=25, actual_tds=17, expected_tds=14.0),
        PlayerStat(player_id="qb1", season=2025, pass_att=580, pass_yards=4300.0, pass_tds=36,
                   interceptions=6, rush_att=50, rush_yards=400.0, rush_tds=6,
                   receptions=0, rec_yards=0.0, rec_tds=0, targets=0,
                   games_played=17, carry_share=None, target_share=None,
                   snap_pct=1.0, red_zone_looks=0, actual_tds=42, expected_tds=None),
    ]
    for s in stats:
        db.add(s)

    projs = [
        Projection(player_id="wr1", source="espn",        scoring_format="ppr", projected_points=350.0, last_updated=date.today()),
        Projection(player_id="wr1", source="fantasypros",  scoring_format="ppr", projected_points=340.0, last_updated=date.today()),
        Projection(player_id="rb1", source="espn",        scoring_format="ppr", projected_points=330.0, last_updated=date.today()),
        Projection(player_id="rb1", source="fantasypros",  scoring_format="ppr", projected_points=320.0, last_updated=date.today()),
        Projection(player_id="qb1", source="espn",        scoring_format="ppr", projected_points=410.0, last_updated=date.today()),
        Projection(player_id="qb1", source="fantasypros",  scoring_format="ppr", projected_points=400.0, last_updated=date.today()),
    ]
    for proj in projs:
        db.add(proj)

    await db.commit()


_GENERATE_BODY = {
    "scoring_format": "ppr",
    "league_type": "standard",
    "league_size": 12,
    "qb_td_points": 4.0,
    "bonus_100yd_rushing": False,
    "bonus_100yd_receiving": False,
    "bonus_first_downs": False,
    "weight_prior_year": 0.40,
    "weight_espn": 0.30,
    "weight_consensus": 0.30,
    "rules": [],
}


async def test_health(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_generate_returns_all_players(async_client, test_db):
    await _seed(test_db)
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    ranks = sorted(p["overall_rank"] for p in data["players"])
    assert ranks == [1, 2, 3]


async def test_generate_rank_one_has_highest_score(async_client, test_db):
    await _seed(test_db)
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    by_rank = {p["overall_rank"]: p for p in resp.json()["players"]}
    rank1_score = by_rank[1]["adjusted_score"]
    assert all(rank1_score >= by_rank[r]["adjusted_score"] for r in [2, 3])


async def test_generate_empty_db_returns_empty(async_client):
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_generate_invalid_weights_returns_422(async_client):
    body = {**_GENERATE_BODY, "weight_prior_year": 0.5, "weight_espn": 0.5, "weight_consensus": 0.5}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 422


async def test_list_rules_returns_builtin_rules(async_client):
    resp = await async_client.get("/api/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 15
    assert all("name" in r and "conditions" in r for r in rules)


async def test_data_status_returns_dict(async_client, test_db):
    resp = await async_client.get("/api/data/status")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
```

- [ ] **Step 3: Run the full test suite**

```bash
cd backend
pytest tests/ -v --tb=short
```

Expected: all tests PASSED (scoring, rules, tiers, api).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_api.py
git commit -m "test: add integration tests for API endpoints"
```

---

## Task 12: APScheduler Setup

**Files:**
- Create: `backend/app/scheduler.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write `backend/app/scheduler.py`**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.data.fetcher import fetcher
from app.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _refresh_job() -> None:
    async with AsyncSessionLocal() as db:
        status = await fetcher.refresh_all(db)
        logger.info("Data refresh complete: %s", status)


def setup_scheduler() -> None:
    # Weekly refresh June–July (Sunday midnight)
    scheduler.add_job(_refresh_job, CronTrigger(day_of_week="sun", hour=0, month="6,7"), id="weekly_refresh")
    # Daily refresh August–September (midnight)
    scheduler.add_job(_refresh_job, CronTrigger(hour=0, month="8,9"), id="daily_refresh")
    scheduler.start()
    logger.info("Scheduler started")
```

- [ ] **Step 2: Wire the scheduler into `backend/app/main.py`** (add the lifespan handler)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate, rules, players, data
from app.scheduler import setup_scheduler, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(title="AutoTiers API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(data.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests still PASSED.

- [ ] **Step 4: Commit**

```bash
git add backend/app/scheduler.py backend/app/main.py
git commit -m "feat: add APScheduler for automated data refresh"
```

---

## Self-Review Notes

**Spec coverage:**
- Architecture ✓ (FastAPI + SQLAlchemy + PostgreSQL)
- Database schema ✓ (all 5 tables)
- Scoring engine ✓ (all settings, blended weights, configurable)
- Rules engine ✓ (18 built-in rules, custom rule support, weight/enable toggles)
- Tier algorithm ✓ (Jenks per position, then merge)
- CSV output — **not in this plan.** The generate endpoint returns JSON. A `/api/generate/csv` endpoint that streams a CSV response should be added. Add as Task 13 below.
- API endpoints ✓ (/generate, /rules, /players, /data/status, /data/refresh)

---

## Task 13: CSV Download Endpoint

**Files:**
- Modify: `backend/app/api/generate.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Add a failing test for the CSV endpoint**

Add to `backend/tests/test_api.py`:

```python
async def test_generate_csv_returns_csv_content(async_client, test_db):
    await _seed(test_db)
    resp = await async_client.post("/api/generate/csv", json=_GENERATE_BODY)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().split("\n")
    assert lines[0].startswith("overall_rank")   # header row
    assert len(lines) == 4                        # header + 3 players
```

- [ ] **Step 2: Run and confirm the test fails**

```bash
pytest tests/test_api.py::test_generate_csv_returns_csv_content -v
```

Expected: FAIL with 404.

- [ ] **Step 3: Add the CSV route to `backend/app/api/generate.py`**

Add after the existing `/generate` route:

```python
import csv
import io
from fastapi.responses import StreamingResponse


@router.post("/generate/csv")
async def generate_tiers_csv(req: GenerateRequest, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    response = await generate_tiers(req, db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "overall_rank", "player", "position", "team", "age",
        "overall_tier", "positional_tier",
        "adjusted_score", "projected_score_raw", "prior_year_actual",
        "adp_standard", "adp_ppr", "adp_dynasty",
        "flags", "rules_applied",
    ])
    for p in response.players:
        writer.writerow([
            p.overall_rank, p.name, p.position, p.team, p.age,
            p.overall_tier, p.positional_tier,
            p.adjusted_score, p.projected_score_raw, p.prior_year_actual,
            p.adp_standard, p.adp_ppr, p.adp_dynasty,
            "|".join(p.flags), "|".join(p.rules_applied),
        ])
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=autotiers.csv"},
    )
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
pytest tests/test_api.py -v --tb=short
```

Expected: all API tests PASSED including the new CSV test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/generate.py backend/tests/test_api.py
git commit -m "feat: add CSV download endpoint"
```

---

## What's Next

- **Plan 2 — Data Pipeline:** Real implementations of the four data fetchers (`nfl_data_py`, FantasyPros scraper, ESPN unofficial API client, Sleeper API client) plus the `new_team` / `new_coach` / `red_zone_looks` fields that are currently stubbed in `PlayerContext`.
- **Plan 3 — Frontend:** React + Vite app with the three-panel UI (Settings, Rules, Tiers), linked weight sliders, rule toggles, in-browser tier preview, and CSV download button.
