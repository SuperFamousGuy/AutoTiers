"""Tests for the ff_opportunity benchmark validation in calibrate_xfp_rule.

These cover the pure, data-only layer — aggregation, per-position z-scoring,
Pearson r / MAE, the >= 200 player-season gate, and the r < 0.6 follow-up
message. The nflreadpy data load itself is not exercised here (it needs the
heavy, optional dependency); it's a thin adapter over these tested functions.
"""
import pytest

from scripts.calibrate_xfp_rule import (
    _BenchmarkRow,
    _aggregate_ff_opportunity,
    _ff_opportunity_records,
    _zscore,
    compute_benchmark_correlation,
)


# --- _BenchmarkRow ----------------------------------------------------------

def test_benchmark_row_residual():
    row = _BenchmarkRow(year=2023, player_id="x", position="WR", actual_fp=150.0, expected_fp=120.0)
    assert row.residual == pytest.approx(30.0)


# --- _zscore ----------------------------------------------------------------

def test_zscore_basic():
    zs = _zscore([10.0, -10.0, 0.0])  # mean 0, sample stdev = 10
    assert zs == pytest.approx([1.0, -1.0, 0.0])


def test_zscore_too_few_points():
    assert _zscore([5.0]) is None
    assert _zscore([]) is None


def test_zscore_zero_variance():
    assert _zscore([3.0, 3.0, 3.0]) is None


# --- _aggregate_ff_opportunity ---------------------------------------------

def test_aggregate_sums_weekly_rows_per_player_season():
    records = [
        {"season": 2023, "player_id": "x", "position": "WR",
         "total_fantasy_points": 10.0, "total_fantasy_points_exp": 8.0},
        {"season": 2023, "player_id": "x", "position": "WR",
         "total_fantasy_points": 12.0, "total_fantasy_points_exp": 9.0},
    ]
    rows = _aggregate_ff_opportunity(records)
    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2023
    assert row.player_id == "x"
    assert row.actual_fp == pytest.approx(22.0)
    assert row.expected_fp == pytest.approx(17.0)
    assert row.residual == pytest.approx(5.0)


def test_aggregate_separates_seasons_and_players():
    records = [
        {"season": 2022, "player_id": "a", "position": "RB",
         "total_fantasy_points": 5.0, "total_fantasy_points_exp": 4.0},
        {"season": 2023, "player_id": "a", "position": "RB",
         "total_fantasy_points": 7.0, "total_fantasy_points_exp": 6.0},
        {"season": 2023, "player_id": "b", "position": "TE",
         "total_fantasy_points": 3.0, "total_fantasy_points_exp": 2.0},
    ]
    rows = _aggregate_ff_opportunity(records)
    keyed = {(r.year, r.player_id): r for r in rows}
    assert len(keyed) == 3
    assert keyed[(2022, "a")].position == "RB"
    assert keyed[(2023, "b")].position == "TE"


def test_aggregate_drops_non_modelled_positions_and_bad_rows():
    records = [
        {"season": 2023, "player_id": "k", "position": "K",
         "total_fantasy_points": 9.0, "total_fantasy_points_exp": 9.0},          # K excluded
        {"season": 2023, "player_id": None, "position": "WR",
         "total_fantasy_points": 9.0, "total_fantasy_points_exp": 9.0},          # no id
        {"season": None, "player_id": "z", "position": "WR",
         "total_fantasy_points": 9.0, "total_fantasy_points_exp": 9.0},          # no season
        {"season": 2023, "player_id": "keep", "position": "WR",
         "total_fantasy_points": 9.0, "total_fantasy_points_exp": 9.0},
    ]
    rows = _aggregate_ff_opportunity(records)
    assert [r.player_id for r in rows] == ["keep"]


def test_aggregate_skips_rows_missing_actual_or_expected():
    # Missing FP columns must not fold in a zero residual — the row is skipped.
    records = [
        {"season": 2023, "player_id": "keep", "position": "WR",
         "total_fantasy_points": 9.0, "total_fantasy_points_exp": 7.0},
        {"season": 2023, "player_id": "no_exp", "position": "WR",
         "total_fantasy_points": 9.0},                                   # missing expected
        {"season": 2023, "player_id": "no_act", "position": "WR",
         "total_fantasy_points_exp": 7.0},                               # missing actual
    ]
    rows = _aggregate_ff_opportunity(records)
    assert [r.player_id for r in rows] == ["keep"]


def test_aggregate_skips_only_the_missing_weeks_of_a_player():
    # A player with one good week and one week missing expected keeps the good
    # week's contribution rather than losing the whole player-season.
    records = [
        {"season": 2023, "player_id": "x", "position": "WR",
         "total_fantasy_points": 10.0, "total_fantasy_points_exp": 8.0},
        {"season": 2023, "player_id": "x", "position": "WR",
         "total_fantasy_points": 12.0},                                  # missing expected
    ]
    rows = _aggregate_ff_opportunity(records)
    assert len(rows) == 1
    assert rows[0].actual_fp == pytest.approx(10.0)
    assert rows[0].expected_fp == pytest.approx(8.0)


def test_aggregate_empty_when_fp_columns_absent_entirely():
    # Schema drift: the FP columns are gone for every row -> no rows survive,
    # so downstream reports an empty/insufficient sample instead of all-zeros.
    records = [
        {"season": 2023, "player_id": "a", "position": "WR"},
        {"season": 2023, "player_id": "b", "position": "RB"},
    ]
    assert _aggregate_ff_opportunity(records) == []


def test_aggregate_uses_column_name_fallbacks():
    # nflverse has shipped gsis_id/pos in place of player_id/position.
    records = [
        {"season": 2023, "gsis_id": "g1", "pos": "WR",
         "total_fantasy_points": 4.0, "total_fantasy_points_exp": 3.0},
    ]
    rows = _aggregate_ff_opportunity(records)
    assert len(rows) == 1
    assert rows[0].player_id == "g1"
    assert rows[0].position == "WR"


# --- _ff_opportunity_records ------------------------------------------------

class _FakePolars:
    def __init__(self, records):
        self._records = records

    def iter_rows(self, named=False):
        assert named is True
        return iter(self._records)


class _FakePandas:
    def __init__(self, records):
        self._records = records

    def to_dict(self, orient):
        assert orient == "records"
        return list(self._records)


def test_ff_opportunity_records_handles_polars():
    recs = [{"season": 2023, "player_id": "x"}]
    assert list(_ff_opportunity_records(_FakePolars(recs))) == recs


def test_ff_opportunity_records_handles_pandas():
    recs = [{"season": 2023, "player_id": "x"}]
    assert list(_ff_opportunity_records(_FakePandas(recs))) == recs


# --- compute_benchmark_correlation ------------------------------------------

def _benchmark_rows(year, position, residual_by_pid):
    """Build benchmark rows with a chosen residual (actual set, expected 0)."""
    return [
        _BenchmarkRow(year=year, player_id=pid, position=position,
                      actual_fp=residual, expected_fp=0.0)
        for pid, residual in residual_by_pid.items()
    ]


def test_correlation_ok_when_aligned_and_high_r():
    n = 250
    autotiers = {2023: {str(i): (float(i), "WR") for i in range(n)}}
    rows = _benchmark_rows(2023, "WR", {str(i): float(i) for i in range(n)})
    report = compute_benchmark_correlation(autotiers, rows)
    assert report["n_player_seasons"] == n
    assert report["sufficient_sample"] is True
    assert report["pearson_r"] == pytest.approx(1.0)
    assert report["follow_up_needed"] is False
    assert report["message"].startswith("OK:")


def test_correlation_flags_follow_up_when_r_below_threshold():
    n = 250
    autotiers = {2023: {str(i): (float(i), "WR") for i in range(n)}}
    # Benchmark residual runs opposite to AutoTiers z -> perfect anti-correlation.
    rows = _benchmark_rows(2023, "WR", {str(i): float(-i) for i in range(n)})
    report = compute_benchmark_correlation(autotiers, rows)
    assert report["n_player_seasons"] == n
    assert report["pearson_r"] == pytest.approx(-1.0)
    assert report["follow_up_needed"] is True
    assert "ACTION REQUIRED" in report["message"]
    assert "mathematician" in report["message"]


def test_correlation_flags_insufficient_sample():
    autotiers = {2023: {str(i): (float(i), "WR") for i in range(10)}}
    rows = _benchmark_rows(2023, "WR", {str(i): float(i) for i in range(10)})
    report = compute_benchmark_correlation(autotiers, rows)
    assert report["n_player_seasons"] == 10
    assert report["sufficient_sample"] is False
    assert report["follow_up_needed"] is True
    assert "INSUFFICIENT SAMPLE" in report["message"]


def test_correlation_indeterminate_when_zero_variance():
    n = 250
    # AutoTiers z constant -> Pearson undefined even with a large sample.
    autotiers = {2023: {str(i): (5.0, "WR") for i in range(n)}}
    rows = _benchmark_rows(2023, "WR", {str(i): float(i) for i in range(n)})
    report = compute_benchmark_correlation(autotiers, rows)
    assert report["n_player_seasons"] == n
    assert report["pearson_r"] is None
    assert report["follow_up_needed"] is True
    assert "INDETERMINATE" in report["message"]


def test_correlation_aligns_only_shared_player_seasons():
    autotiers = {2023: {"a": (1.0, "WR"), "b": (2.0, "WR"), "c": (3.0, "WR")}}
    # Benchmark only has a and b (c is unmatched); d is extra and unmatched.
    rows = _benchmark_rows(2023, "WR", {"a": 1.0, "b": 2.0, "d": 4.0})
    report = compute_benchmark_correlation(autotiers, rows, min_player_seasons=2)
    assert report["n_player_seasons"] == 2


def test_correlation_zscore_is_per_position_and_year():
    # Same raw residual magnitude in two positions must not collapse the signal:
    # each group is normalised independently, so a within-group ordering that
    # matches AutoTiers still yields positive correlation.
    autotiers = {2023: {"w1": (0.0, "WR"), "w2": (1.0, "WR"),
                        "r1": (0.0, "RB"), "r2": (1.0, "RB")}}
    rows = (
        _benchmark_rows(2023, "WR", {"w1": 10.0, "w2": 20.0})
        + _benchmark_rows(2023, "RB", {"r1": 100.0, "r2": 200.0})
    )
    report = compute_benchmark_correlation(autotiers, rows, min_player_seasons=2)
    assert report["n_player_seasons"] == 4
    # Both groups z-score to [-1, +1] aligned with AutoTiers -> r = 1.0.
    assert report["pearson_r"] == pytest.approx(1.0)


def test_correlation_skips_group_with_single_member():
    # A (year, position) group of one can't be z-scored -> that player-season
    # is dropped from the aligned set.
    autotiers = {2023: {"solo": (1.0, "QB"), "a": (2.0, "WR"), "b": (3.0, "WR")}}
    rows = (
        _benchmark_rows(2023, "QB", {"solo": 5.0})  # lone QB -> no z
        + _benchmark_rows(2023, "WR", {"a": 2.0, "b": 3.0})
    )
    report = compute_benchmark_correlation(autotiers, rows, min_player_seasons=2)
    assert report["n_player_seasons"] == 2  # only the two WRs align


def test_correlation_does_not_cross_match_positions():
    # Same player_id and year, but the position label disagrees between the two
    # sources. Aligning on (year, player_id, position) must drop the pair rather
    # than compare z-scores from different normalisation groups.
    autotiers = {2023: {"a": (1.0, "WR"), "b": (2.0, "WR"), "x": (3.0, "RB")}}
    rows = (
        _benchmark_rows(2023, "WR", {"a": 1.0, "b": 2.0})
        + _benchmark_rows(2023, "TE", {"x": 5.0, "y": 6.0})  # x is RB in AutoTiers
    )
    report = compute_benchmark_correlation(autotiers, rows, min_player_seasons=2)
    assert report["n_player_seasons"] == 2  # only the two WRs align; x is dropped
