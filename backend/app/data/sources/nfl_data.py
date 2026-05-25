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

    def __init__(self, prior_seasons: int = 3, latest_season: int | None = None):
        self.latest_season = latest_season or (datetime.utcnow().year - 1)
        self.seasons_to_load = [self.latest_season - i for i in range(prior_seasons)]
        # Back-compat alias for callers that still read `.season`:
        self.season = self.latest_season

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        season_to_use = self.season
        seasonal_df = snap_df = pbp_df = None
        last_err: Exception | None = None
        for candidate in (self.season, self.season - 1):
            try:
                seasonal_df = import_seasonal_data([candidate])
                snap_df = import_snap_counts([candidate])
                pbp_df = import_pbp_data([candidate])
                season_to_use = candidate
                last_err = None
                break
            except Exception as e:
                last_err = e
                continue

        if last_err is not None or seasonal_df is None:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted,
                                success=False,
                                error=f"could not fetch any season (tried {self.season}, {self.season - 1}): {last_err}")

        # Build gsis_id → Player.id map.
        players = (await db.scalars(select(Player).where(Player.gsis_id.is_not(None)))).all()
        gsis_to_pid = {p.gsis_id: p.id for p in players}

        # Build gsis_id → snap_pct map from snap_df.
        snap_by_gsis: dict[str, float] = {}
        if not snap_df.empty:
            try:
                # snap_df has multiple rows per player (one per game). Aggregate to season pct.
                aggregated = snap_df.groupby("gsis_id")["offense_pct"].mean()
                snap_by_gsis = aggregated.to_dict()
            except KeyError as e:
                # Real nfl_data_py snap_counts uses pfr_player_id, not gsis_id.
                # Joining via pfr_player_id → gsis_id requires import_ids() — deferred.
                # For now: skip snap_pct rather than fail the entire fetcher.
                import logging
                logging.getLogger(__name__).warning(
                    "[nfl_data] snap_counts schema mismatch (missing %s); skipping snap_pct", e
                )

        # PBP-derived: red_zone_looks and expected_tds per gsis_id.
        rz_looks: dict[str, int] = {}
        xtds: dict[str, float] = {}
        if not pbp_df.empty:
            # Filter to actual offensive plays — exclude no_plays (penalties) and other non-scrimmage rows.
            valid_plays = pbp_df[pbp_df["play_type"].isin(["run", "pass"])]
            rz = valid_plays[valid_plays["yardline_100"] <= 20]
            for _, play in rz.iterrows():
                td_prob = float(play.get("td_prob") or 0)
                rusher = play.get("rusher_player_id")
                receiver = play.get("receiver_player_id")
                if isinstance(rusher, str) and rusher:
                    rz_looks[rusher] = rz_looks.get(rusher, 0) + 1
                    xtds[rusher] = xtds.get(rusher, 0.0) + td_prob
                if isinstance(receiver, str) and receiver:
                    rz_looks[receiver] = rz_looks.get(receiver, 0) + 1
                    xtds[receiver] = xtds.get(receiver, 0.0) + td_prob

        # Index existing stats by (player_id, season) to allow upsert.
        existing_stats = (await db.scalars(
            select(PlayerStat).where(PlayerStat.season == season_to_use)
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
                stat = PlayerStat(player_id=pid, season=season_to_use)
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
            if gsis in rz_looks:
                stat.red_zone_looks = rz_looks[gsis]
            if gsis in xtds:
                stat.expected_tds = round(xtds[gsis], 3)

            upserted += 1

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
