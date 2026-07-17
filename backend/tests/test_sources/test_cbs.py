import pytest
import respx
from httpx import Response
from sqlalchemy import event, select
from app.data.sources.cbs import CBSFetcher
from app.models import Player, Projection


# A table layout matching CBS's actual structure: <table class="TableBase">
# with a header row containing a fantasy-points column, then tbody rows
# with the player name (and team in a <small>) followed by stat cells.
def _valid_cbs_html(rows: list[tuple[str, str, str]]) -> str:
    """rows is [(player_name, team_code, projected_points), ...].

    Modeled on CBS's table: the first cell contains just the player name
    (the source code's get_text(strip=True) doesn't separate the team out
    cleanly from the name, so we put the team in its own cell for the
    parser's purposes). Team is added as a sibling <small> sibling only
    when the test wants to exercise the team-extraction path.
    """
    body = "".join(
        f"""<tr>
            <td>{name}</td>
            <td>{team}</td>
            <td>{pts}</td>
        </tr>"""
        for name, team, pts in rows
    )
    return f"""<html><body>
        <table class="TableBase">
            <thead><tr><th>Player</th><th>Team</th><th>FPTS</th></tr></thead>
            <tbody>{body}</tbody>
        </table>
    </body></html>"""


def test_cbs_fetcher_name():
    assert CBSFetcher.name == "cbs"


@pytest.mark.asyncio
async def test_cbs_fetcher_handles_network_failure_gracefully(test_db):
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=r"/fantasy/football/projections/.*").mock(return_value=Response(500))
        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_cbs_fetcher_handles_empty_html_gracefully(test_db):
    """If the page returns 200 but with no parseable table, return failed with warning."""
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=r"/fantasy/football/projections/.*").mock(
            return_value=Response(200, text="<html><body><h1>Loading...</h1></body></html>"),
        )
        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "JS-rendered" in (result.error or "") or "client-side rendered" in (result.error or "") or "investigation" in (result.error or "")


@pytest.mark.asyncio
async def test_cbs_fetcher_parses_valid_table_and_upserts_projections(test_db):
    """Happy path: a valid CBS-style table results in matched players + projection upserts."""
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    await test_db.commit()

    html = _valid_cbs_html([
        ("Ja'Marr Chase", "CIN", "298.5"),
        ("Mystery Player", "FA", "120.0"),  # won't match
    ])

    with respx.mock(base_url="https://www.cbssports.com") as router:
        # Only the WR endpoints return data; others return an empty table.
        router.get(url__regex=r"/fantasy/football/projections/WR/.*").mock(
            return_value=Response(200, text=html),
        )
        router.get(url__regex=r"/fantasy/football/projections/(QB|RB|TE)/.*").mock(
            return_value=Response(200, text="<html><body><table class='TableBase'><tbody></tbody></table></body></html>"),
        )

        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)

    assert result.success is True
    # 1 matched player × 3 scoring formats = 3 upserts
    assert result.rows_upserted == 3

    proj_ppr = await test_db.scalar(
        select(Projection).where(
            Projection.player_id == "6794",
            Projection.source == "cbs",
            Projection.scoring_format == "ppr",
        )
    )
    assert proj_ppr is not None
    assert proj_ppr.projected_points == 298.5


@pytest.mark.asyncio
async def test_cbs_fetcher_skips_rows_with_unparseable_points(test_db):
    """A row whose points cell isn't a number should be skipped, not crash the fetcher."""
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    await test_db.commit()

    html = _valid_cbs_html([
        ("Ja'Marr Chase", "CIN", "298.5"),       # ok
        ("Garbage Row", "XXX", "not-a-number"),  # skipped — ValueError
    ])

    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=r"/fantasy/football/projections/WR/.*").mock(
            return_value=Response(200, text=html),
        )
        router.get(url__regex=r"/fantasy/football/projections/(QB|RB|TE)/.*").mock(
            return_value=Response(200, text="<html><body><table class='TableBase'><tbody></tbody></table></body></html>"),
        )

        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)

    assert result.success is True
    # Only Chase upserts (3 formats), the garbage row is skipped silently.
    assert result.rows_upserted == 3


@pytest.mark.asyncio
async def test_cbs_fetcher_queries_position_once_not_per_row(test_engine, test_db):
    """N+1 guard: fuzzy matching must issue at most one WR position query for the
    whole run, not one per row × scoring format. Three WR rows across three
    scoring formats would be nine queries without the per-run PositionMatchIndex."""
    for i in range(3):
        test_db.add(Player(id=f"wr_{i}", name=f"Wide Receiver {i}", position="WR", team="MIN"))
    await test_db.commit()

    html = _valid_cbs_html([
        ("Wide Receiver 0", "MIN", "298.5"),
        ("Wide Receiver 1", "MIN", "271.0"),
        ("Wide Receiver 2", "MIN", "245.5"),
    ])

    position_queries: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.split()).lower()
        if "from players" in normalized and "players.position" in normalized:
            position_queries.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", _listener)
    try:
        with respx.mock(base_url="https://www.cbssports.com") as router:
            router.get(url__regex=r"/fantasy/football/projections/WR/.*").mock(
                return_value=Response(200, text=html),
            )
            router.get(url__regex=r"/fantasy/football/projections/(QB|RB|TE)/.*").mock(
                return_value=Response(200, text="<html><body><table class='TableBase'><tbody></tbody></table></body></html>"),
            )
            fetcher = CBSFetcher()
            result = await fetcher.fetch(test_db)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", _listener)

    assert result.success is True
    # 3 players × 3 scoring formats = 9 upserts, but only ONE WR position query.
    assert result.rows_upserted == 9
    assert len(position_queries) == 1, (
        f"expected one WR position query for the whole run, got {len(position_queries)} "
        "(N+1 regression — PositionMatchIndex not shared across rows/formats)"
    )


@pytest.mark.parametrize("n_rows", [1, 5, 20])
@pytest.mark.asyncio
async def test_cbs_parse_projections_existence_check_is_one_select(test_engine, test_db, n_rows):
    """N+1 guard: the existence check must be a single pre-load SELECT against
    ``projections`` for the whole page, regardless of how many rows are parsed —
    not one round-trip SELECT per row."""
    from datetime import date as _date

    for i in range(n_rows):
        test_db.add(Player(id=f"wr_{i}", name=f"Wide Receiver {i}", position="WR", team="MIN"))
    await test_db.commit()

    html = _valid_cbs_html([
        (f"Wide Receiver {i}", "MIN", f"{300 - i}.0") for i in range(n_rows)
    ])

    projection_selects: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.split()).lower()
        if normalized.startswith("select") and "from projections" in normalized:
            projection_selects.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", _listener)
    try:
        fetcher = CBSFetcher()
        upserted = await fetcher._parse_projections(
            test_db, html, "WR", "ppr", _date.today(),
        )
        await test_db.commit()
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", _listener)

    assert upserted == n_rows
    assert len(projection_selects) == 1, (
        f"expected exactly one existence-check SELECT for {n_rows} rows, "
        f"got {len(projection_selects)} (N+1 regression)"
    )


@pytest.mark.asyncio
async def test_cbs_fetcher_updates_existing_projection(test_db):
    """Re-running CBS for the same player should update the existing row, not insert."""
    from datetime import date as _date
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    test_db.add(Projection(
        player_id="6794", source="cbs", scoring_format="ppr",
        projected_points=200.0, last_updated=_date(2025, 1, 1),
    ))
    await test_db.commit()

    html = _valid_cbs_html([("Ja'Marr Chase", "CIN", "350.0")])

    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=r"/fantasy/football/projections/WR/.*").mock(
            return_value=Response(200, text=html),
        )
        router.get(url__regex=r"/fantasy/football/projections/(QB|RB|TE)/.*").mock(
            return_value=Response(200, text="<html><body><table class='TableBase'><tbody></tbody></table></body></html>"),
        )

        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)

    assert result.success is True
    rows = (await test_db.scalars(
        select(Projection).where(
            Projection.player_id == "6794",
            Projection.source == "cbs",
            Projection.scoring_format == "ppr",
        )
    )).all()
    assert len(rows) == 1  # updated, not duplicated
    assert rows[0].projected_points == 350.0
