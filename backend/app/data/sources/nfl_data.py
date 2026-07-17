"""nfl_data_py fetcher — seasonal stats, snap counts, and PBP-derived fields."""
from __future__ import annotations

from datetime import datetime, date
from typing import ClassVar

import pandas as pd
from nfl_data_py import (
    import_seasonal_data,
    import_snap_counts,
    import_pbp_data,
    import_schedules,
    import_draft_picks,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player, PlayerStat, TeamSeason


def _safe_float(value, default: float = 0.0) -> float:
    """Coerce a possibly-None/NaN pandas scalar to a finite float.

    Real nflfastR data carries NaN in fields like ``td_prob`` (garbage-time
    and unconverged win-probability rows). ``float(x or 0)`` does NOT guard
    against this: ``NaN`` is truthy, so ``NaN or 0`` evaluates to ``NaN`` and
    silently poisons any season aggregate the value feeds. Guard explicitly.
    """
    if value is None or pd.isna(value):
        return default
    return float(value)


def _safe_int_or_none(value):
    """Coerce a possibly-None/NaN pandas scalar to ``int`` or ``None``.

    Draft-pick rows carry NaN for undrafted players and for rows missing a
    round/pick, and ``int(NaN)`` raises. Return ``None`` for any absent value so
    the downstream rule (which treats None as a non-match) behaves correctly.
    """
    if value is None or pd.isna(value):
        return None
    return int(value)


class NflDataFetcher:
    name: ClassVar[str] = "nfl_data_py"

    def __init__(self, prior_seasons: int = 3, latest_season: int | None = None):
        self.latest_season = latest_season or (datetime.utcnow().year - 1)
        self.seasons_to_load = [self.latest_season - i for i in range(prior_seasons)]
        # Back-compat alias for callers that still read `.season`:
        self.season = self.latest_season

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        total_upserted = 0
        last_err: Exception | None = None

        # Build gsis_id → Player map once across all seasons.
        players = (await db.scalars(select(Player).where(Player.gsis_id.is_not(None)))).all()
        gsis_to_pid = {p.gsis_id: p.id for p in players}
        players_by_gsis = {p.gsis_id: p for p in players}

        # Draft capital is a career-constant player attribute, not a per-season
        # stat, so populate it once outside the season loop. Fetch draft classes
        # from the oldest loaded stat season through the upcoming draft
        # (latest_season + 1) so this season's rookies (years_exp==0, drafted in
        # latest_season + 1) are covered. Failures are silent — draft data is
        # supplemental and must not fail the whole fetcher (like schedules).
        draft_years = list(range(min(self.seasons_to_load), self.latest_season + 2))
        try:
            draft_df = import_draft_picks(draft_years)
        except Exception:
            draft_df = None
        if draft_df is not None and not draft_df.empty and "gsis_id" in draft_df.columns:
            for _, row in draft_df.iterrows():
                gsis = row.get("gsis_id")
                player = players_by_gsis.get(gsis) if isinstance(gsis, str) else None
                if player is None:
                    continue
                player.draft_round = _safe_int_or_none(row.get("round"))
                player.draft_pick = _safe_int_or_none(row.get("pick"))

        for season in self.seasons_to_load:
            try:
                seasonal_df = import_seasonal_data([season])
                snap_df = import_snap_counts([season])
                pbp_df = import_pbp_data([season])
            except Exception as e:
                last_err = e
                continue

            # Build gsis_id → snap_pct map from snap_df for this season.
            # ``snap_available`` is True only when the groupby actually produced a
            # season map this run. When the source failed entirely (empty df, or a
            # schema KeyError) we leave previously-persisted snap_pct untouched
            # rather than wipe it on a failed fetch.
            snap_by_gsis: dict[str, float] = {}
            snap_available = False
            if not snap_df.empty:
                try:
                    # snap_df has multiple rows per player (one per game). Aggregate to season pct.
                    aggregated = snap_df.groupby("gsis_id")["offense_pct"].mean()
                    snap_by_gsis = aggregated.to_dict()
                    snap_available = True
                except KeyError as e:
                    # Real nfl_data_py snap_counts uses pfr_player_id, not gsis_id.
                    # Joining via pfr_player_id → gsis_id requires import_ids() — deferred.
                    # For now: skip snap_pct rather than fail the entire fetcher.
                    import logging
                    logging.getLogger(__name__).warning(
                        "[nfl_data] snap_counts schema mismatch (missing %s); skipping snap_pct", e
                    )

            # PBP-derived: red_zone_looks and expected_tds per gsis_id for this season.
            rz_looks: dict[str, int] = {}
            xtds: dict[str, float] = {}
            # ``pbp_available`` distinguishes "player had zero red-zone plays this
            # run" (write 0) from "the PBP source failed for the season" (leave
            # existing values untouched — don't wipe on a failed fetch).
            pbp_available = not pbp_df.empty
            if pbp_available:
                # Filter to actual offensive plays — exclude no_plays (penalties) and other non-scrimmage rows.
                valid_plays = pbp_df[pbp_df["play_type"].isin(["run", "pass"])]
                rz = valid_plays[valid_plays["yardline_100"] <= 20]
                for _, play in rz.iterrows():
                    # NaN td_prob must contribute 0.0 (not NaN) to the season
                    # total; the play still counts as a red-zone look.
                    td_prob = _safe_float(play.get("td_prob"))
                    rusher = play.get("rusher_player_id")
                    receiver = play.get("receiver_player_id")
                    if isinstance(rusher, str) and rusher:
                        rz_looks[rusher] = rz_looks.get(rusher, 0) + 1
                        xtds[rusher] = xtds.get(rusher, 0.0) + td_prob
                    if isinstance(receiver, str) and receiver:
                        rz_looks[receiver] = rz_looks.get(receiver, 0) + 1
                        xtds[receiver] = xtds.get(receiver, 0.0) + td_prob

            # Index existing stats by player_id for this season to allow upsert.
            existing_stats = (await db.scalars(
                select(PlayerStat).where(PlayerStat.season == season)
            )).all()
            stats_by_pid = {s.player_id: s for s in existing_stats}

            for _, row in seasonal_df.iterrows():
                gsis = row.get("player_id")
                pid = gsis_to_pid.get(gsis)
                if pid is None:
                    continue

                stat = stats_by_pid.get(pid)
                if stat is None:
                    stat = PlayerStat(player_id=pid, season=season)
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
                # Turnovers / 2-pt conversions (#663). nflverse splits each across
                # play types (rushing/receiving/sack fumbles; passing/rushing/
                # receiving 2-pt); sum them into the single per-player season count
                # the scoring engine expects. Missing columns default to 0.
                stat.fumbles_lost = (
                    int(row.get("rushing_fumbles_lost") or 0)
                    + int(row.get("receiving_fumbles_lost") or 0)
                    + int(row.get("sack_fumbles_lost") or 0)
                )
                stat.two_pt_conversions = (
                    int(row.get("passing_2pt_conversions") or 0)
                    + int(row.get("rushing_2pt_conversions") or 0)
                    + int(row.get("receiving_2pt_conversions") or 0)
                )

                if snap_available:
                    # The source produced a season map this run, so write for every
                    # player row (like the basic stat fields above). A player absent
                    # from the map genuinely has no snap rows this pull — resolve to
                    # None — so a stale prior snap_pct can't survive. An all-NaN mean
                    # also resolves to None (regression case from #631).
                    raw = snap_by_gsis.get(gsis)
                    stat.snap_pct = None if raw is None or pd.isna(raw) else float(raw)
                if pbp_available:
                    # Likewise for PBP-derived fields: a player absent from this run's
                    # red-zone plays genuinely has zero looks / zero expected TDs, so
                    # write the zero rather than leave a stale (often larger) value.
                    stat.red_zone_looks = rz_looks.get(gsis, 0)
                    stat.expected_tds = round(xtds.get(gsis, 0.0), 3)

                total_upserted += 1

            # Per-season schedule → TeamSeason (points scored + rank).
            # Failures here are silent — schedule data is supplemental and shouldn't fail the whole fetcher.
            try:
                schedule_df = import_schedules([season])
            except Exception:
                schedule_df = None

            if schedule_df is not None and not schedule_df.empty:
                points_by_team: dict[str, int] = {}
                for _, game in schedule_df.iterrows():
                    home, away = game.get("home_team"), game.get("away_team")
                    home_pts = int(game.get("home_score") or 0)
                    away_pts = int(game.get("away_score") or 0)
                    if isinstance(home, str):
                        points_by_team[home] = points_by_team.get(home, 0) + home_pts
                    if isinstance(away, str):
                        points_by_team[away] = points_by_team.get(away, 0) + away_pts

                ranked = sorted(points_by_team.items(), key=lambda kv: kv[1], reverse=True)
                rank_by_team = {team: i + 1 for i, (team, _) in enumerate(ranked)}

                existing_ts = (await db.scalars(
                    select(TeamSeason).where(TeamSeason.season == season)
                )).all()
                ts_by_team = {ts.team: ts for ts in existing_ts}

                for team, pts in points_by_team.items():
                    ts = ts_by_team.get(team)
                    if ts is None:
                        ts = TeamSeason(team=team, season=season,
                                        points_scored=pts,
                                        points_rank=rank_by_team[team],
                                        last_updated=date.today())
                        db.add(ts)
                    else:
                        ts.points_scored = pts
                        ts.points_rank = rank_by_team[team]
                        ts.last_updated = date.today()

        if total_upserted == 0 and last_err is not None:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False,
                                error=f"failed for all seasons: {last_err}")

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=total_upserted,
                            last_attempted=attempted, success=True, error=None)
