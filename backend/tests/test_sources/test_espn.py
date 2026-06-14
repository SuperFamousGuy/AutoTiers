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
    with respx.mock(base_url="https://lm-api-reads.fantasy.espn.com") as router:
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

    # Each matched player gets 1 projection row (ppr only).
    # 2 matched players × 1 format = 2 rows.
    assert result.rows_upserted == 2

    rows = (await test_db.scalars(
        select(Projection).where(Projection.player_id == "4017", Projection.source == "espn")
    )).all()
    formats = {r.scoring_format for r in rows}
    assert formats == {"ppr"}
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
    assert len(rows) == 1  # one per format (ppr only), not duplicated


@pytest.mark.asyncio
async def test_espn_handles_http_error(test_db):
    with respx.mock(base_url="https://lm-api-reads.fantasy.espn.com") as router:
        router.get(url__regex=r"/apis/v3/games/ffl/.*").mock(return_value=Response(503))
        fetcher = EspnFetcher(season=2026)
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "503" in (result.error or "")
