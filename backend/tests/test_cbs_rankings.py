"""Tests for the CBS expert rankings probe/scaffold (issue #422).

Placed at the top level of ``tests/`` (not ``tests/test_sources/``) on purpose:
the CI backend run ignores ``tests/test_sources/`` (it OOMs there), and the
diff-coverage gate computes coverage from that same run. These tests must run
in-suite to cover the new fetcher's lines.
"""
import pytest
import respx
from httpx import Response

from app.data.sources.cbs_rankings import CBSRankingsFetcher, RankingRow


_RANKINGS_PATH_RE = r"/fantasy/football/rankings/.*"


def _populated_html(rows: list[tuple[int, str, str, str]]) -> str:
    """rows is [(rank, player_name, team, position), ...].

    Models the *re-enable* contract: a server-rendered ``.rankings-table`` with
    a rank cell, a player anchor carrying the team in a ``<small>``, and a
    position cell.
    """
    body = "".join(
        f"""<tr>
            <td>{rank}</td>
            <td><a href="/fantasy/football/players/{rank}/">{name}</a><small>{team}</small></td>
            <td>{position}</td>
        </tr>"""
        for rank, name, team, position in rows
    )
    return f"""<html><body>
        <table class="rankings-table">
            <thead><tr><th>Rank</th><th>Player</th><th>Pos</th></tr></thead>
            <tbody>{body}</tbody>
        </table>
    </body></html>"""


# The real-world state today: the client-side-rendered Next.js shell. The
# ``.rankings-table`` token only ever appears inside an analytics tracking
# config attribute, never as an actual populated <table>.
_SHELL_HTML = (
    "<html><body><h1>Rankings</h1>"
    "<div data-options='{\"rankingsTable\":\".rankings-table\"}'></div>"
    "</body></html>"
)


def test_cbs_rankings_fetcher_name():
    assert CBSRankingsFetcher.name == "cbs_rankings"


@pytest.mark.asyncio
async def test_blocked_on_client_side_rendered_shell():
    """The page returns 200 but has no rankings rows → failed with the blocker error."""
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=_RANKINGS_PATH_RE).mock(
            return_value=Response(200, text=_SHELL_HTML),
        )
        result = await CBSRankingsFetcher().fetch()

    assert result.success is False
    assert result.rows_upserted == 0
    assert "client-side rendered" in (result.error or "")
    assert "#422" in (result.error or "")


@pytest.mark.asyncio
async def test_network_failure_is_handled_gracefully():
    """An HTTP error on every format page is isolated; result is failed, not raised."""
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=_RANKINGS_PATH_RE).mock(return_value=Response(500))
        result = await CBSRankingsFetcher().fetch()

    assert result.success is False
    assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_extracts_rankings_when_markup_is_server_rendered():
    """Re-enable path: a populated .rankings-table is parsed and counted."""
    html = _populated_html([
        (1, "Ja'Marr Chase", "CIN", "WR"),
        (2, "Bijan Robinson", "ATL", "RB"),
    ])
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=_RANKINGS_PATH_RE).mock(
            return_value=Response(200, text=html),
        )
        result = await CBSRankingsFetcher().fetch()

    assert result.success is True
    # 2 players × 3 scoring formats = 6 extracted rows.
    assert result.rows_upserted == 6
    assert result.error is None


def test_parse_rankings_extracts_fields():
    """The parser pulls rank, name, team, and position from a populated table."""
    html = _populated_html([
        (1, "Ja'Marr Chase", "CIN", "WR"),
        (2, "Bijan Robinson", "ATL", "RB"),
    ])
    rows = CBSRankingsFetcher._parse_rankings(html, "ppr")

    assert rows == [
        RankingRow(rank=1, name="Ja'Marr Chase", team="CIN", position="WR", scoring_format="ppr"),
        RankingRow(rank=2, name="Bijan Robinson", team="ATL", position="RB", scoring_format="ppr"),
    ]


def test_parse_rankings_returns_empty_for_shell():
    """No populated table → no rows (the everyday blocked case)."""
    assert CBSRankingsFetcher._parse_rankings(_SHELL_HTML, "standard") == []


def test_parse_rankings_returns_empty_when_no_table_at_all():
    """Markup with no <table> element yields no rows, not an error."""
    assert CBSRankingsFetcher._parse_rankings("<html><body>nope</body></html>", "ppr") == []


def test_parse_rankings_falls_back_to_row_order_for_rank():
    """When no explicit numeric rank cell exists, rank falls back to row order."""
    html = """<html><body><table class="rankings-table"><tbody>
        <tr><td><a href="#">First Guy</a><small>SF</small></td><td>WR</td></tr>
        <tr><td><a href="#">Second Guy</a><small>KC</small></td><td>RB</td></tr>
    </tbody></table></body></html>"""
    rows = CBSRankingsFetcher._parse_rankings(html, "standard")

    assert [r.rank for r in rows] == [1, 2]
    assert [r.name for r in rows] == ["First Guy", "Second Guy"]


def test_parse_rankings_skips_rows_without_a_name():
    """A row with an empty player cell is skipped, not fatal."""
    html = """<html><body><table class="rankings-table"><tbody>
        <tr><td>1</td><td><a href="#"></a></td><td>WR</td></tr>
        <tr><td>2</td><td><a href="#">Real Player</a><small>SF</small></td><td>RB</td></tr>
    </tbody></table></body></html>"""
    rows = CBSRankingsFetcher._parse_rankings(html, "standard")

    assert len(rows) == 1
    assert rows[0].name == "Real Player"
    assert rows[0].rank == 2
