"""ESPN unofficial fantasy API fetcher — current-season projections.

NOTE (deprecated for v1): this fetcher is currently NOT invoked by the
orchestrator (app/data/fetcher.py). ESPN's public endpoint redirects
anonymous requests; using it requires S2/SWID cookie auth (env vars).
Source preserved in place so re-enabling is a one-line orchestrator change
once cookie auth is wired up.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player, Projection


# The leaguedefaults/3 endpoint returns PPR-calibrated projections (segment 0 = full-season
# aggregate at PPR scoring). Writing this value to standard/half_ppr formats would overstate
# projected points for non-PPR leagues — it is not a format-neutral number.
#
# To fully support all scoring formats, fetch segment 1 (standard) and segment 2 (half-PPR)
# separately and write each to the appropriate format row. That is deferred until this
# fetcher is re-enabled in the orchestrator (see NOTE at top of file).
#
# For now: only write to "ppr". Standard and half-ppr leagues will get espn_pts=None
# from _get_projection(), which is honest — no ESPN data for those formats — rather than
# silently writing a PPR-inflated number.
_ESPN_FORMATS = ("ppr",)


class EspnFetcher:
    name: ClassVar[str] = "espn"
    base_url: ClassVar[str] = "https://lm-api-reads.fantasy.espn.com"

    def __init__(self, season: int):
        self.season = season

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        url = f"/apis/v3/games/ffl/seasons/{self.season}/segments/0/leaguedefaults/3"
        params = {"view": "kona_player_info"}
        headers = {"x-fantasy-filter": '{"players":{"limit":1500,"sortPercOwned":{"sortAsc":false,"sortPriority":1}}}'}

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
            ) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        players_in = payload.get("players") or []

        # Build espn_id → Player map.
        all_players = (await db.scalars(select(Player).where(Player.espn_id.is_not(None)))).all()
        espn_to_pid = {p.espn_id: p.id for p in all_players}

        # Index existing ESPN projections.
        existing = (await db.scalars(
            select(Projection).where(Projection.source == "espn")
        )).all()
        existing_key = {(p.player_id, p.scoring_format): p for p in existing}

        today = date.today()
        upserted = 0
        for entry in players_in:
            espn_id = str(entry.get("id"))
            pid = espn_to_pid.get(espn_id)
            if pid is None:
                continue

            stats = entry.get("player", {}).get("stats") or []
            projection_pts = None
            for s in stats:
                if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0 and s.get("seasonId") == self.season:
                    projection_pts = float(s.get("appliedTotal") or 0)
                    break
            if projection_pts is None:
                continue

            for fmt in _ESPN_FORMATS:
                row = existing_key.get((pid, fmt))
                if row is None:
                    row = Projection(player_id=pid, source="espn", scoring_format=fmt,
                                     projected_points=projection_pts, last_updated=today)
                    db.add(row)
                    existing_key[(pid, fmt)] = row
                else:
                    row.projected_points = projection_pts
                    row.last_updated = today
                upserted += 1

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
