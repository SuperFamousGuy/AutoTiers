"""Sleeper API fetcher — the master player list."""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player


_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}


class SleeperFetcher:
    name: ClassVar[str] = "sleeper"
    base_url: ClassVar[str] = "https://api.sleeper.app"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
            ) as client:
                resp = await client.get("/v1/players/nfl")
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        existing_rows = (await db.scalars(select(Player))).all()
        existing_by_id = {p.id: p for p in existing_rows}
        seen_ids: set[str] = set()

        upserted = 0
        for sleeper_id, raw in payload.items():
            position = raw.get("position")
            team = raw.get("team")
            if position not in _FANTASY_POSITIONS or team is None:
                continue

            seen_ids.add(sleeper_id)
            existing = existing_by_id.get(sleeper_id)
            if existing is None:
                existing = Player(id=sleeper_id)
                db.add(existing)

            existing.name = raw.get("full_name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip()
            existing.position = position
            existing.team = team
            existing.age = raw.get("age")
            existing.years_exp = raw.get("years_exp")
            existing.gsis_id = raw.get("gsis_id")
            existing.espn_id = str(raw["espn_id"]) if raw.get("espn_id") is not None else None
            existing.active = True
            upserted += 1

        for pid, p in existing_by_id.items():
            if pid not in seen_ids:
                p.active = False

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
