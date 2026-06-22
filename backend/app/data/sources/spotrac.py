"""Spotrac scraper — per-position cap-hit tables. Resolves players via fuzzy match."""
from __future__ import annotations

import logging
import re
from datetime import datetime, date
from typing import ClassVar, Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.matching import fuzzy_match
from app.data.sources.base import SourceResult
from app.models import PlayerContract


logger = logging.getLogger(__name__)

_POSITIONS = ("QB", "RB", "WR", "TE")
_CAP_HIT_CLEAN = re.compile(r"[\$,]")


def _parse_cap_hit(text: str) -> Optional[float]:
    cleaned = _CAP_HIT_CLEAN.sub("", text or "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


class SpotracFetcher:
    name: ClassVar[str] = "spotrac"
    base_url: ClassVar[str] = "https://www.spotrac.com"

    def __init__(self, season: Optional[int] = None):
        self.season = season or datetime.utcnow().year

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        today = date.today()
        upserted = 0
        last_err: Optional[Exception] = None
        any_success = False

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=20.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
        ) as client:
            for position in _POSITIONS:
                url = f"/nfl/positional/{position}/cap_hit/"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                except Exception as e:
                    last_err = e
                    logger.warning("[spotrac] failed to fetch %s: %s", position, e)
                    continue
                any_success = True
                upserted += await self._parse_and_upsert(
                    db, resp.text, position, today,
                )

        if not any_success and last_err is not None:
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False,
                error=f"all positions failed: {last_err}",
            )

        await db.commit()

        if upserted == 0:
            return SourceResult(
                source=self.name, rows_upserted=0,
                last_attempted=attempted, success=False,
                error="No contracts extracted from Spotrac (source layout may have changed; needs investigation)",
            )

        return SourceResult(
            source=self.name, rows_upserted=upserted,
            last_attempted=attempted, success=True, error=None,
        )

    async def _parse_and_upsert(
        self, db: AsyncSession, html: str, position: str, today: date,
    ) -> int:
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tbody tr")
        upserted = 0

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            name = cells[0].get_text(strip=True)
            cap_hit = _parse_cap_hit(cells[1].get_text(strip=True))
            if not name or cap_hit is None:
                continue

            player = await fuzzy_match(db, name, "", position)
            if player is None:
                logger.warning("[spotrac] unmatched %s | %s", position, name)
                continue

            existing = await db.scalar(
                select(PlayerContract).where(
                    PlayerContract.player_id == player.id,
                    PlayerContract.season == self.season,
                )
            )
            if existing is None:
                db.add(PlayerContract(
                    player_id=player.id, season=self.season,
                    cap_hit=cap_hit, last_updated=today,
                ))
            else:
                existing.cap_hit = cap_hit
                existing.last_updated = today
            upserted += 1
        return upserted
