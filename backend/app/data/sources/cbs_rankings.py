"""CBS Sports expert rankings ingestion — currently BLOCKED (client-side rendered).

Goal (issue #422): pull CBS Sports' own expert player rankings into AutoTiers
as a ranking source alongside FantasyPros.

Blocker: the CBS rankings pages (e.g.
https://www.cbssports.com/fantasy/football/rankings/standard/top200/consensus/)
are client-side rendered. A static HTML fetch returns the Next.js marketing
shell with *zero* rankings rows: the ``.rankings-table`` selector appears only
inside an analytics tracking config, there is no ``__NEXT_DATA__`` / inline JSON
payload, and no same-origin rankings API host is referenced in the static
markup. This was confirmed empirically (a live fetch returns ~1.2 MB of shell
HTML with only a handful of stray player anchors). It is the same wall that
killed the dead CBS *projections* scraper (``app/data/sources/cbs.py``, #404).

Until a live browser DevTools network capture identifies the XHR/JSON endpoint
that populates the rankings table, this source is not buildable as a live
scraper. This module is therefore a **probe/scaffold**, mirroring the existing
``cbs.py`` projections scaffold and the kept-but-not-invoked ``espn.py``:

  * ``fetch`` attempts the static fetch and runs the parser. Today that yields
    0 rows, so it returns ``success=False`` with a precise, actionable error
    naming the blocker — it never silently returns 0 (which would mask the
    cause) and never raises.
  * ``_parse_rankings`` encodes the best-known table contract so that, once the
    endpoint or a server-rendered page is found, re-enabling this source is a
    small, well-tested change rather than a from-scratch build.

It is intentionally **not** wired into ``DataFetcher.refresh_all``: a
permanently-blocked source would drag the freshness banner (which surfaces the
*oldest* source — see #404) and pollute ``DataSourceStatus``. Wiring + a
rankings persistence model are deferred follow-ups.
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

# CBS publishes a separate ranking page per scoring format. Slugs map our
# internal format names to the path segment CBS uses.
_SCORING_SLUGS = {
    "standard": "standard",
    "ppr": "ppr",
    "half_ppr": "half-ppr",
}

# A short, unambiguous explanation returned to the status layer / surfaced in
# logs when the page is the client-side-rendered shell. Kept stable so tests and
# the freshness UI can match on it.
_BLOCKED_ERROR = (
    "CBS rankings page is client-side rendered: no static rankings rows found "
    "(the shell exposes no inline JSON or rankings markup). A live browser "
    "DevTools network capture is needed to locate the XHR/JSON endpoint that "
    "populates the table — see issue #422. Source not yet buildable."
)


@dataclass(frozen=True)
class RankingRow:
    """One expert-ranking entry. ``rank`` is the overall ranking (1 = best)."""

    rank: int
    name: str
    team: str
    position: str
    scoring_format: str


class CBSRankingsFetcher:
    """Probe/scaffold fetcher for CBS expert rankings. See module docstring."""

    name: ClassVar[str] = "cbs_rankings"
    base_url: ClassVar[str] = "https://www.cbssports.com"

    async def fetch(self, db=None) -> SourceResult:
        # ``db`` is accepted to satisfy the SourceFetcher protocol but unused:
        # there is no rankings persistence model yet (deferred follow-up), and
        # the static fetch yields nothing to persist regardless.
        attempted = datetime.utcnow()
        rows: list[RankingRow] = []

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
            ) as client:
                for scoring_format, slug in _SCORING_SLUGS.items():
                    try:
                        resp = await client.get(
                            f"/fantasy/football/rankings/{slug}/top200/consensus/"
                        )
                        resp.raise_for_status()
                        rows.extend(
                            self._parse_rankings(resp.text, scoring_format)
                        )
                    except Exception as e:  # noqa: BLE001 — isolate per-format failures
                        logger.warning(
                            "[cbs_rankings] failed to fetch %s rankings: %s",
                            scoring_format, e,
                        )
                        continue
        except Exception as e:  # noqa: BLE001 — client construction / unexpected
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False, error=str(e),
            )

        if not rows:
            # The expected state today: a client-side-rendered shell.
            logger.warning("[cbs_rankings] %s", _BLOCKED_ERROR)
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False, error=_BLOCKED_ERROR,
            )

        # Re-enable path: CBS is now serving extractable rankings markup. We do
        # not yet have a rankings persistence model, so flag this loudly rather
        # than silently discard the data. ``rows_upserted`` reports the count of
        # rows *extracted* (not persisted) until the model lands.
        logger.warning(
            "[cbs_rankings] extracted %d rankings rows from static markup, but "
            "no rankings persistence model exists yet — wire one up (issue #422).",
            len(rows),
        )
        return SourceResult(
            source=self.name, rows_upserted=len(rows),
            last_attempted=attempted, success=True, error=None,
        )

    @staticmethod
    def _parse_rankings(html: str, scoring_format: str) -> list[RankingRow]:
        """Extract ranking rows from a CBS rankings page.

        Provisional contract — confirmed against the analytics-config selector
        (``.rankings-table``) present in the live shell, to be finalised once the
        endpoint markup is captured. Each ``<tbody>`` row is expected to expose a
        rank cell, a player-name anchor with the team in a ``<small>``, and a
        position cell. Rows missing a name or a parseable rank are skipped, never
        fatal.
        """
        soup = BeautifulSoup(html, "lxml")
        table = (
            soup.find("table", class_="rankings-table")
            or soup.find("table", class_="TableBase")
            or soup.find("table")
        )
        if table is None:
            return []

        rows: list[RankingRow] = []
        for idx, tr in enumerate(table.select("tbody tr"), start=1):
            cells = tr.find_all("td")
            if not cells:
                continue

            # Locate the player cell: the first cell containing an <a>.
            name_cell = next((c for c in cells if c.find("a")), cells[0])
            anchor = name_cell.find("a")
            name = (anchor or name_cell).get_text(strip=True)
            if not name:
                continue

            small = name_cell.find("small")
            team = small.get_text(strip=True) if small else ""

            # Rank: prefer an explicit numeric cell distinct from the name cell;
            # fall back to row order.
            rank = idx
            for c in cells:
                if c is name_cell:
                    continue
                text = c.get_text(strip=True)
                if text.isdigit():
                    rank = int(text)
                    break

            # Position: a cell whose text looks like a position code.
            position = ""
            for c in cells:
                text = c.get_text(strip=True).upper()
                if text in ("QB", "RB", "WR", "TE", "K", "DST"):
                    position = text
                    break

            rows.append(RankingRow(
                rank=rank, name=name, team=team,
                position=position, scoring_format=scoring_format,
            ))

        return rows
