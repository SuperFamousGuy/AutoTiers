"""CBS Sports projections scraper.

RETIRED (issue #404): CBS's projection page is client-side rendered, so the
static fetch+parse below found no populated rows and returned 0 upserted on
every run. A chronically-empty source is worse than no source: it pinned the
"data updated" freshness banner (which reports the OLDEST source) and cluttered
the per-source tooltip with a permanent error.

This fetcher is therefore NOT invoked by the orchestrator (app/data/fetcher.py),
and `cbs` is listed in that module's RETIRED_SOURCES so any lingering status row
is purged on refresh. The class is preserved in place — mirroring EspnFetcher —
so once a real data-extraction path is found (an underlying XHR JSON endpoint, or
a headless render), re-enabling takes two small edits in app/data/fetcher.py:
wire this fetcher back into refresh_all, AND drop `cbs` from RETIRED_SOURCES (so
its freshly-written status row is no longer purged on every refresh).
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.matching import fuzzy_match
from app.data.sources.base import SourceResult
from app.models import Player, Projection


logger = logging.getLogger(__name__)

_POSITIONS = ("QB", "RB", "WR", "TE")
_SCORING_FORMATS = {
    "standard": "STD",
    "half_ppr": "HALF",
    "ppr": "PPR",
}


class CBSFetcher:
    name: ClassVar[str] = "cbs"
    base_url: ClassVar[str] = "https://www.cbssports.com"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        today = date.today()
        upserted = 0

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
            ) as client:
                for position in _POSITIONS:
                    for scoring_format, scoring_param in _SCORING_FORMATS.items():
                        try:
                            resp = await client.get(
                                f"/fantasy/football/projections/{position}/",
                                params={"scoring": scoring_param},
                            )
                            resp.raise_for_status()
                            upserted += await self._parse_projections(
                                db, resp.text, position, scoring_format, today,
                            )
                        except Exception as e:
                            logger.warning("[cbs] failed to fetch %s %s: %s", position, scoring_format, e)
                            continue
        except Exception as e:
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False, error=str(e),
            )

        await db.commit()

        if upserted == 0:
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False,
                error="No projections extracted from CBS (page may be client-side rendered; needs investigation)",
            )

        return SourceResult(
            source=self.name, rows_upserted=upserted,
            last_attempted=attempted, success=True, error=None,
        )

    async def _parse_projections(
        self, db: AsyncSession, html: str, position: str, scoring_format: str, today: date,
    ) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_="TableBase") or soup.find("table")
        if table is None:
            logger.warning("[cbs] no projection table found for %s %s", position, scoring_format)
            return 0

        fpts_idx: int | None = None
        thead = table.find("thead")
        if thead is not None:
            for i, th in enumerate(thead.find_all("th")):
                text = th.get_text(strip=True).upper()
                if text in ("FPTS", "FANTASY POINTS", "PROJ", "PROJ FPTS"):
                    fpts_idx = i
                    break

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if not cells:
                continue

            name_cell = cells[0]
            name = name_cell.get_text(strip=True)
            small = name_cell.find("small")
            team = small.get_text(strip=True) if small else ""

            if not name:
                continue

            try:
                if fpts_idx is not None and fpts_idx < len(cells):
                    points_cell = cells[fpts_idx]
                else:
                    points_cell = cells[-1]
                points = float(points_cell.get_text(strip=True).replace(",", ""))
            except (ValueError, IndexError):
                continue

            player = await fuzzy_match(db, name, team, position)
            if player is None:
                logger.warning("[cbs] unmatched %s | %s %s", position, name, team or "?")
                continue

            existing = await db.scalar(
                select(Projection).where(
                    Projection.player_id == player.id,
                    Projection.source == "cbs",
                    Projection.scoring_format == scoring_format,
                )
            )
            if existing is None:
                db.add(Projection(
                    player_id=player.id, source="cbs",
                    scoring_format=scoring_format, projected_points=points,
                    last_updated=today,
                ))
            else:
                existing.projected_points = points
                existing.last_updated = today
            upserted += 1

        return upserted
