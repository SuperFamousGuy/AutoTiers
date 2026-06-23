"""Tests for the NFL.com expert/draft rankings probe/scaffold (issue #431).

Placed at the top level of ``tests/`` (not ``tests/test_sources/``) on purpose,
exactly like ``test_cbs_rankings.py``: keeping them in the lightweight set means
they always run in the standard backend suite, so the diff-coverage gate sees
them and the new fetcher's lines are covered.
"""
import pytest
import respx
from httpx import Response

from app.data.sources.nfl_rankings import NflRankingsFetcher, RankingRow


_RANKINGS_PATH_RE = r"/research/rankings.*"


def _populated_html(rows: list[tuple[int, str, str, str]]) -> str:
    """rows is [(rank, player_name, team, position), ...].

    Models the *re-enable* contract: a server-rendered NFL.com player table
    (``tableType-player``) with a ``.rank`` cell, a ``.playerName`` anchor, and a
    sibling ``<em>`` carrying ``"POS - TEAM"`` (NFL.com's actual layout).
    """
    body = "".join(
        f"""<tr>
            <td class="rank">{rank}</td>
            <td class="playerNameAndInfo">
                <a href="/players/{rank}" class="playerName">{name}</a>
                <em>{position} - {team}</em>
            </td>
        </tr>"""
        for rank, name, team, position in rows
    )
    return f"""<html><body>
        <table class="tableType-player hasGroups">
            <thead><tr><th>Rank</th><th>Player</th></tr></thead>
            <tbody>{body}</tbody>
        </table>
    </body></html>"""


# The real-world state today: the client-side-rendered NFL.com app shell. The
# rankings table is injected by JS, so the static markup carries no populated
# player table — only a placeholder container the parser must NOT latch onto.
_SHELL_HTML = (
    "<html><body><h1>Rankings</h1>"
    "<div id=\"researchRankings\" data-options='{\"table\":\"tableType-player\"}'></div>"
    "</body></html>"
)


def test_nfl_rankings_fetcher_name():
    assert NflRankingsFetcher.name == "nfl_rankings"


@pytest.mark.asyncio
async def test_blocked_on_client_side_rendered_shell():
    """The page returns 200 but has no rankings rows → failed with the blocker error."""
    with respx.mock(base_url="https://fantasy.nfl.com") as router:
        router.get(url__regex=_RANKINGS_PATH_RE).mock(
            return_value=Response(200, text=_SHELL_HTML),
        )
        result = await NflRankingsFetcher().fetch()

    assert result.success is False
    assert result.rows_upserted == 0
    assert "client-side rendered" in (result.error or "")
    assert "#431" in (result.error or "")


@pytest.mark.asyncio
async def test_network_failure_is_handled_gracefully():
    """An HTTP error on every format page is isolated; result is failed, not raised.

    The error must indicate an HTTP/fetch failure and must NOT be the
    client-side-rendered blocker error: nothing was fetched successfully, so
    attributing the empty result to client-side rendering would be wrong.
    """
    with respx.mock(base_url="https://fantasy.nfl.com") as router:
        router.get(url__regex=_RANKINGS_PATH_RE).mock(return_value=Response(500))
        result = await NflRankingsFetcher().fetch()

    assert result.success is False
    assert result.rows_upserted == 0
    assert "fetch failed" in (result.error or "")
    assert "500" in (result.error or "")
    assert "client-side rendered" not in (result.error or "")


@pytest.mark.asyncio
async def test_extracts_rankings_when_markup_is_server_rendered():
    """Re-enable path: a populated player table is parsed and counted."""
    html = _populated_html([
        (1, "Ja'Marr Chase", "CIN", "WR"),
        (2, "Bijan Robinson", "ATL", "RB"),
    ])
    with respx.mock(base_url="https://fantasy.nfl.com") as router:
        router.get(url__regex=_RANKINGS_PATH_RE).mock(
            return_value=Response(200, text=html),
        )
        result = await NflRankingsFetcher().fetch()

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
    rows = NflRankingsFetcher._parse_rankings(html, "ppr")

    assert rows == [
        RankingRow(rank=1, name="Ja'Marr Chase", team="CIN", position="WR", scoring_format="ppr"),
        RankingRow(rank=2, name="Bijan Robinson", team="ATL", position="RB", scoring_format="ppr"),
    ]


def test_parse_rankings_returns_empty_for_shell():
    """No populated player table → no rows (the everyday blocked case)."""
    assert NflRankingsFetcher._parse_rankings(_SHELL_HTML, "standard") == []


def test_parse_rankings_returns_empty_when_no_table_at_all():
    """Markup with no <table> element yields no rows, not an error."""
    assert NflRankingsFetcher._parse_rankings("<html><body>nope</body></html>", "ppr") == []


def test_parse_rankings_falls_back_to_row_order_for_rank():
    """When no explicit numeric rank cell exists, rank falls back to row order."""
    html = """<html><body><table class="tableType-player"><tbody>
        <tr><td><a class="playerName" href="#">First Guy</a><em>WR - SF</em></td></tr>
        <tr><td><a class="playerName" href="#">Second Guy</a><em>RB - KC</em></td></tr>
    </tbody></table></body></html>"""
    rows = NflRankingsFetcher._parse_rankings(html, "standard")

    assert [r.rank for r in rows] == [1, 2]
    assert [r.name for r in rows] == ["First Guy", "Second Guy"]


def test_parse_rankings_skips_rows_without_a_name():
    """A row with an empty player anchor is skipped, not fatal."""
    html = """<html><body><table class="tableType-player"><tbody>
        <tr><td class="rank">1</td><td><a class="playerName" href="#"></a><em>WR - SF</em></td></tr>
        <tr><td class="rank">2</td><td><a class="playerName" href="#">Real Player</a><em>RB - SF</em></td></tr>
    </tbody></table></body></html>"""
    rows = NflRankingsFetcher._parse_rankings(html, "standard")

    assert len(rows) == 1
    assert rows[0].name == "Real Player"
    assert rows[0].rank == 2


def test_parse_rankings_handles_position_without_team():
    """An <em> with only a position (no ' - TEAM') yields position, empty team."""
    html = """<html><body><table class="tableType-player"><tbody>
        <tr><td class="rank">1</td><td><a class="playerName" href="#">Solo Pos</a><em>QB</em></td></tr>
    </tbody></table></body></html>"""
    rows = NflRankingsFetcher._parse_rankings(html, "standard")

    assert len(rows) == 1
    assert rows[0].position == "QB"
    assert rows[0].team == ""
