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
#
# The hand-tuned elite players below carry rich (xfp-relevant) stats. The RB/WR
# pools are then padded out to realistic depth (~32 each) by _build_depth() so
# their VBD replacement baselines (RB30/WR30 at mult 2.5 in a 12-team league)
# land on real mid-pack players instead of the degenerate worst-of-4 fallback.
_ELITE: list[dict] = [
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
    # QB3..QB24 - realistic 2025-era starters with a smooth, monotone decline.
    # QB is a single-format-equivalent position, so ppr == half_ppr == standard.
    # The decline is engineered so the QB12 replacement baseline (12-team league)
    # lands ~285 ppr (Dak Prescott, ESPN) and QB24 ~243 ppr - a real
    # replacement-level player rather
    # than the degenerate 2-QB fallback. Prereq for #310 QB VBD recalibration.
    {
        "id": "qb_daniels", "name": "Jayden Daniels", "position": "QB", "team": "WAS",
        "age": 25, "years_exp": 2,
        "stats": {"season": 2025, "pass_att": 500, "pass_yards": 3950, "pass_tds": 28,
                  "interceptions": 9, "rush_att": 130, "rush_yards": 820, "rush_tds": 7, "games_played": 17},
        "projections": {"ppr": (366.0, 372.0), "half_ppr": (366.0, 372.0), "standard": (366.0, 372.0)},
        "adp": {"ppr": 24.0, "half_ppr": 24.0, "standard": 23.0, "dynasty": 8.0},
    },
    {
        "id": "qb_hurts", "name": "Jalen Hurts", "position": "QB", "team": "PHI",
        "age": 27, "years_exp": 6,
        "stats": {"season": 2025, "pass_att": 480, "pass_yards": 3650, "pass_tds": 24,
                  "interceptions": 10, "rush_att": 150, "rush_yards": 600, "rush_tds": 13, "games_played": 17},
        "projections": {"ppr": (354.0, 360.0), "half_ppr": (354.0, 360.0), "standard": (354.0, 360.0)},
        "adp": {"ppr": 28.0, "half_ppr": 28.0, "standard": 27.0, "dynasty": 14.0},
    },
    {
        "id": "qb_burrow", "name": "Joe Burrow", "position": "QB", "team": "CIN",
        "age": 29, "years_exp": 6,
        "stats": {"season": 2025, "pass_att": 600, "pass_yards": 4600, "pass_tds": 38,
                  "interceptions": 11, "rush_att": 40, "rush_yards": 120, "rush_tds": 2, "games_played": 17},
        "projections": {"ppr": (342.0, 348.0), "half_ppr": (342.0, 348.0), "standard": (342.0, 348.0)},
        "adp": {"ppr": 36.0, "half_ppr": 36.0, "standard": 35.0, "dynasty": 16.0},
    },
    {
        "id": "qb_mahomes", "name": "Patrick Mahomes", "position": "QB", "team": "KC",
        "age": 30, "years_exp": 9,
        "stats": {"season": 2025, "pass_att": 580, "pass_yards": 4350, "pass_tds": 31,
                  "interceptions": 10, "rush_att": 60, "rush_yards": 320, "rush_tds": 3, "games_played": 17},
        "projections": {"ppr": (330.0, 336.0), "half_ppr": (330.0, 336.0), "standard": (330.0, 336.0)},
        "adp": {"ppr": 42.0, "half_ppr": 42.0, "standard": 41.0, "dynasty": 22.0},
    },
    {
        "id": "qb_nix", "name": "Bo Nix", "position": "QB", "team": "DEN",
        "age": 26, "years_exp": 2,
        "stats": {"season": 2025, "pass_att": 540, "pass_yards": 3900, "pass_tds": 29,
                  "interceptions": 12, "rush_att": 90, "rush_yards": 420, "rush_tds": 5, "games_played": 17},
        "projections": {"ppr": (318.0, 324.0), "half_ppr": (318.0, 324.0), "standard": (318.0, 324.0)},
        "adp": {"ppr": 60.0, "half_ppr": 60.0, "standard": 58.0, "dynasty": 40.0},
    },
    {
        "id": "qb_mayfield", "name": "Baker Mayfield", "position": "QB", "team": "TB",
        "age": 30, "years_exp": 8,
        "stats": {"season": 2025, "pass_att": 560, "pass_yards": 4100, "pass_tds": 33,
                  "interceptions": 13, "rush_att": 55, "rush_yards": 230, "rush_tds": 3, "games_played": 17},
        "projections": {"ppr": (308.0, 314.0), "half_ppr": (308.0, 314.0), "standard": (308.0, 314.0)},
        "adp": {"ppr": 66.0, "half_ppr": 66.0, "standard": 64.0, "dynasty": 55.0},
    },
    {
        "id": "qb_herbert", "name": "Justin Herbert", "position": "QB", "team": "LAC",
        "age": 27, "years_exp": 6,
        "stats": {"season": 2025, "pass_att": 570, "pass_yards": 4200, "pass_tds": 27,
                  "interceptions": 9, "rush_att": 50, "rush_yards": 260, "rush_tds": 3, "games_played": 17},
        "projections": {"ppr": (300.0, 306.0), "half_ppr": (300.0, 306.0), "standard": (300.0, 306.0)},
        "adp": {"ppr": 72.0, "half_ppr": 72.0, "standard": 70.0, "dynasty": 38.0},
    },
    {
        "id": "qb_purdy", "name": "Brock Purdy", "position": "QB", "team": "SF",
        "age": 26, "years_exp": 4,
        "stats": {"season": 2025, "pass_att": 510, "pass_yards": 4050, "pass_tds": 28,
                  "interceptions": 11, "rush_att": 45, "rush_yards": 180, "rush_tds": 2, "games_played": 17},
        "projections": {"ppr": (293.0, 299.0), "half_ppr": (293.0, 299.0), "standard": (293.0, 299.0)},
        "adp": {"ppr": 78.0, "half_ppr": 78.0, "standard": 76.0, "dynasty": 44.0},
    },
    {
        "id": "qb_stroud", "name": "C.J. Stroud", "position": "QB", "team": "HOU",
        "age": 24, "years_exp": 3,
        "stats": {"season": 2025, "pass_att": 540, "pass_yards": 4150, "pass_tds": 26,
                  "interceptions": 9, "rush_att": 40, "rush_yards": 200, "rush_tds": 2, "games_played": 17},
        "projections": {"ppr": (288.0, 294.0), "half_ppr": (288.0, 294.0), "standard": (288.0, 294.0)},
        "adp": {"ppr": 84.0, "half_ppr": 84.0, "standard": 82.0, "dynasty": 30.0},
    },
    {
        "id": "qb_prescott", "name": "Dak Prescott", "position": "QB", "team": "DAL",
        "age": 32, "years_exp": 10,
        "stats": {"season": 2025, "pass_att": 590, "pass_yards": 4300, "pass_tds": 30,
                  "interceptions": 11, "rush_att": 35, "rush_yards": 140, "rush_tds": 2, "games_played": 17},
        "projections": {"ppr": (285.0, 291.0), "half_ppr": (285.0, 291.0), "standard": (285.0, 291.0)},
        "adp": {"ppr": 90.0, "half_ppr": 90.0, "standard": 88.0, "dynasty": 70.0},
    },
    {
        "id": "qb_goff", "name": "Jared Goff", "position": "QB", "team": "DET",
        "age": 31, "years_exp": 10,
        "stats": {"season": 2025, "pass_att": 560, "pass_yards": 4250, "pass_tds": 31,
                  "interceptions": 10, "rush_att": 20, "rush_yards": 30, "rush_tds": 1, "games_played": 17},
        "projections": {"ppr": (281.0, 287.0), "half_ppr": (281.0, 287.0), "standard": (281.0, 287.0)},
        "adp": {"ppr": 96.0, "half_ppr": 96.0, "standard": 94.0, "dynasty": 78.0},
    },
    {
        "id": "qb_williams", "name": "Caleb Williams", "position": "QB", "team": "CHI",
        "age": 24, "years_exp": 2,
        "stats": {"season": 2025, "pass_att": 530, "pass_yards": 3850, "pass_tds": 25,
                  "interceptions": 11, "rush_att": 75, "rush_yards": 340, "rush_tds": 3, "games_played": 17},
        "projections": {"ppr": (276.0, 282.0), "half_ppr": (276.0, 282.0), "standard": (276.0, 282.0)},
        "adp": {"ppr": 102.0, "half_ppr": 102.0, "standard": 100.0, "dynasty": 36.0},
    },
    {
        "id": "qb_murray", "name": "Kyler Murray", "position": "QB", "team": "ARI",
        "age": 28, "years_exp": 7,
        "stats": {"season": 2025, "pass_att": 510, "pass_yards": 3700, "pass_tds": 22,
                  "interceptions": 10, "rush_att": 80, "rush_yards": 480, "rush_tds": 5, "games_played": 16},
        "projections": {"ppr": (272.0, 278.0), "half_ppr": (272.0, 278.0), "standard": (272.0, 278.0)},
        "adp": {"ppr": 108.0, "half_ppr": 108.0, "standard": 106.0, "dynasty": 60.0},
    },
    {
        "id": "qb_lawrence", "name": "Trevor Lawrence", "position": "QB", "team": "JAX",
        "age": 26, "years_exp": 5,
        "stats": {"season": 2025, "pass_att": 540, "pass_yards": 3950, "pass_tds": 24,
                  "interceptions": 11, "rush_att": 55, "rush_yards": 260, "rush_tds": 3, "games_played": 17},
        "projections": {"ppr": (268.0, 274.0), "half_ppr": (268.0, 274.0), "standard": (268.0, 274.0)},
        "adp": {"ppr": 114.0, "half_ppr": 114.0, "standard": 112.0, "dynasty": 64.0},
    },
    {
        "id": "qb_maye", "name": "Drake Maye", "position": "QB", "team": "NE",
        "age": 23, "years_exp": 2,
        "stats": {"season": 2025, "pass_att": 520, "pass_yards": 3750, "pass_tds": 22,
                  "interceptions": 12, "rush_att": 70, "rush_yards": 360, "rush_tds": 3, "games_played": 17},
        "projections": {"ppr": (264.0, 270.0), "half_ppr": (264.0, 270.0), "standard": (264.0, 270.0)},
        "adp": {"ppr": 120.0, "half_ppr": 120.0, "standard": 118.0, "dynasty": 50.0},
    },
    {
        "id": "qb_tagovailoa", "name": "Tua Tagovailoa", "position": "QB", "team": "MIA",
        "age": 27, "years_exp": 6,
        "stats": {"season": 2025, "pass_att": 540, "pass_yards": 3900, "pass_tds": 25,
                  "interceptions": 12, "rush_att": 25, "rush_yards": 50, "rush_tds": 1, "games_played": 15},
        "projections": {"ppr": (260.0, 266.0), "half_ppr": (260.0, 266.0), "standard": (260.0, 266.0)},
        "adp": {"ppr": 126.0, "half_ppr": 126.0, "standard": 124.0, "dynasty": 82.0},
    },
    {
        "id": "qb_love", "name": "Jordan Love", "position": "QB", "team": "GB",
        "age": 27, "years_exp": 6,
        "stats": {"season": 2025, "pass_att": 510, "pass_yards": 3800, "pass_tds": 28,
                  "interceptions": 12, "rush_att": 45, "rush_yards": 200, "rush_tds": 2, "games_played": 16},
        "projections": {"ppr": (256.0, 262.0), "half_ppr": (256.0, 262.0), "standard": (256.0, 262.0)},
        "adp": {"ppr": 132.0, "half_ppr": 132.0, "standard": 130.0, "dynasty": 58.0},
    },
    {
        "id": "qb_stafford", "name": "Matthew Stafford", "position": "QB", "team": "LAR",
        "age": 37, "years_exp": 17,
        "stats": {"season": 2025, "pass_att": 540, "pass_yards": 3850, "pass_tds": 26,
                  "interceptions": 10, "rush_att": 18, "rush_yards": 25, "rush_tds": 1, "games_played": 16},
        "projections": {"ppr": (253.0, 259.0), "half_ppr": (253.0, 259.0), "standard": (253.0, 259.0)},
        "adp": {"ppr": 138.0, "half_ppr": 138.0, "standard": 136.0, "dynasty": 130.0},
    },
    {
        "id": "qb_darnold", "name": "Sam Darnold", "position": "QB", "team": "SEA",
        "age": 28, "years_exp": 8,
        "stats": {"season": 2025, "pass_att": 520, "pass_yards": 3700, "pass_tds": 25,
                  "interceptions": 12, "rush_att": 40, "rush_yards": 160, "rush_tds": 2, "games_played": 16},
        "projections": {"ppr": (250.0, 256.0), "half_ppr": (250.0, 256.0), "standard": (250.0, 256.0)},
        "adp": {"ppr": 144.0, "half_ppr": 144.0, "standard": 142.0, "dynasty": 110.0},
    },
    {
        "id": "qb_fields", "name": "Justin Fields", "position": "QB", "team": "NYJ",
        "age": 27, "years_exp": 5,
        "stats": {"season": 2025, "pass_att": 440, "pass_yards": 3000, "pass_tds": 18,
                  "interceptions": 9, "rush_att": 110, "rush_yards": 620, "rush_tds": 6, "games_played": 16},
        "projections": {"ppr": (248.0, 254.0), "half_ppr": (248.0, 254.0), "standard": (248.0, 254.0)},
        "adp": {"ppr": 150.0, "half_ppr": 150.0, "standard": 148.0, "dynasty": 90.0},
    },
    {
        "id": "qb_smith", "name": "Geno Smith", "position": "QB", "team": "LV",
        "age": 35, "years_exp": 13,
        "stats": {"season": 2025, "pass_att": 540, "pass_yards": 3750, "pass_tds": 22,
                  "interceptions": 13, "rush_att": 35, "rush_yards": 120, "rush_tds": 1, "games_played": 16},
        "projections": {"ppr": (246.0, 252.0), "half_ppr": (246.0, 252.0), "standard": (246.0, 252.0)},
        "adp": {"ppr": 156.0, "half_ppr": 156.0, "standard": 154.0, "dynasty": 150.0},
    },
    {
        "id": "qb_rodgers", "name": "Aaron Rodgers", "position": "QB", "team": "PIT",
        "age": 42, "years_exp": 21,
        "stats": {"season": 2025, "pass_att": 500, "pass_yards": 3500, "pass_tds": 23,
                  "interceptions": 9, "rush_att": 20, "rush_yards": 40, "rush_tds": 1, "games_played": 16},
        "projections": {"ppr": (243.0, 249.0), "half_ppr": (243.0, 249.0), "standard": (243.0, 249.0)},
        "adp": {"ppr": 162.0, "half_ppr": 162.0, "standard": 160.0, "dynasty": 200.0},
    },
]


# ---------------------------------------------------------------------------
# Depth pools
#
# Real player names in approximate redraft order, used to pad the RB/WR pools
# out to realistic depth below the hand-tuned elite above. Each (name, team)
# gets a synthetic but smoothly-declining projection curve so the sorted pool
# is strictly monotone with no cliffs in the mid-pack — exactly the region the
# VBD replacement baseline (RB30/WR30) reads from.
# ---------------------------------------------------------------------------
_WR_DEPTH: list[tuple[str, str]] = [
    ("Amon-Ra St. Brown", "DET"), ("A.J. Brown", "PHI"), ("Puka Nacua", "LAR"),
    ("Malik Nabers", "NYG"), ("Brian Thomas Jr.", "JAX"), ("Nico Collins", "HOU"),
    ("Drake London", "ATL"), ("Garrett Wilson", "NYJ"), ("Davante Adams", "LV"),
    ("Marvin Harrison Jr.", "ARI"), ("DK Metcalf", "SEA"), ("Mike Evans", "TB"),
    ("DeVonta Smith", "PHI"), ("Terry McLaurin", "WAS"), ("Jaylen Waddle", "MIA"),
    ("Chris Olave", "NO"), ("DJ Moore", "CHI"), ("Tee Higgins", "CIN"),
    ("Zay Flowers", "BAL"), ("George Pickens", "DAL"), ("Cooper Kupp", "SEA"),
    ("Calvin Ridley", "TEN"), ("Jaxon Smith-Njigba", "SEA"), ("Jordan Addison", "MIN"),
    ("Rashee Rice", "KC"), ("Keon Coleman", "BUF"), ("Jameson Williams", "DET"),
    ("Rome Odunze", "CHI"), ("Jerry Jeudy", "CLE"), ("Christian Kirk", "HOU"),
    ("Courtland Sutton", "DEN"), ("Stefon Diggs", "NE"),
]

_RB_DEPTH: list[tuple[str, str]] = [
    ("Jahmyr Gibbs", "DET"), ("Jonathan Taylor", "IND"), ("De'Von Achane", "MIA"),
    ("Ashton Jeanty", "LV"), ("Josh Jacobs", "GB"), ("Kyren Williams", "LAR"),
    ("Breece Hall", "NYJ"), ("Chase Brown", "CIN"), ("Kenneth Walker III", "SEA"),
    ("James Cook", "BUF"), ("Alvin Kamara", "NO"), ("Joe Mixon", "HOU"),
    ("Bucky Irving", "TB"), ("Chuba Hubbard", "CAR"), ("David Montgomery", "DET"),
    ("Aaron Jones", "MIN"), ("James Conner", "ARI"), ("D'Andre Swift", "CHI"),
    ("Tony Pollard", "TEN"), ("Rhamondre Stevenson", "NE"), ("Najee Harris", "LAC"),
    ("Isiah Pacheco", "KC"), ("Brian Robinson Jr.", "WAS"), ("Travis Etienne", "JAX"),
    ("Rachaad White", "TB"), ("Zamir White", "LV"), ("Tyjae Spears", "TEN"),
    ("Jaylen Warren", "PIT"), ("Jordan Mason", "MIN"), ("Tyrone Tracy Jr.", "NYG"),
    ("Javonte Williams", "DAL"), ("J.K. Dobbins", "DEN"),
]

# Per-position settings for the synthetic depth curve. `top`/`floor` bracket the
# PPR projection range the depth tier spans; it starts just below the lowest
# elite PPR projection so the combined sorted pool stays monotone. `curve` > 1
# makes the decline mildly convex (more separation up top, compression at the
# back) the way a real positional value curve behaves. `half`/`std` are the
# format multipliers applied to the PPR value (RBs lose less without PPR).
_DEPTH_CURVES = {
    "WR": {"top": 240.0, "floor": 120.0, "curve": 1.25, "half": 0.82, "std": 0.64},
    "RB": {"top": 240.0, "floor": 95.0, "curve": 1.3, "half": 0.93, "std": 0.87},
}

# FantasyPros source runs slightly above ESPN, mirroring the elite entries.
_FP_FACTOR = 1.02


def _decline(top: float, floor: float, n: int, rank: int, curve: float) -> float:
    """Monotone-decreasing value for 0-indexed `rank` in a pool of `n`.

    Interpolates from `top` (rank 0) down to `floor` (rank n-1) along a convex
    curve. Strictly decreasing in `rank` for curve > 0, so the resulting pool
    has no ties or upward steps.
    """
    if n <= 1:
        return top
    t = rank / (n - 1)
    return round(floor + (top - floor) * ((1.0 - t) ** curve), 1)


def _depth_projections(position: str, ppr: float) -> dict:
    """Build the per-format projection block for a depth player from its PPR value."""
    c = _DEPTH_CURVES[position]
    half = round(ppr * c["half"], 1)
    std = round(ppr * c["std"], 1)
    return {
        "ppr": (ppr, round(ppr * _FP_FACTOR, 1)),
        "half_ppr": (half, round(half * _FP_FACTOR, 1)),
        "standard": (std, round(std * _FP_FACTOR, 1)),
    }


def _depth_stats(position: str, ppr: float, season: int) -> dict:
    """Reasonable, non-degenerate prior-year stats derived from the PPR projection.

    Scales with the projection so deeper players don't all share identical
    volume (which would flatten the xfp-style rules in the dev container).
    """
    if position == "WR":
        receptions = round(ppr * 0.33)
        targets = round(receptions / 0.65)
        rec_tds = max(1, round(ppr * 0.022))
        return {
            "season": season,
            "targets": targets, "receptions": receptions,
            "rec_yards": round(receptions * 13), "rec_tds": rec_tds,
            "games_played": 17, "snap_pct": round(min(0.9, 0.55 + ppr / 800), 2),
            "target_share": round(min(0.30, 0.10 + ppr / 1500), 2),
            "actual_tds": rec_tds, "expected_tds": rec_tds,
            "red_zone_looks": rec_tds * 3,
        }
    # RB
    rush_att = round(ppr * 0.8)
    rush_tds = max(1, round(ppr * 0.03))
    targets = round(ppr * 0.18)
    receptions = round(targets * 0.78)
    rec_tds = max(0, round(ppr * 0.005))
    return {
        "season": season,
        "rush_att": rush_att, "rush_yards": round(rush_att * 4.3), "rush_tds": rush_tds,
        "targets": targets, "receptions": receptions, "rec_yards": round(receptions * 8),
        "rec_tds": rec_tds,
        "games_played": 17, "snap_pct": round(min(0.8, 0.40 + ppr / 700), 2),
        "carry_share": round(min(0.70, 0.30 + ppr / 600), 2),
        "actual_tds": rush_tds + rec_tds, "expected_tds": rush_tds + rec_tds,
        "red_zone_looks": (rush_tds + rec_tds) * 3,
    }


def _build_depth(season: int = 2025) -> list[dict]:
    """Expand the RB/WR pools to realistic depth with a smooth, monotone curve."""
    out: list[dict] = []
    for position, roster in (("WR", _WR_DEPTH), ("RB", _RB_DEPTH)):
        c = _DEPTH_CURVES[position]
        # Fail-fast invariant: the depth curve must start strictly below the
        # weakest elite PPR projection. The elite tier is hand-tuned and the
        # depth `top` is a constant, so if someone lowers an elite projection (or
        # raises the curve) the combined elite+depth board silently goes
        # non-monotone — a generated depth player would outrank a real elite.
        # Guard it here so the seed blows up at build time instead.
        min_elite_ppr = min(
            p["projections"]["ppr"][0] for p in _ELITE if p["position"] == position
        )
        if c["top"] >= min_elite_ppr:
            raise ValueError(
                f"{position} depth top {c['top']} must stay below the weakest "
                f"elite PPR projection {min_elite_ppr} to keep the combined "
                "board monotone"
            )
        n = len(roster)
        for rank, (name, team) in enumerate(roster):
            ppr = _decline(c["top"], c["floor"], n, rank, c["curve"])
            # Overall draft slot for this depth player: elite occupy the very top,
            # so depth ADP starts in the late 2nd round and fans out from there.
            adp = round(20.0 + rank * 5.0, 1)
            age = 23 + (rank % 8)
            out.append({
                "id": f"{position.lower()}_depth_{rank + 5:02d}",
                "name": name,
                "position": position,
                "team": team,
                "age": age,
                "years_exp": max(1, age - 22),
                "stats": _depth_stats(position, ppr, season),
                "projections": _depth_projections(position, ppr),
                "adp": {
                    "ppr": adp, "half_ppr": adp,
                    "standard": round(adp * 1.05, 1),
                    "dynasty": round(adp * 1.1, 1),
                },
            })
    return out


# Final seed roster: hand-tuned elite + generated depth.
PLAYERS: list[dict] = _ELITE + _build_depth()


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
