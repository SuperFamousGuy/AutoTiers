"""Calibration script for the opportunity-score regression rule.

Runs against historical NFL seasons via nfl_data_py:
1. For each year Y in --years, build pseudo-PlayerStat rows from nfl_data_py.
2. Compute xFP and z-score per player.
3. Look at season Y+1: did over-producers (z >= 1.5) actually regress?
   Did under-producers (z <= -1.5) actually rebound?
4. Report: hit rate, average effect size, distribution percentiles.

Not run in CI. Run by hand:

    cd backend && venv/bin/python -m scripts.calibrate_xfp_rule \\
        --years 2022 2023 2024 --output /tmp/xfp_calibration.json

Output JSON gets attached to the implementation PR for review.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from statistics import mean

# Lazy import — nfl_data_py is heavy.
def _load_nfl_data_py():
    try:
        import nfl_data_py as nfl
        return nfl
    except ImportError:
        print("nfl_data_py not installed in this venv. Install with: pip install nfl_data_py", file=sys.stderr)
        sys.exit(2)


from app.engine.scoring import LeagueSettings, LeagueType, ScoringFormat
from app.engine.xfp import (
    compute_league_averages,
    compute_per_position_sigmas,
    compute_opportunity_score_z,
    compute_xfp,
    _MIN_GAMES_PLAYED,
    _MIN_OPPORTUNITY_BY_POSITION,
)


@dataclass
class _CalibrationStat:
    player_id: str
    position: str
    targets: int
    receptions: int
    rec_yards: float
    rec_tds: int
    rush_att: int
    rush_yards: float
    rush_tds: int
    red_zone_looks: int
    games_played: int
    fantasy_points: float
    pass_att: int = 0
    pass_yards: float = 0.0
    pass_tds: int = 0
    interceptions: int = 0


def _ppr_settings() -> LeagueSettings:
    return LeagueSettings(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=1.0, weight_espn=0.0, weight_consensus=0.0,
    )


def _load_year(nfl, year: int) -> list[_CalibrationStat]:
    """Pull seasonal data from nfl_data_py and build _CalibrationStat rows.

    Column names in nfl_data_py can drift across versions. If a column is
    missing, defaults to 0 / 0.0. The script prints a warning listing
    which columns it couldn't find so the user can investigate.
    """
    seasonal = nfl.import_seasonal_data([year])
    seasonal = seasonal[seasonal["position"].isin(["QB", "RB", "WR", "TE"])]
    rows: list[_CalibrationStat] = []

    # Column-name candidates — nfl_data_py has renamed columns across releases.
    # The first existing one wins.
    def _col(r, *candidates, default=0):
        for c in candidates:
            if c in r and r.get(c) is not None:
                return r[c]
        return default

    for _, r in seasonal.iterrows():
        rz_carries = int(_col(r, "red_zone_carries", "rz_carries", default=0) or 0)
        rz_targets = int(_col(r, "red_zone_targets", "rz_targets", default=0) or 0)
        rows.append(_CalibrationStat(
            player_id=str(_col(r, "player_id", "gsis_id", default="")),
            position=str(r["position"]),
            targets=int(_col(r, "targets", default=0) or 0),
            receptions=int(_col(r, "receptions", default=0) or 0),
            rec_yards=float(_col(r, "receiving_yards", "rec_yards", default=0.0) or 0.0),
            rec_tds=int(_col(r, "receiving_tds", "rec_tds", default=0) or 0),
            rush_att=int(_col(r, "carries", "rushing_attempts", default=0) or 0),
            rush_yards=float(_col(r, "rushing_yards", "rush_yards", default=0.0) or 0.0),
            rush_tds=int(_col(r, "rushing_tds", "rush_tds", default=0) or 0),
            red_zone_looks=rz_carries + rz_targets,
            games_played=int(_col(r, "games", "games_played", default=0) or 0),
            fantasy_points=float(_col(r, "fantasy_points_ppr", "fantasy_points", default=0.0) or 0.0),
        ))
    return rows


def calibrate(years: list[int]) -> dict:
    """Run the calibration for the given seasons. Returns the report dict."""
    nfl = _load_nfl_data_py()
    settings = _ppr_settings()
    report: dict = {"years": {}, "summary": {}}

    over_predicted_regression: list[float] = []
    under_predicted_bounce: list[float] = []
    overall_baseline_change: list[float] = []

    for y in years:
        print(f"Loading {y} and {y+1}...", file=sys.stderr)
        stats_y = _load_year(nfl, y)
        stats_y_plus_1 = _load_year(nfl, y + 1)
        next_year_fp = {s.player_id: s.fantasy_points for s in stats_y_plus_1}

        avg = compute_league_averages(stats_y, settings)

        # Build gaps and per-player (stat, fp, xfp)
        from app.engine.scoring import PlayerStats as _PS, _score_receiving, _score_rushing, _score_tds_only
        gaps_by_pos: dict[str, list[float]] = {}
        per_player: list[tuple[_CalibrationStat, float, float]] = []
        for s in stats_y:
            if (s.games_played or 0) < _MIN_GAMES_PLAYED:
                continue
            opportunity = (s.targets or 0) + (s.rush_att or 0) + (s.red_zone_looks or 0)
            if opportunity < _MIN_OPPORTUNITY_BY_POSITION.get(s.position, 50):
                continue
            xfp = compute_xfp(s, avg)
            if xfp is None:
                continue
            ps = _PS(
                targets=s.targets, receptions=s.receptions, rec_yards=s.rec_yards, rec_tds=s.rec_tds,
                rush_att=s.rush_att, rush_yards=s.rush_yards, rush_tds=s.rush_tds,
                pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0, games_played=max(s.games_played, 1),
            )
            fp = _score_receiving(ps, settings, s.position) + _score_rushing(ps, settings) + _score_tds_only(ps, settings)
            gaps_by_pos.setdefault(s.position, []).append(fp - xfp)
            per_player.append((s, fp, xfp))

        sigmas = compute_per_position_sigmas(gaps_by_pos)

        year_over: list[float] = []
        year_under: list[float] = []
        year_baseline: list[float] = []
        for s, fp, xfp in per_player:
            z = compute_opportunity_score_z(s, avg, sigmas, settings)
            if z is None:
                continue
            next_fp = next_year_fp.get(s.player_id)
            if next_fp is None or fp == 0:
                continue
            pct_change = (next_fp - fp) / fp
            year_baseline.append(pct_change)
            if z >= 1.5:
                year_over.append(pct_change)
                over_predicted_regression.append(pct_change)
            elif z <= -1.5:
                year_under.append(pct_change)
                under_predicted_bounce.append(pct_change)

        report["years"][y] = {
            "n_over_fired": len(year_over),
            "n_under_fired": len(year_under),
            "n_baseline": len(year_baseline),
            "over_avg_next_year_change_pct":     mean(year_over) * 100     if year_over else None,
            "under_avg_next_year_change_pct":    mean(year_under) * 100    if year_under else None,
            "baseline_avg_next_year_change_pct": mean(year_baseline) * 100 if year_baseline else None,
        }
        overall_baseline_change.extend(year_baseline)

    report["summary"] = {
        "over_avg_change_pct":     mean(over_predicted_regression) * 100  if over_predicted_regression else None,
        "under_avg_change_pct":    mean(under_predicted_bounce) * 100     if under_predicted_bounce else None,
        "baseline_avg_change_pct": mean(overall_baseline_change) * 100    if overall_baseline_change else None,
        "note": "Acceptable result: over_avg below baseline by ~8%+; under_avg above by ~8%+.",
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = calibrate(args.years)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote calibration report to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
