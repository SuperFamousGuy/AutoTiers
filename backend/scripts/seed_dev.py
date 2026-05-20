"""
Seed the dev database with a small fixed roster so the API returns meaningful
results before the real data pipeline (Plan 2) is built. Idempotent — safe to
run on every container start.

Run inside the api container (or any env with DATABASE_URL set):
    python -m scripts.seed_dev
"""
from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models.adp import ADPData


# Each entry: id, name, position, team, age, years_exp, prior-year stats,
# projections per format, and ADP per format. Values are reasonable order-of-
# magnitude estimates for dev testing — not real projections.
PLAYERS: list[dict] = [
    # ---------- WR ----------
    {
        "id": "wr_chase",
        "name": "Ja'Marr Chase",
        "position": "WR",
        "team": "CIN",
        "age": 26,
        "years_exp": 4,
        "stats": {
            "season": 2025,
            "targets": 175, "receptions": 127, "rec_yards": 1708, "rec_tds": 17,
            "games_played": 17, "snap_pct": 0.92, "target_share": 0.32,
            "actual_tds": 17, "expected_tds": 12.4, "red_zone_looks": 28,
        },
        "projections": {"ppr": (340.0, 350.0), "half_ppr": (276.0, 286.0), "standard": (212.0, 220.0)},
        "adp": {"ppr": 1.5, "half_ppr": 2.0, "standard": 3.0, "dynasty": 1.0},
    },
    {
        "id": "wr_jefferson",
        "name": "Justin Jefferson",
        "position": "WR",
        "team": "MIN",
        "age": 27,
        "years_exp": 5,
        "stats": {
            "season": 2025,
            "targets": 154, "receptions": 103, "rec_yards": 1533, "rec_tds": 10,
            "games_played": 17, "snap_pct": 0.94, "target_share": 0.29,
            "actual_tds": 10, "expected_tds": 9.8,
        },
        "projections": {"ppr": (315.0, 322.0), "half_ppr": (263.0, 270.0), "standard": (212.0, 218.0)},
        "adp": {"ppr": 2.5, "half_ppr": 3.0, "standard": 4.0, "dynasty": 2.0},
    },
    {
        "id": "wr_lamb",
        "name": "CeeDee Lamb",
        "position": "WR",
        "team": "DAL",
        "age": 27,
        "years_exp": 5,
        "stats": {
            "season": 2025,
            "targets": 152, "receptions": 101, "rec_yards": 1194, "rec_tds": 6,
            "games_played": 14, "snap_pct": 0.93, "target_share": 0.30,
            "actual_tds": 6, "expected_tds": 8.1,
        },
        "projections": {"ppr": (290.0, 298.0), "half_ppr": (239.0, 247.0), "standard": (189.0, 196.0)},
        "adp": {"ppr": 5.0, "half_ppr": 6.0, "standard": 8.0, "dynasty": 5.0},
    },
    {
        "id": "wr_hill",
        "name": "Tyreek Hill",
        "position": "WR",
        "team": "MIA",
        "age": 32,
        "years_exp": 9,
        "stats": {
            "season": 2025,
            "targets": 110, "receptions": 79, "rec_yards": 950, "rec_tds": 6,
            "games_played": 15, "snap_pct": 0.86, "target_share": 0.22,
            "actual_tds": 6, "expected_tds": 7.2,
        },
        "projections": {"ppr": (245.0, 252.0), "half_ppr": (205.0, 211.0), "standard": (165.0, 170.0)},
        "adp": {"ppr": 22.0, "half_ppr": 24.0, "standard": 28.0, "dynasty": 35.0},
    },
    # ---------- RB ----------
    {
        "id": "rb_mccaffrey",
        "name": "Christian McCaffrey",
        "position": "RB",
        "team": "SF",
        "age": 29,
        "years_exp": 8,
        "stats": {
            "season": 2025,
            "targets": 50, "receptions": 38, "rec_yards": 320, "rec_tds": 2,
            "rush_att": 220, "rush_yards": 1010, "rush_tds": 9,
            "games_played": 14, "snap_pct": 0.78, "carry_share": 0.62,
            "actual_tds": 11, "expected_tds": 12.5, "red_zone_looks": 34,
        },
        "projections": {"ppr": (270.0, 278.0), "half_ppr": (252.0, 260.0), "standard": (234.0, 242.0)},
        "adp": {"ppr": 4.0, "half_ppr": 4.0, "standard": 5.0, "dynasty": 18.0},
    },
    {
        "id": "rb_robinson",
        "name": "Bijan Robinson",
        "position": "RB",
        "team": "ATL",
        "age": 23,
        "years_exp": 2,
        "stats": {
            "season": 2025,
            "targets": 70, "receptions": 58, "rec_yards": 431, "rec_tds": 1,
            "rush_att": 245, "rush_yards": 1226, "rush_tds": 11,
            "games_played": 17, "snap_pct": 0.82, "carry_share": 0.68,
            "actual_tds": 12, "expected_tds": 10.8, "red_zone_looks": 38,
        },
        "projections": {"ppr": (305.0, 312.0), "half_ppr": (276.0, 283.0), "standard": (247.0, 254.0)},
        "adp": {"ppr": 3.0, "half_ppr": 2.5, "standard": 2.0, "dynasty": 3.0},
    },
    {
        "id": "rb_barkley",
        "name": "Saquon Barkley",
        "position": "RB",
        "team": "PHI",
        "age": 28,
        "years_exp": 7,
        "stats": {
            "season": 2025,
            "targets": 45, "receptions": 36, "rec_yards": 271, "rec_tds": 0,
            "rush_att": 290, "rush_yards": 1610, "rush_tds": 16,
            "games_played": 16, "snap_pct": 0.74, "carry_share": 0.71,
            "actual_tds": 16, "expected_tds": 13.2, "red_zone_looks": 42,
        },
        "projections": {"ppr": (290.0, 298.0), "half_ppr": (272.0, 280.0), "standard": (254.0, 262.0)},
        "adp": {"ppr": 6.0, "half_ppr": 5.0, "standard": 4.0, "dynasty": 22.0},
    },
    {
        "id": "rb_henry",
        "name": "Derrick Henry",
        "position": "RB",
        "team": "BAL",
        "age": 31,
        "years_exp": 9,
        "stats": {
            "season": 2025,
            "targets": 22, "receptions": 19, "rec_yards": 159, "rec_tds": 0,
            "rush_att": 275, "rush_yards": 1450, "rush_tds": 14,
            "games_played": 17, "snap_pct": 0.62, "carry_share": 0.66,
            "actual_tds": 14, "expected_tds": 11.5, "red_zone_looks": 40,
        },
        "projections": {"ppr": (245.0, 252.0), "half_ppr": (236.0, 243.0), "standard": (227.0, 234.0)},
        "adp": {"ppr": 14.0, "half_ppr": 12.0, "standard": 10.0, "dynasty": 60.0},
    },
    # ---------- QB ----------
    {
        "id": "qb_allen",
        "name": "Josh Allen",
        "position": "QB",
        "team": "BUF",
        "age": 29,
        "years_exp": 7,
        "stats": {
            "season": 2025,
            "pass_att": 525, "pass_yards": 4180, "pass_tds": 33, "interceptions": 12,
            "rush_att": 95, "rush_yards": 520, "rush_tds": 8,
            "games_played": 17,
        },
        "projections": {"ppr": (385.0, 392.0), "half_ppr": (385.0, 392.0), "standard": (385.0, 392.0)},
        "adp": {"ppr": 18.0, "half_ppr": 18.0, "standard": 17.0, "dynasty": 12.0},
    },
    {
        "id": "qb_jackson",
        "name": "Lamar Jackson",
        "position": "QB",
        "team": "BAL",
        "age": 28,
        "years_exp": 7,
        "stats": {
            "season": 2025,
            "pass_att": 480, "pass_yards": 3850, "pass_tds": 29, "interceptions": 9,
            "rush_att": 140, "rush_yards": 920, "rush_tds": 6,
            "games_played": 16,
        },
        "projections": {"ppr": (400.0, 408.0), "half_ppr": (400.0, 408.0), "standard": (400.0, 408.0)},
        "adp": {"ppr": 16.0, "half_ppr": 16.0, "standard": 15.0, "dynasty": 10.0},
    },
]


def _stat_kwargs(s: dict) -> dict:
    """Filter the stats dict to fields PlayerStat actually has, dropping None."""
    allowed = {
        "season", "targets", "receptions", "rec_yards", "rec_tds",
        "rush_att", "rush_yards", "rush_tds", "pass_att", "pass_yards", "pass_tds",
        "interceptions", "snaps", "snap_pct", "carry_share", "target_share",
        "games_played", "red_zone_looks", "actual_tds", "expected_tds",
    }
    return {k: v for k, v in s.items() if k in allowed}


async def _seed_player(session: AsyncSession, p: dict, today: date) -> bool:
    """Insert one player and its related rows if not already present. Returns True if inserted."""
    existing = (await session.execute(select(Player).where(Player.id == p["id"]))).scalar_one_or_none()
    if existing is not None:
        return False

    player = Player(
        id=p["id"],
        name=p["name"],
        position=p["position"],
        team=p["team"],
        age=p["age"],
        years_exp=p["years_exp"],
        last_updated=today,
    )
    session.add(player)

    session.add(PlayerStat(player_id=p["id"], **_stat_kwargs(p["stats"])))

    for fmt, (espn_pts, fp_pts) in p["projections"].items():
        session.add(Projection(
            player_id=p["id"], source="espn", scoring_format=fmt,
            projected_points=espn_pts, last_updated=today,
        ))
        session.add(Projection(
            player_id=p["id"], source="fantasypros", scoring_format=fmt,
            projected_points=fp_pts, last_updated=today,
        ))

    for fmt, adp in p["adp"].items():
        session.add(ADPData(
            player_id=p["id"], format=fmt, adp=adp,
            adp_source="seed_dev", last_updated=today,
        ))

    return True


async def main() -> None:
    today = date.today()
    inserted = 0
    async with AsyncSessionLocal() as session:
        for p in PLAYERS:
            if await _seed_player(session, p, today):
                inserted += 1
        await session.commit()

    skipped = len(PLAYERS) - inserted
    print(f"[seed_dev] inserted {inserted} players, skipped {skipped} (already present)")


if __name__ == "__main__":
    asyncio.run(main())
