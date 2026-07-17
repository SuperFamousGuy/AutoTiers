import pytest
import respx
from httpx import Response
from pathlib import Path

from sqlalchemy import event, select
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
        router.get(url__regex=r"/nfl/projections/(qb|rb|te|k|dst)\.php.*").mock(
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


def _projections_html(rows):
    """rows is [(name, team, fpts), ...] → a FantasyPros-style projections table."""
    body = "".join(
        f"<tr><td><a>{name}</a> <small>{team}</small></td><td>{pts}</td></tr>"
        for name, team, pts in rows
    )
    return (
        "<html><body><table id='data'>"
        "<thead><tr><th>Player</th><th>FPTS</th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


def _adp_html(rows):
    """rows is [(name, team, pos, adp), ...] → a FantasyPros-style ADP table."""
    body = "".join(
        f"<tr><td>{i}</td><td><a>{name}</a> <small>{team}</small></td>"
        f"<td>{pos}</td><td>{adp}</td></tr>"
        for i, (name, team, pos, adp) in enumerate(rows, start=1)
    )
    return (
        "<html><body><table id='data'>"
        "<thead><tr><th>Rank</th><th>Player</th><th>Pos</th><th>ADP</th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


def _count_selects(test_engine, from_table):
    """Context-manager-free helper: returns (listener, captured_list)."""
    captured: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.split()).lower()
        if normalized.startswith("select") and f"from {from_table}" in normalized:
            captured.append(statement)

    return _listener, captured


@pytest.mark.parametrize("n_rows", [1, 5, 20])
@pytest.mark.asyncio
async def test_fantasypros_projections_existence_check_is_one_select(test_engine, test_db, n_rows):
    """N+1 guard: parsing N projection rows issues exactly one pre-load SELECT
    against ``projections``, not one per row."""
    from datetime import date as _date

    for i in range(n_rows):
        test_db.add(Player(id=f"wr_{i}", name=f"Wide Receiver {i}", position="WR", team="MIN"))
    await test_db.commit()

    html = _projections_html([(f"Wide Receiver {i}", "MIN", 300 - i) for i in range(n_rows)])

    listener, projection_selects = _count_selects(test_engine, "projections")
    event.listen(test_engine.sync_engine, "before_cursor_execute", listener)
    try:
        fetcher = FantasyProsFetcher()
        upserted = await fetcher._parse_projections(test_db, html, "WR", "ppr", _date.today())
        await test_db.commit()
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", listener)

    assert upserted == n_rows
    assert len(projection_selects) == 1, (
        f"expected one existence-check SELECT for {n_rows} rows, "
        f"got {len(projection_selects)} (N+1 regression)"
    )


@pytest.mark.parametrize("n_rows", [1, 5, 20])
@pytest.mark.asyncio
async def test_fantasypros_adp_existence_check_is_one_select(test_engine, test_db, n_rows):
    """N+1 guard: parsing N ADP rows issues exactly one pre-load SELECT against
    ``adp_data``, not one per row."""
    from datetime import date as _date

    for i in range(n_rows):
        test_db.add(Player(id=f"wr_{i}", name=f"Wide Receiver {i}", position="WR", team="MIN"))
    await test_db.commit()

    html = _adp_html([(f"Wide Receiver {i}", "MIN", "WR", i + 1) for i in range(n_rows)])

    listener, adp_selects = _count_selects(test_engine, "adp_data")
    event.listen(test_engine.sync_engine, "before_cursor_execute", listener)
    try:
        fetcher = FantasyProsFetcher()
        upserted = await fetcher._parse_adp(test_db, html, "ppr", _date.today())
        await test_db.commit()
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", listener)

    assert upserted == n_rows
    assert len(adp_selects) == 1, (
        f"expected one existence-check SELECT for {n_rows} rows, "
        f"got {len(adp_selects)} (N+1 regression)"
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
