"""FantasyPros scraper — consensus projections + ADP. Resolves players via fuzzy match."""
from __future__ import annotations

import logging
import re
from datetime import datetime, date
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.matching import fuzzy_match
from app.data.sources.base import SourceResult
from app.models import Player, Projection, ADPData


logger = logging.getLogger(__name__)

_POSITIONS = ("qb", "rb", "wr", "te")
_ADP_FORMATS = {"standard": "overall", "half_ppr": "half-point-ppr", "ppr": "ppr"}


class FantasyProsFetcher:
    name: ClassVar[str] = "fantasypros"
    base_url: ClassVar[str] = "https://www.fantasypros.com"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        today = date.today()
        upserted = 0

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0,
                                          headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"}) as client:
                # Projections: position × scoring_format
                for position in _POSITIONS:
                    for ff_format, ff_param in [("standard", "STD"), ("half_ppr", "HALF"), ("ppr", "PPR")]:
                        resp = await client.get(f"/nfl/projections/{position}.php", params={"scoring": ff_param})
                        resp.raise_for_status()
                        upserted += await self._parse_projections(
                            db, resp.text, position.upper(), ff_format, today
                        )

                # ADP per format
                for adp_format, slug in _ADP_FORMATS.items():
                    resp = await client.get(f"/nfl/adp/{slug}.php")
                    resp.raise_for_status()
                    upserted += await self._parse_adp(db, resp.text, adp_format, today)
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)

    async def _parse_projections(
        self, db: AsyncSession, html: str, position: str, scoring_format: str, today: date,
    ) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="data")
        if table is None:
            return 0

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            name, team = self._parse_player_cell(cells[0])
            if not name:
                continue
            # Last cell is FPTS.
            try:
                points = float(cells[-1].get_text(strip=True).replace(",", ""))
            except (ValueError, IndexError):
                continue

            player = await fuzzy_match(db, name, team, position)
            if player is None:
                logger.warning("[fantasypros] unmatched %s | %s %s", position, name, team or "?")
                continue

            existing = await db.scalar(
                select(Projection).where(
                    Projection.player_id == player.id,
                    Projection.source == "fantasypros",
                    Projection.scoring_format == scoring_format,
                )
            )
            if existing is None:
                db.add(Projection(player_id=player.id, source="fantasypros",
                                  scoring_format=scoring_format, projected_points=points,
                                  last_updated=today))
            else:
                existing.projected_points = points
                existing.last_updated = today
            upserted += 1
        return upserted

    async def _parse_adp(self, db: AsyncSession, html: str, fmt: str, today: date) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="data")
        if table is None:
            return 0

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            name, team = self._parse_player_cell(cells[1])
            pos_text = cells[2].get_text(strip=True)
            # Strip trailing tier digits, e.g. "WR1" → "WR"
            position = re.sub(r"\d+$", "", pos_text)
            try:
                adp_val = float(cells[3].get_text(strip=True))
            except ValueError:
                continue
            if not name:
                continue

            player = await fuzzy_match(db, name, team, position)
            if player is None:
                logger.warning("[fantasypros adp] unmatched %s %s | %s", fmt, name, team or "?")
                continue

            existing = await db.scalar(
                select(ADPData).where(
                    ADPData.player_id == player.id,
                    ADPData.format == fmt,
                    ADPData.adp_source == "fantasypros",
                )
            )
            if existing is None:
                db.add(ADPData(player_id=player.id, format=fmt, adp=adp_val,
                               adp_source="fantasypros", last_updated=today))
            else:
                existing.adp = adp_val
                existing.last_updated = today
            upserted += 1
        return upserted

    @staticmethod
    def _parse_player_cell(cell) -> tuple[str, str]:
        """Pull (name, team) from a FantasyPros player cell. Name is the <a> text, team is the <small>."""
        a = cell.find("a")
        small = cell.find("small")
        name = a.get_text(strip=True) if a else cell.get_text(strip=True)
        team = small.get_text(strip=True) if small else ""
        return name, team
