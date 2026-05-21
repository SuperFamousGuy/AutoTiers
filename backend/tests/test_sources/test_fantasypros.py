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

    # 2 matched WR projections × 3 formats (STD/HALF/PPR) = 6 projection upserts
    # + 2 ADP rows (PPR only — other ADP URLs return empty fixtures) = 8 upserts.
    # Mystery Player doesn't match → not upserted.
    assert result.rows_upserted >= 4  # at minimum: 2 PPR projections + 2 ADPs

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
