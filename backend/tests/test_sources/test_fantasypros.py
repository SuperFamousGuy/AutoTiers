import pytest
import respx
from datetime import date
from httpx import Response
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
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


_EMPTY_TABLE = "<html><body><table id='data'><tbody></tbody></table></body></html>"


async def _committed_counts(test_engine):
    """Open a fresh session (sees only COMMITTED data) and count FantasyPros
    projection + ADP rows. Used to prove fetch() persisted exactly what its
    SourceResult reports — no phantom rows left for a later commit to pick up."""
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as fresh:
        n_proj = len((await fresh.scalars(
            select(Projection).where(Projection.source == "fantasypros"))).all())
        n_adp = len((await fresh.scalars(
            select(ADPData).where(ADPData.adp_source == "fantasypros"))).all())
    return n_proj, n_adp


@pytest.mark.asyncio
async def test_fantasypros_isolates_midloop_adp_failure(test_db, test_engine):
    """Issue #834: a transient failure on one ADP request must not abort the run
    nor silently commit rows the SourceResult claims don't exist. The successful
    iterations are committed, rows_upserted matches exactly what persisted, and
    success is False because a sub-fetch failed."""
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    await test_db.commit()

    wr_html = _projections_html([("Ja'Marr Chase", "CIN", 340.5)])

    with respx.mock(base_url="https://www.fantasypros.com") as router:
        # WR projections succeed for all three scoring formats → 3 rows.
        router.get(url__regex=r"/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=wr_html))
        router.get(url__regex=r"/nfl/projections/(qb|rb|te|k|dst)\.php.*").mock(
            return_value=Response(200, text=_EMPTY_TABLE))
        # One ADP request fails mid-loop with a transient 503.
        router.get(url__regex=r"/nfl/adp/ppr\.php").mock(
            return_value=Response(503, text="upstream unavailable"))
        router.get(url__regex=r"/nfl/adp/(overall|half-point-ppr)\.php").mock(
            return_value=Response(200, text=_EMPTY_TABLE))

        result = await FantasyProsFetcher().fetch(test_db)

    # A sub-fetch failed → success is False and the error names the failure.
    assert result.success is False
    assert "adp ppr" in result.error
    # rows_upserted equals what actually committed: 3 WR projections, no ADP.
    assert result.rows_upserted == 3

    n_proj, n_adp = await _committed_counts(test_engine)
    assert n_proj == result.rows_upserted == 3
    assert n_adp == 0


@pytest.mark.asyncio
async def test_fantasypros_isolates_midloop_projection_failure(test_db, test_engine):
    """A transient failure on one projection request is skipped; the other
    formats still commit and are reported. Covers the projection-branch guard."""
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    await test_db.commit()

    wr_html = _projections_html([("Ja'Marr Chase", "CIN", 340.5)])

    with respx.mock(base_url="https://www.fantasypros.com") as router:
        # WR HALF projections fail; WR STD + PPR succeed → 2 rows.
        router.get(url__regex=r"/nfl/projections/wr\.php\?scoring=HALF.*").mock(
            return_value=Response(503, text="upstream unavailable"))
        router.get(url__regex=r"/nfl/projections/wr\.php.*").mock(
            return_value=Response(200, text=wr_html))
        router.get(url__regex=r"/nfl/projections/(qb|rb|te|k|dst)\.php.*").mock(
            return_value=Response(200, text=_EMPTY_TABLE))
        router.get(url__regex=r"/nfl/adp/.*").mock(
            return_value=Response(200, text=_EMPTY_TABLE))

        result = await FantasyProsFetcher().fetch(test_db)

    assert result.success is False
    assert "projections wr/half_ppr" in result.error
    assert result.rows_upserted == 2

    n_proj, n_adp = await _committed_counts(test_engine)
    assert n_proj == result.rows_upserted == 2
    assert n_adp == 0


@pytest.mark.asyncio
async def test_fantasypros_all_success_commits_and_reports_true(test_db, test_engine, mock_fantasypros):
    """When every sub-fetch succeeds, success is True and the committed row count
    matches rows_upserted — the happy path still behaves as before."""
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    test_db.add(Player(id="6786", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()

    result = await FantasyProsFetcher().fetch(test_db)
    assert result.success is True
    assert result.error is None

    n_proj, n_adp = await _committed_counts(test_engine)
    assert n_proj + n_adp == result.rows_upserted


@pytest.mark.asyncio
async def test_fantasypros_outer_failure_rolls_back(test_db, test_engine, monkeypatch):
    """A failure outside the per-request guards (e.g. client construction) rolls
    back so no partially-flushed rows survive for the orchestrator's commit, and
    reports rows_upserted=0 / success=False — the atomic-failure invariant."""
    test_db.add(Player(id="6794", name="Ja'Marr Chase", position="WR", team="CIN"))
    await test_db.commit()
    # Simulate an earlier iteration's autoflushed-but-uncommitted write. The
    # outer rollback must discard it rather than let it leak into a later commit.
    test_db.add(Projection(player_id="6794", source="fantasypros",
                           scoring_format="ppr", projected_points=1.0,
                           last_updated=date.today()))
    await test_db.flush()

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("client construction failed")

    monkeypatch.setattr("app.data.sources.fantasypros.httpx.AsyncClient", _Boom)

    result = await FantasyProsFetcher().fetch(test_db)
    assert result.success is False
    assert result.rows_upserted == 0

    # The pending projection was rolled back — a fresh session sees none.
    n_proj, _ = await _committed_counts(test_engine)
    assert n_proj == 0


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
