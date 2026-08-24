"""Non-finite score guard at the /api/generate response boundary (#1186).

The whole API serializes with ORJSONResponse, and both orjson and Pydantic
silently coerce NaN/Infinity floats to JSON ``null``. ``TieredPlayerOut``'s
``adjusted_score`` / ``projected_score_raw`` / ``vbd_score`` /
``position_replacement`` are typed non-optional ``float``, so a NaN escaping
scoring would ship to the client as ``null`` with no 500 and no validation
error — and the frontend calls ``.toFixed(1)`` on them directly, crashing the
Tiers view. ``TieredPlayerOut`` now rejects a non-finite score (loudly logged)
so the bug fails fast server-side instead of corrupting the wire response.
"""
import logging

import orjson
import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.main import app
from app.models import Player
from app.engine.tiers import TieredPlayer
from app.schemas.generate import TieredPlayerOut
import app.api.generate as generate_module


def _valid_out_kwargs(**overrides) -> dict:
    kwargs = dict(
        overall_rank=1,
        player_id="p1",
        name="Justin Jefferson",
        position="WR",
        team="MIN",
        age=25,
        overall_tier=1,
        positional_tier="WR1",
        adjusted_score=300.0,
        projected_score_raw=290.0,
        prior_year_actual=280.0,
        espn_projection=None,
        fantasypros_projection=None,
        avg_projection=295.0,
        adp_standard=1.0,
        adp_ppr=1.0,
        adp_half_ppr=1.0,
        adp_dynasty=1.0,
        league_adp=None,
        vbd_score=120.0,
        position_replacement=180.0,
        flags=[],
        rules_applied=[],
        rule_applications=[],
    )
    kwargs.update(overrides)
    return kwargs


# ---- schema-level guard ----------------------------------------------------

def test_finite_scores_accepted_and_serialize_as_numbers():
    out = TieredPlayerOut(**_valid_out_kwargs())
    dumped = orjson.dumps(out.model_dump())
    # The invariant the guard protects: a numeric field, never null.
    assert b'"vbd_score":null' not in dumped
    assert b'"vbd_score":120.0' in dumped


@pytest.mark.parametrize(
    "field", ["adjusted_score", "projected_score_raw", "vbd_score", "position_replacement"]
)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_score_rejected(field, bad):
    with pytest.raises(ValidationError):
        TieredPlayerOut(**_valid_out_kwargs(**{field: bad}))


def test_non_finite_score_is_logged_loudly(caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValidationError):
            TieredPlayerOut(**_valid_out_kwargs(vbd_score=float("nan")))
    assert any(
        "non-finite score" in rec.getMessage() and rec.levelno == logging.ERROR
        for rec in caplog.records
    )


def test_without_the_guard_a_nan_would_have_shipped_as_null():
    # Documents the exact silent-corruption failure mode the guard exists to
    # stop: absent the validator, orjson coerces the NaN straight to JSON null.
    assert orjson.dumps({"vbd_score": float("nan")}) == b'{"vbd_score":null}'


# ---- endpoint boundary -----------------------------------------------------

async def _client_no_reraise(test_engine) -> AsyncClient:
    """A client that returns a 500 response (rather than re-raising) so we can
    inspect the actual bytes on the wire and prove no ``null`` shipped."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


def _base_body() -> dict:
    return {
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
        "rules": {},
    }


@pytest.mark.asyncio
async def test_generate_never_emits_null_for_a_float_field_on_nan(test_engine, monkeypatch, caplog):
    """A NaN reaching the response boundary is rejected, not serialized to null."""
    nan_player = TieredPlayer(
        player_id="p1",
        name="Justin Jefferson",
        position="WR",
        team="MIN",
        age=25,
        adjusted_score=300.0,
        projected_score_raw=290.0,
        prior_year_actual=None,
        adp_standard=None,
        adp_ppr=None,
        adp_half_ppr=None,
        adp_dynasty=None,
        flags=[],
        rules_applied=[],
        overall_rank=1,
        overall_tier=1,
        positional_tier="WR1",
        vbd_score=float("nan"),
        position_replacement=180.0,
    )

    async def fake_run_generate(req, db):
        return [nan_player]

    monkeypatch.setattr(generate_module, "_run_generate", fake_run_generate)

    client = await _client_no_reraise(test_engine)
    try:
        with caplog.at_level(logging.ERROR):
            r = await client.post("/api/generate", json=_base_body())
    finally:
        await client.aclose()
        app.dependency_overrides.clear()

    # The guard tripped: a server error, never a 200 body carrying a null score.
    assert r.status_code == 500
    assert b'"vbd_score":null' not in r.content
    assert b'"vbd_score"' not in r.content  # nothing about this player shipped
    assert any("non-finite score" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_generate_happy_path_emits_numeric_scores(async_client, test_db):
    """Real players flow through with numeric, non-null float fields."""
    test_db.add_all([
        Player(id="p1", name="Justin Jefferson", position="WR", team="MIN"),
        Player(id="p2", name="Christian McCaffrey", position="RB", team="SF"),
    ])
    await test_db.commit()

    r = await async_client.post("/api/generate", json=_base_body())
    assert r.status_code == 200
    assert b'"vbd_score":null' not in r.content
    for p in r.json()["players"]:
        for field in ("adjusted_score", "projected_score_raw", "vbd_score", "position_replacement"):
            assert isinstance(p[field], (int, float))
