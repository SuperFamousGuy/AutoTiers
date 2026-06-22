import pytest
import respx
from httpx import Response

from sqlalchemy import select
from app.models import Player, PlayerContract


@pytest.fixture
def mock_spotrac():
    """Mock Spotrac cap-hit pages per position."""
    with respx.mock(base_url="https://www.spotrac.com") as router:
        router.get(url__regex=r"/nfl/positional/QB/cap_hit/?").mock(
            return_value=Response(200, text=(
                "<html><body><table>"
                "<thead><tr><th>Player</th><th>Cap Hit</th></tr></thead>"
                "<tbody>"
                "<tr><td>Patrick Mahomes</td><td>$45,000,000</td></tr>"
                "</tbody>"
                "</table></body></html>"
            ))
        )
        for pos in ("RB", "WR", "TE"):
            router.get(url__regex=rf"/nfl/positional/{pos}/cap_hit/?").mock(
                return_value=Response(200, text="<html><body></body></html>")
            )
        yield router


@pytest.mark.asyncio
async def test_spotrac_fetcher_upserts_player_contracts(test_db, mock_spotrac):
    from app.data.sources.spotrac import SpotracFetcher

    # Seed a player so name-matching can resolve
    test_db.add(Player(id="p-1", name="Patrick Mahomes", position="QB", team="KC"))
    await test_db.commit()

    fetcher = SpotracFetcher()
    result = await fetcher.fetch(test_db)
    assert result.success
    assert result.rows_upserted >= 1

    rows = (await test_db.scalars(select(PlayerContract))).all()
    assert len(rows) == 1
    assert rows[0].player_id == "p-1"
    assert rows[0].cap_hit == 45_000_000.0


@pytest.mark.asyncio
async def test_spotrac_fetcher_fails_when_zero_upserted(test_db, mock_spotrac):
    """HTTP succeeds but nothing is upserted (no matching player) → failure.

    Mirrors cbs.py: upserted==0 must surface at /api/data/status as a dead
    source rather than masquerade as a successful fetch.
    """
    from app.data.sources.spotrac import SpotracFetcher

    # No matching player seeded, so every scraped row is dropped.
    fetcher = SpotracFetcher()
    result = await fetcher.fetch(test_db)
    assert result.success is False
    assert result.rows_upserted == 0
    assert "investigation" in (result.error or "")
    rows = (await test_db.scalars(select(PlayerContract))).all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_spotrac_fetcher_fails_when_all_positions_404(test_db):
    """Every position 404s → all-positions-failed failure (pre-existing path)."""
    import respx
    from httpx import Response
    from app.data.sources.spotrac import SpotracFetcher

    with respx.mock(base_url="https://www.spotrac.com") as router:
        router.get(url__regex=r"/nfl/positional/.*/cap_hit/?").mock(
            return_value=Response(404)
        )
        fetcher = SpotracFetcher()
        result = await fetcher.fetch(test_db)

    assert result.success is False
    assert result.rows_upserted == 0
    assert "all positions failed" in (result.error or "")


@pytest.mark.asyncio
async def test_spotrac_fetcher_is_idempotent(test_db, mock_spotrac):
    from app.data.sources.spotrac import SpotracFetcher

    test_db.add(Player(id="p-1", name="Patrick Mahomes", position="QB", team="KC"))
    await test_db.commit()

    fetcher = SpotracFetcher()
    await fetcher.fetch(test_db)
    await fetcher.fetch(test_db)

    rows = (await test_db.scalars(select(PlayerContract))).all()
    assert len(rows) == 1
    assert rows[0].cap_hit == 45_000_000.0
