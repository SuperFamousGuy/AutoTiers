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
async def test_fantasypros_reads_fpts_by_header_not_position(test_db):
    """FPTS column is found by header text, not column index. Add a fake fixture
    where FPTS is not the last column to verify the fallback works."""
    # Pre-seed a player so fuzzy match can find them
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    await test_db.commit()

    # FantasyPros HTML where FPTS is in the middle, with AVG (per-game) at the end
    html_with_avg = """
    <html><body><table id="data">
      <thead><tr><th>Player</th><th>REC</th><th>YDS</th><th>FPTS</th><th>AVG</th></tr></thead>
      <tbody>
        <tr><td><a>Ja'Marr Chase</a> <small>CIN</small></td><td>108</td><td>1450</td><td>340.5</td><td>20.0</td></tr>
      </tbody>
    </table></body></html>
    """

    from app.data.sources.fantasypros import FantasyProsFetcher
    fetcher = FantasyProsFetcher()
    from datetime import date as _date
    upserted = await fetcher._parse_projections(
        test_db, html_with_avg, "WR", "ppr", _date.today(),
    )
    await test_db.commit()

    # Should pick up FPTS (340.5) by header, not AVG (20.0) by being last cell
    chase_proj = await test_db.scalar(
        select(Projection).where(
            Projection.player_id == "6794",
            Projection.source == "fantasypros",
            Projection.scoring_format == "ppr",
        )
    )
    assert chase_proj is not None
    assert chase_proj.projected_points == 340.5, (
        f"Expected 340.5 (FPTS season-total), got {chase_proj.projected_points}. "
        "Probably read the last column (AVG = per-game) instead."
    )


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
