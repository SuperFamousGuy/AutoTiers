"""Sleeper API fetcher — the master player list."""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player


_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST", "DEF"}
_POSITION_NORMALIZE = {"DEF": "DST"}


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
            if position not in _FANTASY_POSITIONS:
                continue
            # Gate on Sleeper's own ``active`` flag, NOT on ``team`` (#791).
            # A just-released *free agent* is still ``active=True`` but has
            # ``team=None``; treating team-null as deletion-worthy hard-deleted
            # him (and cascaded away his PlayerStat/Projection/ADPData history)
            # the instant he showed up unrostered, even though every public ADP
            # board still ranks him as a discounted-but-draftable option. Only
            # genuinely retired/inactive players carry ``active=False`` — those
            # we still skip (and thus prune) as before.
            if not raw.get("active", True):
                continue

            team = raw.get("team")  # None for free agents — persisted as-is.
            seen_ids.add(sleeper_id)
            existing = existing_by_id.get(sleeper_id)
            if existing is None:
                existing = Player(id=sleeper_id)
                db.add(existing)

            existing.name = raw.get("full_name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip()
            existing.position = _POSITION_NORMALIZE.get(position, position)
            existing.team = team
            existing.age = raw.get("age")
            existing.years_exp = raw.get("years_exp")
            # Only overwrite cross-IDs when Sleeper explicitly produced a value this
            # run. Sleeper transiently omits gsis_id/espn_id even for players it has
            # populated on prior pulls; an unconditional assignment would wipe a
            # previously-correct id to None and silently drop the player from every
            # downstream nfl_data_py join (which keys on Player.gsis_id.is_not(None)).
            # Mirrors the "only overwrite when the source produced a value" pattern in
            # nfl_data.py. See issue #837.
            if raw.get("gsis_id") is not None:
                existing.gsis_id = raw["gsis_id"]
            if raw.get("espn_id") is not None:
                existing.espn_id = str(raw["espn_id"])
            existing.active = True
            upserted += 1

        # Hard-delete players Sleeper has dropped from its player list *entirely*
        # (id absent from the response), plus any it now marks inactive. A player
        # who is merely unrostered (team=None but still active) stays in
        # ``seen_ids`` above and is preserved — see #791.
        # Cascade FKs on Player.stats/projections/adp_entries clean up dependent
        # rows for the players we do delete.
        for pid, p in existing_by_id.items():
            if pid not in seen_ids:
                await db.delete(p)

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
