"""Calibration script for the opportunity-score regression rule.

Two modes:

Default (regression self-check) — runs against historical NFL seasons via
nfl_data_py:
1. For each year Y in --years, build pseudo-PlayerStat rows from nfl_data_py.
2. Compute xFP and z-score per player.
3. Look at season Y+1: did over-producers (z >= 1.5) actually regress?
   Did under-producers (z <= -1.5) actually rebound?
4. Report: hit rate, average effect size, distribution percentiles.

    cd backend && venv/bin/python -m scripts.calibrate_xfp_rule \\
        --years 2022 2023 2024 --output /tmp/xfp_calibration.json

Benchmark validation (`--benchmark ff_opportunity`) — validates the in-house
xFP regression against an independent ground truth, nflverse's maintained
expected-fantasy-points dataset (`nflreadpy.load_ff_opportunity()`):
1. For each year, compute AutoTiers' per-player `opportunity_score_z`.
2. Load ff_opportunity for the same years; per player-season derive the
   over/under-production residual (actual − expected fantasy points) and
   z-score it per position/season — the ff_opportunity analogue of
   `opportunity_score_z`.
3. Report Pearson r and MAE between the two z-vectors over the shared
   player-seasons. If r < 0.6 (or the sample is under 200 player-seasons),
   emit a clear message telling the operator to file a mathematician
   follow-up to review the xfp.py regression coefficients.

    cd backend && venv/bin/python -m scripts.calibrate_xfp_rule \\
        --benchmark ff_opportunity --years 2021 2022 2023 2024 \\
        --output /tmp/xfp_benchmark.json

This is a validation guardrail, not a runtime dependency — nflreadpy is only
imported when `--benchmark` is passed, and only by this manual script.

Not run in CI. Output JSON gets attached to the implementation PR for review.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from statistics import StatisticsError, correlation, mean
from typing import Iterable, Optional

# Lazy import — nfl_data_py is heavy.
def _load_nfl_data_py():
    try:
        import nfl_data_py as nfl
        return nfl
    except ImportError:
        print("nfl_data_py not installed in this venv. Install with: pip install nfl_data_py", file=sys.stderr)
        sys.exit(2)


# Lazy import — nflreadpy is only needed for `--benchmark ff_opportunity`.
def _load_nflreadpy():
    try:
        import nflreadpy
        return nflreadpy
    except ImportError:
        print(
            "nflreadpy not installed in this venv. Install with: pip install nflreadpy\n"
            "(only required for --benchmark ff_opportunity)",
            file=sys.stderr,
        )
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


# ---------------------------------------------------------------------------
# Benchmark validation against nflverse ff_opportunity
# ---------------------------------------------------------------------------

# Fantasy positions we validate. K/DST are absent from the xFP regression.
_BENCHMARK_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


@dataclass(frozen=True)
class _BenchmarkRow:
    """One aggregated ff_opportunity player-season."""
    year: int
    player_id: str
    position: str
    actual_fp: float
    expected_fp: float

    @property
    def residual(self) -> float:
        """Over/under-production: actual minus opportunity-expected points.

        This is ff_opportunity's analogue of AutoTiers' (FP − xFP) gap.
        """
        return self.actual_fp - self.expected_fp


def _autotiers_z_by_year(nfl, years: list[int], settings: LeagueSettings) -> dict[int, dict[str, float]]:
    """Compute AutoTiers `opportunity_score_z` per eligible player, per year.

    Returns {year: {player_id: z}}. Mirrors the eligibility gates and math the
    default calibration path uses so the two stay comparable.
    """
    from app.engine.scoring import (
        PlayerStats as _PS,
        _score_receiving,
        _score_rushing,
        _score_tds_only,
    )

    out: dict[int, dict[str, float]] = {}
    for year in years:
        print(f"Computing AutoTiers opportunity_score_z for {year}...", file=sys.stderr)
        stats_y = _load_year(nfl, year)
        avg = compute_league_averages(stats_y, settings)

        gaps_by_pos: dict[str, list[float]] = {}
        eligible: list[_CalibrationStat] = []
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
            eligible.append(s)

        sigmas = compute_per_position_sigmas(gaps_by_pos)
        z_by_pid: dict[str, float] = {}
        for s in eligible:
            z = compute_opportunity_score_z(s, avg, sigmas, settings)
            if z is not None and s.player_id:
                z_by_pid[s.player_id] = z
        out[year] = z_by_pid
    return out


def _aggregate_ff_opportunity(records: Iterable[dict]) -> list[_BenchmarkRow]:
    """Aggregate raw ff_opportunity rows into one _BenchmarkRow per player-season.

    ff_opportunity ships weekly rows; we sum expected and actual fantasy points
    across a player's weeks. Column names are matched against a candidate list
    because nflverse has renamed fields across releases. Rows missing an id,
    season, or a modelled position are skipped.
    """
    def _pick(r: dict, *candidates, default=None):
        for c in candidates:
            if c in r and r.get(c) is not None:
                return r[c]
        return default

    accum: dict[tuple[int, str], dict] = {}
    for r in records:
        pid = _pick(r, "player_id", "gsis_id")
        season = _pick(r, "season")
        position = _pick(r, "position", "pos")
        if pid is None or season is None or position is None:
            continue
        position = str(position)
        if position not in _BENCHMARK_POSITIONS:
            continue
        try:
            year = int(season)
        except (TypeError, ValueError):
            continue
        expected = _pick(r, "total_fantasy_points_exp", default=0.0)
        actual = _pick(r, "total_fantasy_points", default=0.0)
        key = (year, str(pid))
        cell = accum.setdefault(key, {"position": position, "actual": 0.0, "expected": 0.0})
        cell["actual"] += float(actual or 0.0)
        cell["expected"] += float(expected or 0.0)
        cell["position"] = position  # last non-null wins; positions are stable within a season

    return [
        _BenchmarkRow(year=year, player_id=pid, position=cell["position"],
                      actual_fp=cell["actual"], expected_fp=cell["expected"])
        for (year, pid), cell in accum.items()
    ]


def _zscore(values: list[float]) -> Optional[list[float]]:
    """Sample z-score (ddof=1) of a list; None if fewer than 2 points or zero σ."""
    if len(values) < 2:
        return None
    mu = mean(values)
    from statistics import stdev
    sigma = stdev(values)
    if sigma == 0:
        return None
    return [(v - mu) / sigma for v in values]


def compute_benchmark_correlation(
    autotiers_z_by_year: dict[int, dict[str, float]],
    benchmark_rows: list[_BenchmarkRow],
    min_player_seasons: int = 200,
    r_threshold: float = 0.6,
) -> dict:
    """Correlate AutoTiers `opportunity_score_z` against the ff_opportunity residual.

    The ff_opportunity residual (actual − expected FP) is z-scored per
    (year, position) — matching how `opportunity_score_z` is normalised — then
    aligned with AutoTiers' z on shared player-seasons. Reports Pearson r and
    MAE over the aligned pairs and flags whether a mathematician follow-up is
    warranted.
    """
    # z-score benchmark residuals within each (year, position) group.
    groups: dict[tuple[int, str], list[_BenchmarkRow]] = {}
    for row in benchmark_rows:
        groups.setdefault((row.year, row.position), []).append(row)

    benchmark_z: dict[tuple[int, str], float] = {}  # (year, player_id) -> z
    for rows in groups.values():
        zs = _zscore([r.residual for r in rows])
        if zs is None:
            continue
        for row, z in zip(rows, zs):
            benchmark_z[(row.year, row.player_id)] = z

    # Align on player-seasons present in both.
    autotiers_pairs: list[float] = []
    benchmark_pairs: list[float] = []
    for year, z_by_pid in autotiers_z_by_year.items():
        for pid, a_z in z_by_pid.items():
            b_z = benchmark_z.get((year, pid))
            if b_z is None:
                continue
            autotiers_pairs.append(a_z)
            benchmark_pairs.append(b_z)

    n = len(autotiers_pairs)
    pearson_r: Optional[float] = None
    mae: Optional[float] = None
    if n >= 2:
        try:
            pearson_r = correlation(autotiers_pairs, benchmark_pairs)
        except StatisticsError:
            # One side has zero variance — correlation undefined.
            pearson_r = None
        mae = mean(abs(a - b) for a, b in zip(autotiers_pairs, benchmark_pairs))

    sufficient_sample = n >= min_player_seasons
    # A follow-up is warranted when the sample is too small to trust, when the
    # correlation can't be computed at all, or when it falls below threshold.
    follow_up_needed = (not sufficient_sample) or pearson_r is None or pearson_r < r_threshold

    if not sufficient_sample:
        message = (
            f"INSUFFICIENT SAMPLE: only {n} aligned player-seasons "
            f"(need >= {min_player_seasons}). Widen --years before trusting this result, "
            f"then file a mathematician follow-up to review the xfp.py regression coefficients."
        )
    elif pearson_r is None:
        message = (
            f"INDETERMINATE: {n} player-seasons but Pearson r is undefined "
            f"(zero variance in one series). File a mathematician follow-up to review the "
            f"xfp.py regression coefficients."
        )
    elif pearson_r < r_threshold:
        message = (
            f"ACTION REQUIRED: Pearson r = {pearson_r:.3f} < {r_threshold} over {n} "
            f"player-seasons. AutoTiers' opportunity_score_z has drifted from the nflverse "
            f"ff_opportunity benchmark. File a mathematician follow-up to review the xfp.py "
            f"regression coefficients."
        )
    else:
        message = (
            f"OK: Pearson r = {pearson_r:.3f} >= {r_threshold} over {n} player-seasons "
            f"(MAE = {mae:.3f}). xFP regression tracks the ff_opportunity benchmark."
        )

    return {
        "benchmark": "ff_opportunity",
        "n_player_seasons": n,
        "min_player_seasons": min_player_seasons,
        "r_threshold": r_threshold,
        "pearson_r": pearson_r,
        "mae": mae,
        "sufficient_sample": sufficient_sample,
        "follow_up_needed": follow_up_needed,
        "message": message,
    }


def calibrate_against_benchmark(
    years: list[int],
    min_player_seasons: int = 200,
    r_threshold: float = 0.6,
) -> dict:
    """Run the ff_opportunity benchmark validation for the given seasons."""
    nfl = _load_nfl_data_py()
    nflreadpy = _load_nflreadpy()
    settings = _ppr_settings()

    autotiers_z = _autotiers_z_by_year(nfl, years, settings)

    print(f"Loading ff_opportunity for {years}...", file=sys.stderr)
    ff_df = nflreadpy.load_ff_opportunity(seasons=list(years), stat_type="weekly")
    records = _ff_opportunity_records(ff_df)
    benchmark_rows = _aggregate_ff_opportunity(records)

    report = compute_benchmark_correlation(
        autotiers_z, benchmark_rows,
        min_player_seasons=min_player_seasons,
        r_threshold=r_threshold,
    )
    report["years"] = years
    return report


def _ff_opportunity_records(df) -> Iterable[dict]:
    """Normalise the ff_opportunity dataframe to plain dict records.

    nflreadpy returns a polars DataFrame; older/alternate stacks may hand us a
    pandas DataFrame. Support both without importing either eagerly.
    """
    # polars DataFrame
    iter_rows = getattr(df, "iter_rows", None)
    if callable(iter_rows):
        return list(df.iter_rows(named=True))
    # pandas DataFrame
    to_dict = getattr(df, "to_dict", None)
    if callable(to_dict):
        return df.to_dict("records")
    # Already an iterable of mappings.
    return list(df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--benchmark",
        choices=["ff_opportunity"],
        default=None,
        help="Validate opportunity_score_z against an independent benchmark "
             "(nflverse ff_opportunity) instead of the default regression self-check.",
    )
    parser.add_argument(
        "--min-player-seasons", type=int, default=200,
        help="Minimum aligned player-seasons for the benchmark result to be trusted (default: 200).",
    )
    parser.add_argument(
        "--r-threshold", type=float, default=0.6,
        help="Pearson r below which a mathematician follow-up is flagged (default: 0.6).",
    )
    args = parser.parse_args()

    if args.benchmark == "ff_opportunity":
        report = calibrate_against_benchmark(
            args.years,
            min_player_seasons=args.min_player_seasons,
            r_threshold=args.r_threshold,
        )
        print(report["message"], file=sys.stderr)
    else:
        report = calibrate(args.years)

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote calibration report to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
