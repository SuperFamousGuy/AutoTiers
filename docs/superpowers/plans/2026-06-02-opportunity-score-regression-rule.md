# Opportunity Score Regression Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new builtin rules ("Opportunity Over-Producer" / "Opportunity Under-Producer") that detect players whose prior-season fantasy production diverged materially from their opportunity-implied expectation, and adjust `adjusted_score` toward the mean.

**Architecture:** Compute league averages of fantasy points per opportunity unit (target / carry / red-zone look), per position, in a single pre-pass over players. Use those to compute each player's xFP and the z-score of their `(actual_FP − xFP)` gap against the position's σ_gap. Surface the z-score as a new `PlayerContext` field; two new `Rule` entries fire off threshold comparisons against it.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, FastAPI, pytest, numpy, dataclasses. No new dependencies. No DB migration. All input columns already exist in `app/models/player.PlayerStat`.

**Spec:** [`docs/superpowers/specs/2026-06-02-opportunity-score-regression-rule-design.md`](../specs/2026-06-02-opportunity-score-regression-rule-design.md) — the math contract. Treat any disagreement between this plan and the spec as a bug in this plan; the spec wins.

---

## Pre-flight — read these files first (15 minutes)

The engineer should `Read` these in order before touching code:

1. `docs/superpowers/specs/2026-06-02-opportunity-score-regression-rule-design.md` — the math.
2. `backend/app/engine/scoring.py` — `LeagueSettings`, `PlayerStats`, `calculate_fantasy_points`. The function we'll need to factor.
3. `backend/app/engine/rules.py` — `PlayerContext`, `Rule`, `RuleCondition`, `RuleEffect`, `apply_rules`.
4. `backend/app/engine/builtin_rules.py` — existing rule entries, especially `TD Regression` (lines 72–76) and `Red Zone Usage Premium` (lines 78–82). The new rules follow this exact pattern.
5. `backend/app/api/generate.py` — `_run_generate()` (line 151) and the `PlayerContext(...)` construction (lines 271–298). The wire-up site.
6. `backend/tests/test_rules.py` — existing tests for TD Regression (lines 193–203). The new tests mirror this style.
7. `.claude/skills/autotiers-test-running/SKILL.md` — exact venv path + warnings to ignore. Read once.

## File map (decomposition decisions)

**Create:**
- `backend/app/engine/xfp.py` — pure-math module: league-average computation, xFP per player, per-position σ_gap, z-score helper. No DB access, no FastAPI dependency. Unit-testable in isolation.
- `backend/tests/test_xfp.py` — unit tests for `xfp.py`'s math.
- `backend/tests/test_xfp_rule.py` — unit tests for the two new builtin rules and their `PlayerContext` integration. Mirrors `test_rules.py` style.
- `backend/scripts/calibrate_xfp_rule.py` — calibration script, runs against historical `nfl_data_py` seasons. Not CI-gated; outputs a JSON report.

**Modify:**
- `backend/app/engine/scoring.py` — factor `calculate_fantasy_points` into private component helpers (`_score_receiving`, `_score_rushing`, `_score_tds_only`). The public function keeps its signature and behavior.
- `backend/app/engine/rules.py` — add `opportunity_score_z: Optional[float] = None` to `PlayerContext`.
- `backend/app/engine/builtin_rules.py` — append two new `Rule` entries.
- `backend/app/api/generate.py` — call `xfp.compute_league_averages` + `xfp.compute_per_position_sigmas` once before the player loop; per-player call `xfp.compute_opportunity_score_z` and pass it into the `PlayerContext` constructor.
- `backend/tests/test_rules.py` — extend the `make_ctx` helper to accept the new field (it uses `**defaults`; just need to add `opportunity_score_z=None` to the defaults dicts at lines 16 and 29 so old tests still construct cleanly).

**Don't touch (yet):**
- Frontend. The new rules will appear in the rule list automatically because the rule-config endpoint reads `BUILTIN_RULES` at request time. A separate follow-up can group them in `RuleCategory` and surface z as a player flag. Note this as out-of-scope in the PR description.

## Decomposition rationale

- `xfp.py` is **pure math, no I/O**. We can test it without any DB, async, or fixture machinery. This is the cheapest place to make math correct.
- The scoring component factoring stays in `scoring.py` because `_score_receiving` etc. are logically scoring-engine concerns. Moving them would pollute the boundaries.
- The wire-up in `generate.py` is the only async/SQLAlchemy-aware code — kept small.
- Calibration script lives under `backend/scripts/` (not `backend/tests/`) because it's a one-shot human-run tool, not a CI artifact.

---

## Task 1: Factor scoring components

Goal: split `calculate_fantasy_points` so we can compute the receiving / rushing / TD subcomponents separately for league averages, without changing the public function's behavior.

**Files:**
- Modify: `backend/app/engine/scoring.py:48-77` (the `calculate_fantasy_points` body)
- Test: `backend/tests/test_scoring.py` (add tests; file already exists)

- [ ] **Step 1.1: Write failing tests for the new helpers**

Add to `backend/tests/test_scoring.py` (append at the end):

```python
from app.engine.scoring import (
    PlayerStats, LeagueSettings, ScoringFormat, LeagueType,
    _score_receiving, _score_rushing, _score_tds_only, calculate_fantasy_points,
)


def _ppr_settings() -> LeagueSettings:
    return LeagueSettings(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.2,
        weight_espn=0.4,
        weight_consensus=0.4,
    )


def _empty_stats() -> PlayerStats:
    return PlayerStats(
        targets=0, receptions=0, rec_yards=0.0, rec_tds=0,
        rush_att=0, rush_yards=0.0, rush_tds=0,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
        games_played=1,
    )


def test_score_receiving_excludes_tds():
    s = _empty_stats()
    s.receptions = 50
    s.rec_yards = 600.0
    s.rec_tds = 5
    # Expect: 50 PPR pts + 60 yards pts; TDs excluded here.
    assert _score_receiving(s, _ppr_settings()) == 110.0


def test_score_rushing_excludes_tds():
    s = _empty_stats()
    s.rush_att = 200
    s.rush_yards = 1000.0
    s.rush_tds = 8
    # Expect: 100 yards pts; TDs excluded; carries don't score directly.
    assert _score_rushing(s, _ppr_settings()) == 100.0


def test_score_tds_only_sums_rec_and_rush():
    s = _empty_stats()
    s.rec_tds = 4
    s.rush_tds = 6
    # Expect: 10 TDs × 6 = 60.
    assert _score_tds_only(s, _ppr_settings()) == 60.0


def test_calculate_fantasy_points_unchanged():
    """Regression: factoring must not change calculate_fantasy_points output."""
    s = _empty_stats()
    s.receptions = 50
    s.rec_yards = 600.0
    s.rec_tds = 5
    s.rush_att = 200
    s.rush_yards = 1000.0
    s.rush_tds = 8
    # 50 + 60 (rec yds + rec) + 30 (5 rec TDs) + 100 (rush yds) + 48 (8 rush TDs) = 288
    assert calculate_fantasy_points(s, _ppr_settings(), position="RB") == 288.0
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_scoring.py -k "score_receiving or score_rushing or score_tds_only or calculate_fantasy_points_unchanged" -v
```

Expected: 4 fails (`_score_receiving / _score_rushing / _score_tds_only` not defined; `calculate_fantasy_points_unchanged` passes). 3 of 4 fail with `ImportError` on the helpers; the regression test passes (proves the baseline).

- [ ] **Step 1.3: Implement the helpers and refactor `calculate_fantasy_points`**

Replace `calculate_fantasy_points` in `backend/app/engine/scoring.py` (currently lines 48–77) with this:

```python
def _score_receiving(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Receiving points EXCLUDING TDs (yards + reception bonus + 100yd bonus)."""
    if settings.scoring_format == ScoringFormat.PPR:
        rec_pts = 1.0
    elif settings.scoring_format == ScoringFormat.HALF_PPR:
        rec_pts = 0.5
    else:
        rec_pts = 0.0
    pts = stats.receptions * rec_pts + stats.rec_yards * 0.1
    if settings.bonus_100yd_receiving and stats.rec_yards >= 100:
        pts += 3.0
    return pts


def _score_rushing(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Rushing points EXCLUDING TDs (yards + 100yd bonus)."""
    pts = stats.rush_yards * 0.1
    if settings.bonus_100yd_rushing and stats.rush_yards >= 100:
        pts += 3.0
    return pts


def _score_tds_only(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Total TD points (rushing + receiving). Passing TDs excluded — those are QB-only."""
    return (stats.rec_tds + stats.rush_tds) * 6.0


def _score_passing(stats: PlayerStats, settings: LeagueSettings) -> float:
    """Passing points (QB-only). Includes pass yards, pass TDs, INTs."""
    return (
        stats.pass_yards * 0.04
        + stats.pass_tds * settings.qb_td_points
        - stats.interceptions * 2.0
    )


def calculate_fantasy_points(stats: PlayerStats, settings: LeagueSettings, position: str = "") -> float:
    """Total fantasy points across all categories. Behavior unchanged — this is now a sum of the component helpers."""
    pts = (
        _score_passing(stats, settings)
        + _score_rushing(stats, settings)
        + _score_tds_only(stats, settings)
        + _score_receiving(stats, settings)
    )
    return round(pts, 2)
```

- [ ] **Step 1.4: Run all scoring tests to verify nothing regressed**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_scoring.py -v
```

Expected: all pass, including the 4 new ones and every pre-existing scoring test. If any pre-existing test fails, the factoring changed a numeric output — go back and reconcile rather than updating the test.

- [ ] **Step 1.5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/engine/scoring.py backend/tests/test_scoring.py
git commit -m "refactor(scoring): factor calculate_fantasy_points into component helpers

Pure refactor — total points unchanged. Splits into _score_receiving,
_score_rushing, _score_tds_only, _score_passing so the xFP module can
sum opportunity-relevant components separately when computing league
averages.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: xfp.py — pure-math module

Goal: implement league-average computation, xFP per player, σ_gap per position, and z-score in one I/O-free module. This is where the spec's math lives.

**Files:**
- Create: `backend/app/engine/xfp.py`
- Test: `backend/tests/test_xfp.py`

- [ ] **Step 2.1: Write the failing tests**

Create `backend/tests/test_xfp.py`:

```python
"""Unit tests for the xFP regression math.

These tests cover the pure-math layer — no DB, no async. The integration
into PlayerContext / the rule engine lives in test_xfp_rule.py.
"""
import pytest
from app.engine.scoring import LeagueSettings, LeagueType, ScoringFormat
from app.engine.xfp import (
    LeagueAverages,
    compute_league_averages,
    compute_xfp,
    compute_per_position_sigmas,
    compute_opportunity_score_z,
)


def _ppr_settings() -> LeagueSettings:
    return LeagueSettings(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=0.2,
        weight_espn=0.4,
        weight_consensus=0.4,
    )


# Minimal "stat-like" object the xfp module needs. We use a dataclass / dict
# so tests don't need an ORM session. The real call site passes
# app.models.player.PlayerStat instances; both must satisfy the same
# attribute-access protocol.
from dataclasses import dataclass


@dataclass
class _StubStat:
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
    pass_att: int = 0
    pass_yards: float = 0.0
    pass_tds: int = 0
    interceptions: int = 0


def test_league_averages_basic_two_wrs():
    """Two WRs, hand-computed averages."""
    stats = [
        _StubStat(position="WR", targets=100, receptions=70, rec_yards=900, rec_tds=6,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=15, games_played=16),
        _StubStat(position="WR", targets=80, receptions=55, rec_yards=700, rec_tds=4,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16),
    ]
    avg = compute_league_averages(stats, _ppr_settings())
    # rec pts (PPR, no bonus): WR1 = 70 + 90 = 160; WR2 = 55 + 70 = 125 → total 285.
    # total targets = 180 → pts/target = 285 / 180 = 1.5833...
    assert avg.pts_per_target["WR"] == pytest.approx(285.0 / 180.0)
    # rush pts: 0 / 0 → defined as 0.0 by guard
    assert avg.pts_per_carry.get("WR", 0.0) == 0.0
    # td pts: (6 + 4) × 6 = 60; rz looks = 25 → 60 / 25 = 2.4
    assert avg.pts_per_rz_look["WR"] == pytest.approx(2.4)


def test_league_averages_skips_low_games_played():
    """Players with games_played < 8 are excluded from averages (small-sample noise)."""
    stats = [
        _StubStat(position="WR", targets=100, receptions=70, rec_yards=900, rec_tds=6,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=15, games_played=16),
        # This injury-shortened season should NOT contribute to averages.
        _StubStat(position="WR", targets=10, receptions=8, rec_yards=120, rec_tds=2,
                  rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=3, games_played=3),
    ]
    avg = compute_league_averages(stats, _ppr_settings())
    # rec pts: 70 + 90 = 160; targets = 100; pts/target = 1.6
    assert avg.pts_per_target["WR"] == pytest.approx(1.6)


def test_compute_xfp_combines_target_carry_rzlook():
    """xFP = targets × pts/target + rush_att × pts/carry + rz_looks × pts/rzlook."""
    avg = LeagueAverages(
        pts_per_target={"WR": 1.5},
        pts_per_carry={"WR": 0.0},
        pts_per_rz_look={"WR": 2.0},
    )
    stat = _StubStat(position="WR", targets=80, receptions=50, rec_yards=600, rec_tds=4,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16)
    # xFP = 80 × 1.5 + 0 × 0 + 10 × 2 = 140.
    assert compute_xfp(stat, avg) == pytest.approx(140.0)


def test_compute_xfp_returns_none_for_unsupported_position():
    """K and DST never have target/carry/rz_looks; we can't compute xFP for them."""
    avg = LeagueAverages(pts_per_target={}, pts_per_carry={}, pts_per_rz_look={})
    stat = _StubStat(position="K", targets=0, receptions=0, rec_yards=0, rec_tds=0,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=0, games_played=16)
    assert compute_xfp(stat, avg) is None


def test_per_position_sigmas_uses_sample_stdev():
    """σ_gap is sample stdev (ddof=1), per position."""
    # Construct two WRs whose (FP − xFP) gap differs.
    # We'll feed gaps directly via _StubStat values that resolve to the right gaps.
    # Simpler: test the helper with a known gap dict directly.
    gaps_by_position = {"WR": [10.0, -10.0, 0.0]}  # mean 0, sample stdev = sqrt(200/2) ≈ 10
    sigmas = compute_per_position_sigmas(gaps_by_position)
    assert sigmas["WR"] == pytest.approx(10.0)


def test_per_position_sigmas_handles_too_few_samples():
    """Position with fewer than 2 samples → sigma undefined → entry omitted."""
    gaps_by_position = {"QB": [5.0]}  # only one sample
    sigmas = compute_per_position_sigmas(gaps_by_position)
    assert "QB" not in sigmas


def test_opportunity_score_z_basic():
    """z = (FP − xFP) / σ. Hand-checked."""
    avg = LeagueAverages(
        pts_per_target={"WR": 1.5},
        pts_per_carry={"WR": 0.0},
        pts_per_rz_look={"WR": 2.0},
    )
    sigmas = {"WR": 10.0}
    settings = _ppr_settings()
    # Stat: 80 targets, 50 rec, 600 yds, 4 rec_tds, 10 rz_looks
    # FP (rec yds + rec): 50 + 60 = 110; TDs: 4 × 6 = 24; total FP = 134.
    # xFP = 80 × 1.5 + 0 + 10 × 2 = 140.
    # gap = 134 − 140 = −6. z = −6 / 10 = −0.6.
    stat = _StubStat(position="WR", targets=80, receptions=50, rec_yards=600, rec_tds=4,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16)
    z = compute_opportunity_score_z(stat, avg, sigmas, settings)
    assert z == pytest.approx(-0.6)


def test_opportunity_score_z_returns_none_for_low_games_played():
    avg = LeagueAverages(pts_per_target={"WR": 1.5}, pts_per_carry={"WR": 0.0}, pts_per_rz_look={"WR": 2.0})
    sigmas = {"WR": 10.0}
    settings = _ppr_settings()
    stat = _StubStat(position="WR", targets=20, receptions=10, rec_yards=120, rec_tds=1,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=2, games_played=5)
    assert compute_opportunity_score_z(stat, avg, sigmas, settings) is None


def test_opportunity_score_z_returns_none_for_zero_opportunity():
    """A player with 0 targets + 0 carries + 0 rz_looks is not in the regression distribution."""
    avg = LeagueAverages(pts_per_target={"WR": 1.5}, pts_per_carry={"WR": 0.0}, pts_per_rz_look={"WR": 2.0})
    sigmas = {"WR": 10.0}
    settings = _ppr_settings()
    stat = _StubStat(position="WR", targets=0, receptions=0, rec_yards=0, rec_tds=0,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=0, games_played=16)
    assert compute_opportunity_score_z(stat, avg, sigmas, settings) is None


def test_opportunity_score_z_returns_none_when_sigma_missing():
    """If the position lacks enough samples for σ, we can't compute z."""
    avg = LeagueAverages(pts_per_target={"WR": 1.5}, pts_per_carry={"WR": 0.0}, pts_per_rz_look={"WR": 2.0})
    sigmas = {}  # no WR σ
    settings = _ppr_settings()
    stat = _StubStat(position="WR", targets=80, receptions=50, rec_yards=600, rec_tds=4,
                     rush_att=0, rush_yards=0, rush_tds=0, red_zone_looks=10, games_played=16)
    assert compute_opportunity_score_z(stat, avg, sigmas, settings) is None
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_xfp.py -v
```

Expected: all 10 tests fail with `ModuleNotFoundError: No module named 'app.engine.xfp'`. (We haven't written it yet.)

- [ ] **Step 2.3: Implement `xfp.py`**

Create `backend/app/engine/xfp.py`:

```python
"""Opportunity-score (xFP) regression math.

Implements the spec at docs/superpowers/specs/2026-06-02-opportunity-score-regression-rule-design.md.

This module is pure math — no DB access, no FastAPI dependency, no async.
Callers (currently app.api.generate) pass in iterables of stat-like objects
that have the standard PlayerStat attribute names (targets, receptions,
rec_yards, rec_tds, rush_att, rush_yards, rush_tds, red_zone_looks,
games_played, position).
"""
from dataclasses import dataclass, field
from statistics import stdev
from typing import Optional, Protocol

from app.engine.scoring import (
    LeagueSettings,
    PlayerStats,
    _score_receiving,
    _score_rushing,
    _score_tds_only,
)


# Position-aware minimum total opportunity to be eligible for the rule.
# Players with fewer targets+carries+rz_looks than this are excluded
# (they're not in the regression distribution at all).
_MIN_OPPORTUNITY_BY_POSITION = {
    "WR": 50,
    "RB": 50,
    "TE": 20,
    "QB": 50,  # QBs can have rush opportunity; targets/rec_tds are usually 0
}

# Minimum games_played to contribute to league averages OR have z computed.
# Below this, the season is too injury-truncated to be a clean signal.
_MIN_GAMES_PLAYED = 8

# Positions for which we compute opportunity-score regression. K and DST
# excluded — they don't have target/carry/rz_look inputs.
_REGRESSION_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


class _StatLike(Protocol):
    """The attribute surface compute_*  needs. Both ORM PlayerStat and test stubs match."""
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
    pass_att: int
    pass_yards: float
    pass_tds: int
    interceptions: int


@dataclass(frozen=True)
class LeagueAverages:
    """Per-position averages of fantasy points per opportunity unit."""
    pts_per_target: dict[str, float] = field(default_factory=dict)
    pts_per_carry: dict[str, float] = field(default_factory=dict)
    pts_per_rz_look: dict[str, float] = field(default_factory=dict)


def _to_player_stats(s: _StatLike) -> PlayerStats:
    """Adapt a stat-like object to the scoring engine's PlayerStats dataclass."""
    return PlayerStats(
        targets=s.targets or 0,
        receptions=s.receptions or 0,
        rec_yards=s.rec_yards or 0.0,
        rec_tds=s.rec_tds or 0,
        rush_att=s.rush_att or 0,
        rush_yards=s.rush_yards or 0.0,
        rush_tds=s.rush_tds or 0,
        pass_att=s.pass_att or 0,
        pass_yards=s.pass_yards or 0.0,
        pass_tds=s.pass_tds or 0,
        interceptions=s.interceptions or 0,
        games_played=s.games_played or 1,
    )


def compute_league_averages(
    stats: list[_StatLike], settings: LeagueSettings
) -> LeagueAverages:
    """Compute per-position league averages of pts/target, pts/carry, pts/rz_look.

    Only stats with games_played >= _MIN_GAMES_PLAYED contribute. Positions
    with zero denominator for a metric get 0.0 (the metric won't fire for
    that position; xFP will skip it).
    """
    # Aggregate sums per position.
    targets_sum: dict[str, int] = {}
    rec_pts_sum: dict[str, float] = {}
    carries_sum: dict[str, int] = {}
    rush_pts_sum: dict[str, float] = {}
    rz_looks_sum: dict[str, int] = {}
    td_pts_sum: dict[str, float] = {}

    for s in stats:
        if (s.games_played or 0) < _MIN_GAMES_PLAYED:
            continue
        if s.position not in _REGRESSION_POSITIONS:
            continue
        ps = _to_player_stats(s)
        pos = s.position
        targets_sum[pos] = targets_sum.get(pos, 0) + ps.targets
        rec_pts_sum[pos] = rec_pts_sum.get(pos, 0.0) + _score_receiving(ps, settings)
        carries_sum[pos] = carries_sum.get(pos, 0) + ps.rush_att
        rush_pts_sum[pos] = rush_pts_sum.get(pos, 0.0) + _score_rushing(ps, settings)
        rz_looks_sum[pos] = rz_looks_sum.get(pos, 0) + (s.red_zone_looks or 0)
        td_pts_sum[pos] = td_pts_sum.get(pos, 0.0) + _score_tds_only(ps, settings)

    def _safe_div(num: float, den: float) -> float:
        return num / den if den > 0 else 0.0

    return LeagueAverages(
        pts_per_target={pos: _safe_div(rec_pts_sum.get(pos, 0.0), targets_sum.get(pos, 0)) for pos in targets_sum},
        pts_per_carry={pos: _safe_div(rush_pts_sum.get(pos, 0.0), carries_sum.get(pos, 0)) for pos in carries_sum},
        pts_per_rz_look={pos: _safe_div(td_pts_sum.get(pos, 0.0), rz_looks_sum.get(pos, 0)) for pos in rz_looks_sum},
    )


def compute_xfp(stat: _StatLike, averages: LeagueAverages) -> Optional[float]:
    """Opportunity-implied fantasy points for one player.

    Returns None for positions we don't model (K, DST) or when no league
    averages exist for the player's position.
    """
    pos = stat.position
    if pos not in _REGRESSION_POSITIONS:
        return None
    pt = averages.pts_per_target.get(pos)
    pc = averages.pts_per_carry.get(pos)
    pr = averages.pts_per_rz_look.get(pos)
    if pt is None and pc is None and pr is None:
        return None
    targets = stat.targets or 0
    carries = stat.rush_att or 0
    rz = stat.red_zone_looks or 0
    return (
        targets * (pt or 0.0)
        + carries * (pc or 0.0)
        + rz * (pr or 0.0)
    )


def compute_per_position_sigmas(gaps_by_position: dict[str, list[float]]) -> dict[str, float]:
    """Sample standard deviation (ddof=1) of FP − xFP gaps, per position.

    Positions with fewer than 2 gap samples are omitted — sample stdev is
    undefined on a single point.
    """
    out: dict[str, float] = {}
    for pos, gaps in gaps_by_position.items():
        if len(gaps) >= 2:
            out[pos] = stdev(gaps)
    return out


def compute_opportunity_score_z(
    stat: _StatLike,
    averages: LeagueAverages,
    sigmas: dict[str, float],
    settings: LeagueSettings,
) -> Optional[float]:
    """Z-score of this player's (actual FP − xFP) gap against position σ_gap.

    Returns None when any of:
    - position is not in _REGRESSION_POSITIONS (K, DST)
    - games_played < _MIN_GAMES_PLAYED (small-sample)
    - total opportunity (targets + carries + rz_looks) below the position threshold
    - no σ for the position (too few players to estimate)
    - xFP cannot be computed (no averages for position)
    """
    pos = stat.position
    if pos not in _REGRESSION_POSITIONS:
        return None
    if (stat.games_played or 0) < _MIN_GAMES_PLAYED:
        return None
    opportunity = (stat.targets or 0) + (stat.rush_att or 0) + (stat.red_zone_looks or 0)
    if opportunity < _MIN_OPPORTUNITY_BY_POSITION.get(pos, 50):
        return None
    sigma = sigmas.get(pos)
    if sigma is None or sigma == 0:
        return None
    xfp = compute_xfp(stat, averages)
    if xfp is None:
        return None
    ps = _to_player_stats(stat)
    fp = (
        _score_receiving(ps, settings)
        + _score_rushing(ps, settings)
        + _score_tds_only(ps, settings)
        # Passing intentionally excluded: xFP doesn't model passing
        # opportunity (we'd need pass_att, pass_attempts under pressure,
        # etc.). Keeping FP comparable means dropping passing here too.
    )
    return (fp - xfp) / sigma
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_xfp.py -v
```

Expected: 10 passes, 0 fails.

- [ ] **Step 2.5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/engine/xfp.py backend/tests/test_xfp.py
git commit -m "feat(engine): xfp module — league averages + per-player z-score

Pure-math module implementing the opportunity-score regression math
from the spec. No I/O, no async, no SQLAlchemy. Helpers:

- compute_league_averages: per-position pts/target, pts/carry, pts/rz_look.
- compute_xfp: opportunity-implied FP for one player.
- compute_per_position_sigmas: sample stdev of (FP - xFP) gaps.
- compute_opportunity_score_z: signed z-score; None on degenerate inputs.

Edge cases tested: low games_played, zero opportunity, missing σ,
unsupported position (K/DST), per-position sample-size threshold.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: PlayerContext field + extend existing test helpers

Goal: add `opportunity_score_z` to `PlayerContext` and update the test fixtures so existing tests keep constructing it cleanly.

**Files:**
- Modify: `backend/app/engine/rules.py` (the `PlayerContext` dataclass at lines ~38–60)
- Modify: `backend/tests/test_rules.py` (the `make_ctx` defaults at lines 16 and 29)

- [ ] **Step 3.1: Add the field to `PlayerContext`**

Open `backend/app/engine/rules.py`. Find the `PlayerContext` dataclass (around line 38). Add this field at the end of the dataclass — right after `above_market_contract: Optional[bool] = None`:

```python
    opportunity_score_z: Optional[float] = None
```

- [ ] **Step 3.2: Update the test fixture defaults**

Open `backend/tests/test_rules.py`. Find the two `defaults` dicts (lines around 16 and 29 — they're inside `make_ctx`-style helpers). Add `opportunity_score_z=None` to each defaults dict, alongside the other `Optional` fields.

Concretely, the first helper currently looks like:

```python
defaults = dict(
    player_id="p", position="WR", age=25, snap_pct=0.7, ...
    actual_tds_above_expected=None, red_zone_looks=None,
    is_over_the_hill=None, projection_unavailable=None,
    prior_touches=None, injured_two_years_ago=None,
    bad_offense_team=None, above_market_contract=None,
)
```

Add `opportunity_score_z=None,` at the end of the defaults block (both occurrences).

- [ ] **Step 3.3: Run all existing rule tests to verify nothing regressed**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_rules.py -v
```

Expected: all pre-existing tests pass. If any fail, the field addition broke an unrelated test — likely a `dataclasses.asdict` or similar — investigate before continuing.

- [ ] **Step 3.4: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/engine/rules.py backend/tests/test_rules.py
git commit -m "feat(rules): add opportunity_score_z field to PlayerContext

Plumbing for the upcoming Opportunity Over-Producer / Under-Producer
rules. Optional field, default None (engine ignores rules whose
condition field is None).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Two new builtin rules + their tests

Goal: add the two new entries to `BUILTIN_RULES` and lock their behavior with unit tests that mirror the existing TD Regression tests.

**Files:**
- Modify: `backend/app/engine/builtin_rules.py` (append two new `Rule` entries)
- Create: `backend/tests/test_xfp_rule.py`

- [ ] **Step 4.1: Write the failing tests**

Create `backend/tests/test_xfp_rule.py`:

```python
"""Tests for the Opportunity Over-Producer / Under-Producer rules.

Mirrors the style of test_rules.py's TD Regression coverage (lines
~193-203). We make a PlayerContext directly and run apply_rules.
"""
import pytest
from app.engine.rules import (
    PlayerContext, apply_rules, EffectType, RuleCondition, RuleEffect, Rule,
)
from app.engine.builtin_rules import BUILTIN_RULES


def make_ctx(**overrides) -> PlayerContext:
    """Construct a minimal PlayerContext with sane defaults for these tests."""
    defaults = dict(
        player_id="p", position="WR", age=25, snap_pct=0.7,
        carry_share=None, target_share=0.20, games_played=16,
        years_exp=4, adp=50.0, projected_score=180.0,
        new_team=False, new_coach=False,
        actual_tds=None, expected_tds=None, actual_tds_above_expected=None,
        red_zone_looks=None, is_over_the_hill=None,
        projection_unavailable=None, prior_touches=None,
        injured_two_years_ago=None, bad_offense_team=None,
        above_market_contract=None, opportunity_score_z=None,
    )
    defaults.update(overrides)
    return PlayerContext(**defaults)


def _over_producer_rule() -> Rule:
    """Locate the over-producer rule from BUILTIN_RULES."""
    return next(r for r in BUILTIN_RULES if r.name == "Opportunity Over-Producer")


def _under_producer_rule() -> Rule:
    return next(r for r in BUILTIN_RULES if r.name == "Opportunity Under-Producer")


def test_over_producer_fires_at_threshold():
    rule = _over_producer_rule()
    ctx = make_ctx(opportunity_score_z=1.5)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    # z = 1.5 → fires → -8%. 180 × 0.92 = 165.6
    assert result.adjusted_score == pytest.approx(165.6, abs=0.01)
    assert "Opportunity Over-Producer" in result.rules_applied


def test_over_producer_does_not_fire_below_threshold():
    rule = _over_producer_rule()
    ctx = make_ctx(opportunity_score_z=1.49)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Over-Producer" not in result.rules_applied


def test_over_producer_does_not_fire_when_z_is_none():
    rule = _over_producer_rule()
    ctx = make_ctx(opportunity_score_z=None)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Over-Producer" not in result.rules_applied


def test_under_producer_fires_at_negative_threshold():
    rule = _under_producer_rule()
    ctx = make_ctx(opportunity_score_z=-1.5)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    # z = -1.5 → fires → +8%. 180 × 1.08 = 194.4
    assert result.adjusted_score == pytest.approx(194.4, abs=0.01)
    assert "Opportunity Under-Producer" in result.rules_applied


def test_under_producer_does_not_fire_above_negative_threshold():
    rule = _under_producer_rule()
    ctx = make_ctx(opportunity_score_z=-1.49)
    result = apply_rules(ctx.projected_score, ctx, [rule])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Under-Producer" not in result.rules_applied


def test_neither_rule_fires_at_zero():
    over = _over_producer_rule()
    under = _under_producer_rule()
    ctx = make_ctx(opportunity_score_z=0.0)
    result = apply_rules(ctx.projected_score, ctx, [over, under])
    assert result.adjusted_score == pytest.approx(180.0)
    assert "Opportunity Over-Producer" not in result.rules_applied
    assert "Opportunity Under-Producer" not in result.rules_applied


def test_only_one_direction_fires_at_a_time():
    """The two rules are mutually exclusive by threshold construction."""
    over = _over_producer_rule()
    under = _under_producer_rule()
    # Strongly positive z
    ctx_pos = make_ctx(opportunity_score_z=2.5)
    result_pos = apply_rules(ctx_pos.projected_score, ctx_pos, [over, under])
    assert "Opportunity Over-Producer" in result_pos.rules_applied
    assert "Opportunity Under-Producer" not in result_pos.rules_applied
    # Strongly negative z
    ctx_neg = make_ctx(opportunity_score_z=-2.5)
    result_neg = apply_rules(ctx_neg.projected_score, ctx_neg, [over, under])
    assert "Opportunity Under-Producer" in result_neg.rules_applied
    assert "Opportunity Over-Producer" not in result_neg.rules_applied
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_xfp_rule.py -v
```

Expected: 7 fails. The failures should be `StopIteration` from `next(...)` because the new rules don't exist in `BUILTIN_RULES` yet.

- [ ] **Step 4.3: Add the two rule entries**

Open `backend/app/engine/builtin_rules.py`. Find the existing `TD Regression` rule (around line 72). Append two new entries to the `BUILTIN_RULES` list. Suggested placement: right after `TD Regression`, since they're thematically adjacent. Insert this block:

```python
    Rule(
        name="Opportunity Over-Producer",
        conditions=[RuleCondition(field="opportunity_score_z", operator=">=", value=1.5)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.92),
        description=(
            "Penalizes players who scored 1.5+ standard deviations above their "
            "target/carry/red-zone opportunity last season — strong regression "
            "candidate. -8% at default weight."
        ),
    ),
    Rule(
        name="Opportunity Under-Producer",
        conditions=[RuleCondition(field="opportunity_score_z", operator="<=", value=-1.5)],
        effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.08),
        description=(
            "Boosts players who scored 1.5+ standard deviations below their "
            "target/carry/red-zone opportunity last season — positive regression "
            "candidate. +8% at default weight."
        ),
    ),
```

- [ ] **Step 4.4: Run rule tests to verify they pass**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_xfp_rule.py tests/test_rules.py -v
```

Expected: 7 new tests pass; all existing `test_rules.py` tests still pass.

- [ ] **Step 4.5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/engine/builtin_rules.py backend/tests/test_xfp_rule.py
git commit -m "feat(rules): add Opportunity Over-Producer and Under-Producer rules

Two new builtin rules off opportunity_score_z:
- Over-Producer: z >= 1.5 → MULTIPLIER 0.92 (-8%)
- Under-Producer: z <= -1.5 → MULTIPLIER 1.08 (+8%)

Split into two so users can toggle each direction independently — the
over-producer penalty is uncontroversial, the under-producer boost is
more contested (could be a true talent floor, not pure regression).

Tests cover: threshold inclusivity, None handling, mutual exclusion of
the two rules, all-zero baseline.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Wire xFP into `generate.py`

Goal: compute league averages once per request, populate the new `PlayerContext` field, and confirm the rules fire end-to-end via an integration test.

**Files:**
- Modify: `backend/app/api/generate.py` — add the league-averages + per-player z-score computation around line 200 (just before the `for player in players` loop) and pass `opportunity_score_z` into `PlayerContext(...)` at line 271.
- Create: `backend/tests/test_xfp_integration.py` — a focused integration test that feeds a `_run_generate`-shaped input and verifies a known z-fired player.

- [ ] **Step 5.1: Write the failing integration test**

Create `backend/tests/test_xfp_integration.py`:

```python
"""End-to-end test: generate flow respects the opportunity-score rules.

Uses a tiny in-memory DB and a hand-crafted set of players so we can
verify that the over-producer rule fires for a player we know is an
over-producer relative to the others.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.scoring import ScoringFormat, LeagueType
from app.schemas.generate import GenerateRequest
from app.api.generate import _run_generate


@pytest.mark.asyncio
async def test_over_producer_rule_fires_in_generate(test_db: AsyncSession):
    """Two WRs with the same opportunity but very different actual production.

    - Player A: 80 targets, 600 yards, 4 TDs. ~ league-average efficiency.
    - Player B: 80 targets, 600 yards, 12 TDs. Massively over-produced TDs
      relative to red-zone share → high z → over-producer rule should fire.

    With only two WRs, the σ across the two is large; we add a few more
    middle-of-the-road WRs to anchor the distribution.
    """
    from app.models.player import Player, PlayerStat
    from app.models.projection import Projection
    from app.models.adp import ADPData

    # Build 5 WRs: 1 over-producer, 4 baseline.
    season = 2025
    players_data = [
        ("A_overproducer", 80, 50, 600.0, 12, 10),  # 12 TDs, only 10 RZ looks → high z
        ("B_baseline_1",   80, 50, 600.0, 4,  10),
        ("C_baseline_2",   80, 50, 600.0, 5,  12),
        ("D_baseline_3",   80, 50, 600.0, 3,  10),
        ("E_baseline_4",   80, 50, 600.0, 4,  10),
    ]
    for pid, targets, rec, yds, tds, rz in players_data:
        p = Player(id=pid, name=pid, position="WR", team="ABC", age=26, years_exp=4)
        test_db.add(p)
        test_db.add(PlayerStat(
            player_id=pid, season=season - 1,
            targets=targets, receptions=rec, rec_yards=yds, rec_tds=tds,
            rush_att=0, rush_yards=0.0, rush_tds=0,
            pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
            snaps=900, snap_pct=0.8, carry_share=None, target_share=0.20,
            games_played=16, red_zone_looks=rz,
            actual_tds=tds, expected_tds=float(rz) * 0.4,
        ))
        # Minimal projection so player isn't flagged as "Projection Unavailable"
        test_db.add(Projection(
            player_id=pid, source="fantasypros",
            scoring_format="ppr", projected_points=180.0, season=season,
        ))
    await test_db.commit()

    req = GenerateRequest(
        scoring_format=ScoringFormat.PPR,
        league_type=LeagueType.STANDARD,
        league_size=12,
        qb_td_points=4.0,
        bonus_100yd_rushing=False,
        bonus_100yd_receiving=False,
        bonus_first_downs=False,
        weight_prior_year=1.0,
        weight_espn=0.0,
        weight_consensus=0.0,
        rules=[],
        keepers=[],
    )
    tiered = await _run_generate(req, test_db)

    over = next(t for t in tiered if t.player_id == "A_overproducer")
    baseline = next(t for t in tiered if t.player_id == "B_baseline_1")

    # Over-producer should have had the rule applied — adjusted_score lower
    # than baseline despite identical receiving volume.
    assert "Opportunity Over-Producer" in over.rules_applied
    assert "Opportunity Over-Producer" not in baseline.rules_applied
    assert over.adjusted_score < baseline.adjusted_score
```

- [ ] **Step 5.2: Run the test to verify it fails**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_xfp_integration.py -v
```

Expected: fails because `opportunity_score_z` is never populated in `_run_generate` yet — the rule's condition is `>= 1.5` on `None`, which the engine treats as "field missing → don't fire."

- [ ] **Step 5.3: Wire xFP into `_run_generate`**

Open `backend/app/api/generate.py`. At the top, add the import:

```python
from app.engine.xfp import (
    compute_league_averages,
    compute_per_position_sigmas,
    compute_opportunity_score_z,
    compute_xfp,
)
from app.engine.scoring import _score_receiving, _score_rushing, _score_tds_only
```

Around line 200 (just before the `tiered: list[TieredPlayer] = []` line and the `for player in players` loop), insert this block:

```python
    # ---- Opportunity-score (xFP) pre-pass ----------------------------------
    # Compute per-position league averages of pts/target, pts/carry, pts/RZ
    # using the SAME settings that determine each player's actual FP. Then
    # compute per-position σ_gap. Both feed into per-player z-scores below.
    #
    # Cost: O(players) once. We already iterate `players` below; this loop
    # short-circuits when stat is None so the cost is bounded by players who
    # have a prior-year stat row.
    prior_stats_with_pos = []
    for p in players:
        s = _get_stat(p.stats)
        if s is None:
            continue
        # Wrap so xfp.compute_league_averages sees .position alongside the
        # PlayerStat ORM attributes.
        prior_stats_with_pos.append(_StatWithPosition(stat=s, position=p.position))

    league_avg = compute_league_averages(prior_stats_with_pos, settings)

    # Compute gaps per position to derive σ.
    gaps_by_position: dict[str, list[float]] = {}
    for sp in prior_stats_with_pos:
        xfp = compute_xfp(sp, league_avg)
        if xfp is None:
            continue
        from app.engine.scoring import PlayerStats as _PS
        ps = _PS(
            targets=sp.stat.targets or 0, receptions=sp.stat.receptions or 0,
            rec_yards=sp.stat.rec_yards or 0.0, rec_tds=sp.stat.rec_tds or 0,
            rush_att=sp.stat.rush_att or 0, rush_yards=sp.stat.rush_yards or 0.0,
            rush_tds=sp.stat.rush_tds or 0, pass_att=0, pass_yards=0.0,
            pass_tds=0, interceptions=0,
            games_played=sp.stat.games_played or 1,
        )
        fp = _score_receiving(ps, settings) + _score_rushing(ps, settings) + _score_tds_only(ps, settings)
        gaps_by_position.setdefault(sp.position, []).append(fp - xfp)

    position_sigmas = compute_per_position_sigmas(gaps_by_position)
    # ------------------------------------------------------------------------
```

And add the small adapter dataclass near the top of the file (after the existing helper definitions):

```python
@dataclasses.dataclass
class _StatWithPosition:
    """Pairs a PlayerStat with its parent player's position, so xfp.* sees both."""
    stat: PlayerStat
    position: str

    # Delegate attribute access used by xfp module to the wrapped stat.
    def __getattr__(self, name):
        return getattr(self.stat, name)
```

Inside the `for player in players:` loop, near the existing `prior_touches = ...` block (around line 250), add the per-player z computation:

```python
        opportunity_score_z: Optional[float] = None
        if stat is not None:
            sp = _StatWithPosition(stat=stat, position=player.position)
            opportunity_score_z = compute_opportunity_score_z(sp, league_avg, position_sigmas, settings)
```

Finally, inside the `PlayerContext(...)` constructor call (line ~271), append the new field:

```python
            above_market_contract=above_market_contract,
            opportunity_score_z=opportunity_score_z,
        )
```

- [ ] **Step 5.4: Run the integration test and related tests**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/test_xfp_integration.py tests/test_xfp_rule.py tests/test_xfp.py tests/test_rules.py tests/test_scoring.py -v
```

Expected: all pass. The integration test is the critical one: `A_overproducer` should fire the rule, `B_baseline_1` should not.

- [ ] **Step 5.5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/app/api/generate.py backend/tests/test_xfp_integration.py
git commit -m "feat(generate): wire xFP regression into PlayerContext

Pre-pass over players computes per-position league averages of
pts/target, pts/carry, pts/red-zone-look using the request's
LeagueSettings, then per-position σ_gap from the (FP - xFP)
distribution. Per-player z-score lands on PlayerContext.
opportunity_score_z so the Over-Producer / Under-Producer rules
can fire.

Integration test verifies: given five WRs with identical receiving
volume but one TD outlier, the over-producer rule fires for the
outlier and not for the baselines.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Calibration script (not CI-gated)

Goal: write a stand-alone script that runs the rule against historical seasons via `nfl_data_py` and reports the predictive lift. Used pre-merge to validate the `1.5σ` threshold and `±8%` multipliers; can be re-run any season.

**Files:**
- Create: `backend/scripts/calibrate_xfp_rule.py`
- Create: `backend/scripts/__init__.py` (empty, so the package is importable)

- [ ] **Step 6.1: Create the script**

Create `backend/scripts/__init__.py` as empty (zero bytes).

Create `backend/scripts/calibrate_xfp_rule.py`:

```python
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
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Optional

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
    """Pull seasonal + weekly data from nfl_data_py and build _CalibrationStat rows."""
    seasonal = nfl.import_seasonal_data([year])
    # Filter to skill positions only.
    seasonal = seasonal[seasonal["position"].isin(["QB", "RB", "WR", "TE"])]
    rows: list[_CalibrationStat] = []
    for _, r in seasonal.iterrows():
        rows.append(_CalibrationStat(
            player_id=str(r.get("player_id", "")),
            position=str(r["position"]),
            targets=int(r.get("targets", 0) or 0),
            receptions=int(r.get("receptions", 0) or 0),
            rec_yards=float(r.get("receiving_yards", 0.0) or 0.0),
            rec_tds=int(r.get("receiving_tds", 0) or 0),
            rush_att=int(r.get("carries", 0) or 0),
            rush_yards=float(r.get("rushing_yards", 0.0) or 0.0),
            rush_tds=int(r.get("rushing_tds", 0) or 0),
            red_zone_looks=int(r.get("red_zone_carries", 0) or 0) + int(r.get("red_zone_targets", 0) or 0),
            games_played=int(r.get("games", 0) or 0),
            fantasy_points=float(r.get("fantasy_points_ppr", 0.0) or 0.0),
        ))
    return rows


def calibrate(years: list[int]) -> dict:
    """Run the calibration for the given seasons. Returns the report dict."""
    nfl = _load_nfl_data_py()
    settings = _ppr_settings()
    report = {"years": {}, "summary": {}}

    over_predicted_regression: list[float] = []
    under_predicted_bounce: list[float] = []
    over_baseline_change: list[float] = []
    under_baseline_change: list[float] = []

    for y in years:
        print(f"Loading {y} and {y+1}...", file=sys.stderr)
        stats_y = _load_year(nfl, y)
        stats_y_plus_1 = _load_year(nfl, y + 1)
        next_year_fp = {s.player_id: s.fantasy_points for s in stats_y_plus_1}

        avg = compute_league_averages(stats_y, settings)

        gaps_by_pos: dict[str, list[float]] = {}
        per_player: list[tuple[_CalibrationStat, float, float]] = []
        for s in stats_y:
            xfp = compute_xfp(s, avg)
            if xfp is None:
                continue
            from app.engine.scoring import PlayerStats as _PS, _score_receiving, _score_rushing, _score_tds_only
            ps = _PS(
                targets=s.targets, receptions=s.receptions, rec_yards=s.rec_yards, rec_tds=s.rec_tds,
                rush_att=s.rush_att, rush_yards=s.rush_yards, rush_tds=s.rush_tds,
                pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0, games_played=max(s.games_played, 1),
            )
            fp = _score_receiving(ps, settings) + _score_rushing(ps, settings) + _score_tds_only(ps, settings)
            gaps_by_pos.setdefault(s.position, []).append(fp - xfp)
            per_player.append((s, fp, xfp))

        sigmas = compute_per_position_sigmas(gaps_by_pos)

        year_over = []
        year_under = []
        year_baseline = []
        for s, fp, xfp in per_player:
            z = compute_opportunity_score_z(s, avg, sigmas, settings)
            if z is None:
                continue
            next_fp = next_year_fp.get(s.player_id)
            if next_fp is None or fp == 0:
                year_baseline.append(0.0)
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
            "over_avg_next_year_change_pct": mean(year_over) * 100 if year_over else None,
            "under_avg_next_year_change_pct": mean(year_under) * 100 if year_under else None,
            "baseline_avg_next_year_change_pct": mean(year_baseline) * 100 if year_baseline else None,
        }
        over_baseline_change.extend(year_baseline)
        under_baseline_change.extend(year_baseline)

    report["summary"] = {
        "over_avg_change_pct":     mean(over_predicted_regression) * 100  if over_predicted_regression else None,
        "under_avg_change_pct":    mean(under_predicted_bounce) * 100     if under_predicted_bounce else None,
        "baseline_avg_change_pct": mean(over_baseline_change) * 100       if over_baseline_change else None,
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
```

- [ ] **Step 6.2: Smoke-test the script (manual, not CI)**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/python -m scripts.calibrate_xfp_rule --years 2023 --output /tmp/xfp_calibration_smoke.json
cat /tmp/xfp_calibration_smoke.json | python3 -m json.tool
```

Expected: a JSON report with non-null `over_avg_change_pct` and `under_avg_change_pct` numbers under "summary". If `nfl_data_py` lacks one of the column names this script references (`red_zone_carries`, `red_zone_targets`, `fantasy_points_ppr`), they may have been renamed in a newer version — adjust the column names in `_load_year` to match what the current library exposes. Run `python -c "import nfl_data_py as n; print(list(n.import_seasonal_data([2023]).columns))"` to see what's actually available.

The numeric calibration result itself is for the human reviewer to look at, not for CI to assert. Attach the JSON to the PR description.

- [ ] **Step 6.3: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add backend/scripts/__init__.py backend/scripts/calibrate_xfp_rule.py
git commit -m "feat(scripts): xFP rule calibration tool

Stand-alone script that runs the opportunity-score rule against
historical NFL seasons via nfl_data_py and reports next-year
fantasy-points change for over-producer / under-producer / baseline
groups. Not CI-gated — run by hand and attach the JSON output to the
implementation PR.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Full sweep + PR

Goal: run the full backend test suite (excluding the OOM-prone data sources tests per `autotiers-test-running`), confirm tsc/vitest aren't impacted, and open the PR.

- [ ] **Step 7.1: Backend full sweep**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/pytest tests/ -q --ignore=tests/test_sources
```

Expected: all tests pass. The new tests should add roughly 17 cases (4 scoring helper tests + 10 xfp tests + 7 rule tests = ~21; the integration test is the 22nd).

- [ ] **Step 7.2: Frontend sanity check**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx vitest run 2>&1 | tail -5
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "app-authenticated" | head -5
```

Expected: vitest baseline (157 passing) unchanged; tsc clean. Frontend is untouched, so any change here is a regression — investigate.

- [ ] **Step 7.3: Run the calibration script and capture the report**

```bash
cd /Users/karlkell/Code/AutoTiers/backend && venv/bin/python -m scripts.calibrate_xfp_rule --years 2022 2023 2024 --output /tmp/xfp_calibration_final.json
cat /tmp/xfp_calibration_final.json
```

Keep the output — paste it into the PR description.

- [ ] **Step 7.4: Push the branch**

```bash
cd /Users/karlkell/Code/AutoTiers && git push -u origin <your-branch-name>
```

The pre-push hook (`.githooks/pre-push`) will check the branch's PR state via `gh pr view`. New branch → "no PR" → push proceeds. If the hook isn't installed, run `./.githooks/setup.sh` once.

- [ ] **Step 7.5: Open the PR**

Use the GitHub CLI:

```bash
gh pr create --title "feat: opportunity-score regression rule (xFP)" --body "$(cat <<'EOF'
## Summary

Implements the math contract in `docs/superpowers/specs/2026-06-02-opportunity-score-regression-rule-design.md`. Two new builtin rules that detect players whose actual fantasy production diverged materially from their target/carry/red-zone opportunity last season, and adjust `adjusted_score` toward the mean.

## Calibration result

```
<paste the JSON from Step 7.3 here>
```

Acceptable result per the spec: over-producers' next-season FP change ~8% below baseline, under-producers ~8% above baseline. Adjust multipliers in `builtin_rules.py` if the calibration shows materially different lift.

## What's in this PR

- Pure-math `app/engine/xfp.py` with league averages, xFP, σ, and z-score computation.
- Two new entries in `BUILTIN_RULES` (over-producer, under-producer).
- `opportunity_score_z` field on `PlayerContext`.
- Wire-up in `app/api/generate.py` to compute averages once per request.
- Refactor of `calculate_fantasy_points` into private component helpers (no behavior change).
- Unit tests for the math (`test_xfp.py`), the rule wiring (`test_xfp_rule.py`), and end-to-end (`test_xfp_integration.py`).
- Calibration script `backend/scripts/calibrate_xfp_rule.py` for re-running on future seasons.

## What's NOT in this PR

- Frontend changes. The new rules will appear in the rule list automatically since the rule-config endpoint reads `BUILTIN_RULES`. Follow-up PR: surface z as a player-row flag, group the two new rules in `RuleCategory`.
- Weekly variance / σ-aware tier breaks (separate spec).

## Test plan
- [x] Backend full sweep
- [x] Frontend baseline unchanged
- [x] tsc clean
- [x] Calibration JSON attached above
- [ ] Manual: log in, generate a tier list with the new rules enabled, confirm two players you expect to fire actually do (find them in `rules_applied` in the response).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7.6: Confirm the PR opened**

The output of `gh pr create` includes the PR URL. Verify CI runs and the diff-coverage gate passes (≥80% on touched lines).

---

## Self-review checklist (run before claiming the plan is complete)

### Spec coverage

Walk every section of the spec; identify the implementing task.

- Step 1 (league averages math) → Task 2 (`compute_league_averages` in `xfp.py`)
- Step 2 (xFP per player) → Task 2 (`compute_xfp`)
- Step 3 (actual FP per player) → Task 5 (computed inline in `_run_generate` and inside `compute_opportunity_score_z`)
- Step 4 (z-score) → Task 2 (`compute_opportunity_score_z`)
- Step 5 (the two rules + `opportunity_score_z` field) → Tasks 3 and 4
- "PlayerContext integration" section → Tasks 3 and 5
- "Edge cases" 1–6 → Tasks 2 + 5 (unit-tested in `test_xfp.py`; integration test covers wire-up paths)
- "Statistical concerns" → no implementation task — these go in the PR description (Step 7.5) and the docstring of `xfp.py`
- "Calibration" → Task 6
- "Test plan" → Tasks 2, 4, 5
- "Implementation handoff" file-touch list → covered by Tasks 1–6
- "Open questions for product" → flagged in PR description; not implemented (deliberate)

No spec gaps identified.

### Placeholder scan

`TODO`, `TBD`, "fill in details," "similar to" — none present in the code blocks or commands above. All file paths and commands are exact.

### Type consistency

- `LeagueAverages` (frozen dataclass with three `dict[str, float]` fields) — defined once in Task 2, referenced consistently in Tasks 5 and 6.
- `compute_opportunity_score_z(stat, averages, sigmas, settings) -> Optional[float]` — signature matches between definition (Task 2), wire-up (Task 5), and calibration (Task 6).
- `_score_receiving / _score_rushing / _score_tds_only / _score_passing` — defined in Task 1, used in Tasks 2 and 5.
- `opportunity_score_z` (field name) — consistent across `PlayerContext` (Task 3), tests (Tasks 4, 5), the rule conditions (Task 4), and the wire-up (Task 5).
- `_StatWithPosition` — defined inline in Task 5, used only within that task. Adapter pattern is local; doesn't leak.

No type drift.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-06-02-opportunity-score-regression-rule.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (spec compliance + code quality), fast iteration.

**2. Inline Execution** — execute tasks in this session via `executing-plans`, batch with checkpoints.

Pick one.
