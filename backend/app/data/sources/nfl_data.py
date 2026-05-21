"""nfl_data_py fetcher — seasonal stats, snap counts, and PBP-derived fields."""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from nfl_data_py import import_seasonal_data, import_snap_counts, import_pbp_data
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player, PlayerStat


class NflDataFetcher:
    name: ClassVar[str] = "nfl_data_py"

    def __init__(self, season: int):
        self.season = season

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        try:
            seasonal_df = import_seasonal_data([self.season])
            snap_df = import_snap_counts([self.season])
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        # Build gsis_id → Player.id map.
        players = (await db.scalars(select(Player).where(Player.gsis_id.is_not(None)))).all()
        gsis_to_pid = {p.gsis_id: p.id for p in players}

        # Build gsis_id → snap_pct map from snap_df.
        snap_by_gsis: dict[str, float] = {}
        if not snap_df.empty:
            # snap_df has multiple rows per player (one per game). Aggregate to season pct.
            aggregated = snap_df.groupby("gsis_id")["offense_pct"].mean()
            snap_by_gsis = aggregated.to_dict()

        # Index existing stats by (player_id, season) to allow upsert.
        existing_stats = (await db.scalars(
            select(PlayerStat).where(PlayerStat.season == self.season)
        )).all()
        stats_by_pid = {s.player_id: s for s in existing_stats}

        upserted = 0
        for _, row in seasonal_df.iterrows():
            gsis = row.get("player_id")
            pid = gsis_to_pid.get(gsis)
            if pid is None:
                continue

            stat = stats_by_pid.get(pid)
            if stat is None:
                stat = PlayerStat(player_id=pid, season=self.season)
                db.add(stat)
                stats_by_pid[pid] = stat

            stat.targets = int(row.get("targets") or 0)
            stat.receptions = int(row.get("receptions") or 0)
            stat.rec_yards = float(row.get("receiving_yards") or 0)
            stat.rec_tds = int(row.get("receiving_tds") or 0)
            stat.rush_att = int(row.get("carries") or 0)
            stat.rush_yards = float(row.get("rushing_yards") or 0)
            stat.rush_tds = int(row.get("rushing_tds") or 0)
            stat.pass_att = int(row.get("attempts") or 0)
            stat.pass_yards = float(row.get("passing_yards") or 0)
            stat.pass_tds = int(row.get("passing_tds") or 0)
            stat.interceptions = int(row.get("interceptions") or 0)
            stat.games_played = int(row.get("games") or 0)
            stat.actual_tds = stat.rec_tds + stat.rush_tds + stat.pass_tds

            if gsis in snap_by_gsis:
                stat.snap_pct = float(snap_by_gsis[gsis])

            upserted += 1

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
