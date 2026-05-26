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
async def test_spotrac_fetcher_skips_unmatched_player(test_db, mock_spotrac):
    from app.data.sources.spotrac import SpotracFetcher

    # No matching player seeded
    fetcher = SpotracFetcher()
    result = await fetcher.fetch(test_db)
    assert result.success
    rows = (await test_db.scalars(select(PlayerContract))).all()
    assert len(rows) == 0


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
