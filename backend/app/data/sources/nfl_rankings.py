"""NFL.com expert/draft rankings ingestion — currently BLOCKED (client-side rendered).

Goal (issue #431): pull NFL.com's own expert/consensus player rankings into
AutoTiers as a ranking source alongside FantasyPros, the same role
FantasyPros/ESPN rankings play today. Split from issue #91 (NFL account
linking); PR #430 shipped deliverable B — NFL league *linking* — and deferred
the "pull NFL ranking data" line to this issue, exactly as CBS rankings were
split from #90 to #422.

Blocker: the NFL.com rankings page
(https://fantasy.nfl.com/research/rankings) is client-side rendered. A static
HTML fetch returns the app shell with *zero* rankings rows, and no anonymous
JSON rankings/projections feed was found during deliverable B research — the
legacy ``api.fantasy.nfl.com/v1/players/stats`` feed returns HTTP 404 (dead,
the same failure mode as AutoTiers' already-dead cbs/spotrac scrapers). See the
``autotiers-ff-knowledge`` NFL entry ("NFL.com Fantasy Has an Anonymous-Read
League API … Rankings Unfound"). This is the same wall that blocks CBS rankings
(``app/data/sources/cbs_rankings.py``, #422).

Until a live browser DevTools network capture identifies the XHR/JSON endpoint
that populates the rankings table (DevTools → Network → Fetch/XHR while loading
``fantasy.nfl.com/research/rankings`` live — a same-origin XHR a static fetch
cannot surface), this source is not buildable as a live scraper. This module is
therefore a **probe/scaffold**, mirroring ``cbs_rankings.py`` and the
kept-but-not-invoked ``espn.py``:

  * ``fetch`` attempts the static fetch and runs the parser. Today that yields
    0 rows, so it returns ``success=False`` with a precise, actionable error
    naming the blocker — it never silently returns 0 (which would mask the
    cause) and never raises.
  * ``_parse_rankings`` encodes the best-known table contract so that, once the
    endpoint or a server-rendered page is found, re-enabling this source is a
    small, well-tested change rather than a from-scratch build. The contract is
    modeled on NFL.com's fantasy player-table markup (``<a class="playerName">``
    with an ``<em>`` carrying ``"POS - TEAM"``).

Like ``cbs_rankings.py``, it is intentionally **not** wired into
``DataFetcher.refresh_all``: a permanently-blocked source would drag the
freshness banner (which surfaces the *oldest* source — see #404) and pollute
``DataSourceStatus``. Wiring + a rankings persistence model are deferred
follow-ups shared with #422.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup

from app.data.sources.base import SourceResult


logger = logging.getLogger(__name__)

# NFL.com's research rankings page is driven by query parameters rather than a
# distinct path per scoring format. ``ppr`` selects the scoring weighting; the
# exact parameter is provisional (the page is client-side rendered, so it could
# not be confirmed against a server-rendered table this session) and should be
# finalised once the live XHR capture lands. Kept as a dict so each format gets
# its own request, mirroring CBS's per-format fetch loop.
_SCORING_PARAMS = {
    "standard": {"ppr": "0"},
    "ppr": {"ppr": "1"},
    "half_ppr": {"ppr": "0.5"},
}

# A short, unambiguous explanation returned to the status layer / surfaced in
# logs when the page is the client-side-rendered shell. Kept stable so tests and
# the freshness UI can match on it.
_BLOCKED_ERROR = (
    "NFL.com rankings page is client-side rendered: no static rankings rows "
    "found (the shell exposes no inline JSON or rankings markup), and the "
    "legacy api.fantasy.nfl.com/v1 feed is dead (HTTP 404). A live browser "
    "DevTools network capture is needed to locate the XHR/JSON endpoint that "
    "populates the table — see issue #431. Source not yet buildable."
)

# Distinct from ``_BLOCKED_ERROR``: used when *no* scoring-format page could be
# fetched at all (network/server failure), so the empty result must not be
# misattributed to client-side rendering. Kept as a stable prefix so tests and
# the freshness UI can match on it.
_FETCH_FAILED_PREFIX = (
    "NFL.com rankings fetch failed: no scoring-format page could be retrieved"
)


@dataclass(frozen=True)
class RankingRow:
    """One expert-ranking entry. ``rank`` is the overall ranking (1 = best)."""

    rank: int
    name: str
    team: str
    position: str
    scoring_format: str


class NflRankingsFetcher:
    """Probe/scaffold fetcher for NFL.com expert rankings. See module docstring."""

    name: ClassVar[str] = "nfl_rankings"
    base_url: ClassVar[str] = "https://fantasy.nfl.com"

    async def fetch(self, db=None) -> SourceResult:
        # ``db`` is accepted to satisfy the SourceFetcher protocol but unused:
        # there is no rankings persistence model yet (deferred follow-up shared
        # with #422), and the static fetch yields nothing to persist regardless.
        attempted = datetime.utcnow()
        rows: list[RankingRow] = []
        # Track requests that completed with a 2xx (counted only after
        # ``raise_for_status()``) and capture per-format failures, so an empty
        # result can be correctly attributed to a blocked shell (fetched OK,
        # parsed 0 rows) vs. a network/server failure (nothing fetched).
        successful_fetches = 0
        fetch_errors: list[str] = []

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
            ) as client:
                for scoring_format, params in _SCORING_PARAMS.items():
                    try:
                        resp = await client.get("/research/rankings", params=params)
                        resp.raise_for_status()
                        successful_fetches += 1
                        rows.extend(
                            self._parse_rankings(resp.text, scoring_format)
                        )
                    except Exception as e:  # noqa: BLE001 — isolate per-format failures
                        logger.warning(
                            "[nfl_rankings] failed to fetch %s rankings: %s",
                            scoring_format, e,
                        )
                        fetch_errors.append(f"{scoring_format}: {e}")
                        continue
        except Exception as e:  # noqa: BLE001 — client construction / unexpected
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False, error=str(e),
            )

        if not rows:
            if successful_fetches == 0:
                # Nothing was fetched successfully: a network/server failure,
                # NOT the client-side-rendered shell. Report it as such with the
                # per-format errors so callers can act on the real cause.
                error = (
                    f"{_FETCH_FAILED_PREFIX} "
                    f"({'; '.join(fetch_errors) or 'no requests attempted'}). "
                    "See issue #431."
                )
                logger.warning("[nfl_rankings] %s", error)
                return SourceResult(
                    source=self.name, rows_upserted=0,
                    last_attempted=attempted, success=False, error=error,
                )
            # Pages fetched OK but parsed 0 rows: a client-side-rendered shell.
            logger.warning("[nfl_rankings] %s", _BLOCKED_ERROR)
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False, error=_BLOCKED_ERROR,
            )

        # Re-enable path: NFL.com is now serving extractable rankings markup. We
        # do not yet have a rankings persistence model, so flag this loudly
        # rather than silently discard the data. ``rows_upserted`` reports the
        # count of rows *extracted* (not persisted) until the model lands.
        logger.warning(
            "[nfl_rankings] extracted %d rankings rows from static markup, but "
            "no rankings persistence model exists yet — wire one up (issue #431).",
            len(rows),
        )
        return SourceResult(
            source=self.name, rows_upserted=len(rows),
            last_attempted=attempted, success=True, error=None,
        )

    @staticmethod
    def _parse_rankings(html: str, scoring_format: str) -> list[RankingRow]:
        """Extract ranking rows from an NFL.com rankings page.

        Provisional contract — modeled on NFL.com's fantasy player-table markup,
        to be finalised once the live endpoint markup is captured. NFL.com rows
        carry the player in an ``<a class="playerName">`` anchor and the position
        + team together in a sibling ``<em>`` as ``"WR - CIN"``; rank is an
        explicit numeric cell (commonly ``<td class="rank">``), falling back to
        row order. Rows missing a name are skipped, never fatal.

        Only the known NFL.com player-table selectors are matched. A bare
        ``soup.find("table")`` fallback was deliberately dropped: on the
        client-side-rendered shell (or other marketing pages) it can latch onto
        an unrelated ``<table>`` and emit bogus "rankings" rows, which would make
        ``fetch()`` report ``success=True`` incorrectly (the same trap called out
        in ``cbs_rankings.py``).
        """
        soup = BeautifulSoup(html, "lxml")
        # NFL.com fantasy tables carry a ``tableType-player`` class; some
        # variants id the rankings table ``#rankings``. Match either, but never
        # a bare ``<table>``.
        table = (
            soup.find("table", class_="tableType-player")
            or soup.find("table", id="rankings")
        )
        if table is None:
            return []

        rows: list[RankingRow] = []
        for idx, tr in enumerate(table.select("tbody tr"), start=1):
            cells = tr.find_all("td")
            if not cells:
                continue

            # Player name: the dedicated ``.playerName`` anchor when present,
            # else the first cell that contains an <a>.
            anchor = tr.find("a", class_="playerName") or tr.find("a")
            name = anchor.get_text(strip=True) if anchor else ""
            if not name:
                continue

            # Position + team live together in an <em> as "POS - TEAM"
            # (e.g. "WR - CIN"). DST rows can read "DEF - CIN". Parse defensively.
            position = ""
            team = ""
            em = tr.find("em")
            if em:
                meta = em.get_text(strip=True)
                if " - " in meta:
                    pos_part, _, team_part = meta.partition(" - ")
                    position = pos_part.strip().upper()
                    team = team_part.strip().upper()
                else:
                    position = meta.strip().upper()

            # Rank: prefer an explicit ``.rank`` cell, then any numeric cell,
            # then fall back to row order.
            rank = idx
            rank_cell = tr.find("td", class_="rank")
            rank_text = rank_cell.get_text(strip=True) if rank_cell else ""
            if rank_text.isdigit():
                rank = int(rank_text)
            else:
                for c in cells:
                    text = c.get_text(strip=True)
                    if text.isdigit():
                        rank = int(text)
                        break

            rows.append(RankingRow(
                rank=rank, name=name, team=team,
                position=position, scoring_format=scoring_format,
            ))

        return rows
