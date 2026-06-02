# Opportunity Score Regression Rule — Design Spec

## Goal

Add a rule that detects players whose **actual fantasy production** materially diverged from their **opportunity-implied expected production** in the prior season, and adjusts their `adjusted_score` toward the mean.

This generalizes the existing `TD Regression` rule (which only looks at TDs vs expected TDs) into a full opportunity model that catches efficiency-driven outliers across yards, receptions, and TDs.

## Background

### What we already have

Two rules in `backend/app/engine/builtin_rules.py` touch this space:

- **TD Regression** — `actual_tds_above_expected >= 3.0` → `MULTIPLIER 0.90`. Catches TD over-luck. Small sample (5–20 TDs/season) → noisy signal.
- **Red Zone Usage Premium** — `red_zone_looks >= 25` → `MULTIPLIER 1.07`. Rewards red-zone volume. Doesn't compare to actual TDs.

### What's missing

A rule that compares **total fantasy points** against a **volume-based expectation** computed from targets, carries, and receptions. The reasoning:

1. TDs are 5–20/season per player → high variance → small sample → noisy regression signal.
2. Targets and carries are 50–350/season → low variance → big sample → strong regression signal.
3. A player who out-gained their target-share-implied production is more likely to regress than a player who out-TD'd it — but we only catch the TD case today.

Empirically this is the dominant signal in regression-to-mean fantasy analysis (RotoViz, PFF, Establish The Run all lean on opportunity-vs-output models). Our coverage is partial.

### Data we already ingest

From `app/models/player.py:PlayerStat`, per (player, season):

- `targets`, `receptions`, `rec_yards`, `rec_tds`
- `rush_att`, `rush_yards`, `rush_tds`
- `snaps`, `snap_pct`, `carry_share`, `target_share`
- `red_zone_looks`, `expected_tds`, `actual_tds`
- `games_played`

All inputs for an opportunity model are present. **No new fetcher, no new migration.**

## Math

### Step 1 — League-average efficiency per position, per season

For each (season, position) compute league averages of fantasy points per unit of opportunity:

```
pts_per_target[pos, season]   = Σ (rec_pts from receivers at pos) / Σ targets
pts_per_carry[pos, season]    = Σ (rush_pts from rushers at pos)  / Σ carries
pts_per_rz_look[pos, season]  = Σ (TD_pts from pos)               / Σ red_zone_looks
```

These are computed once per refresh cycle and cached. Position-aware because a target at WR ≠ a target at RB in fantasy points.

Pseudocode (one-pass aggregation):

```python
from collections import defaultdict
def league_averages(stats: list[PlayerStat], scoring: LeagueSettings) -> dict[tuple[str, str], float]:
    """Return {(metric, position): avg} for the season."""
    sums = defaultdict(lambda: defaultdict(float))
    for s in stats:
        pos = s.player.position
        rec_pts = score_receiving(s, scoring)   # uses existing scoring helpers
        rush_pts = score_rushing(s, scoring)
        td_pts = score_tds(s, scoring)
        sums["targets"][pos] += s.targets or 0
        sums["rec_pts"][pos] += rec_pts
        sums["carries"][pos] += s.rush_att or 0
        sums["rush_pts"][pos] += rush_pts
        sums["rz_looks"][pos] += s.red_zone_looks or 0
        sums["td_pts"][pos] += td_pts
    return {
        ("pts_per_target", pos):  sums["rec_pts"][pos]  / max(sums["targets"][pos], 1) for pos in POSITIONS
    } | {
        ("pts_per_carry", pos):   sums["rush_pts"][pos] / max(sums["carries"][pos], 1) for pos in POSITIONS
    } | {
        ("pts_per_rz_look", pos): sums["td_pts"][pos]   / max(sums["rz_looks"][pos], 1) for pos in POSITIONS
    }
```

### Step 2 — Expected fantasy points (xFP) per player

```
xFP(player) = targets    × pts_per_target[pos]
            + rush_att   × pts_per_carry[pos]
            + red_zone_looks × pts_per_rz_look[pos]
```

This is the **opportunity-implied** fantasy point total: what an average position-mate would have scored with the same volume.

### Step 3 — Actual fantasy points (FP)

Already computable from existing scoring engine — sum of recorded receiving, rushing, and TD points under the league's `LeagueSettings`.

### Step 4 — Z-score of the gap

Per position, compute the standard deviation of `(FP - xFP)` across the league:

```
gap(player)    = FP(player) - xFP(player)
σ_gap[pos]     = stdev({gap(p) for p in players_at_pos})
z(player)      = gap(player) / σ_gap[player.position]
```

Positive `z` = over-produced relative to opportunity (regression candidate). Negative `z` = under-produced (positive regression candidate).

Use `numpy.std` with `ddof=1` (Bessel's correction). Skip players with `games_played < 8` from the σ calculation — small-sample outliers distort the denominator.

### Step 5 — The rule

Add to `PlayerContext`:

```python
opportunity_score_z: Optional[float] = None  # signed z-score; None if insufficient data
```

Two new rules, both off the same field:

```python
Rule(
    name="Opportunity Over-Producer",
    conditions=[RuleCondition(field="opportunity_score_z", operator=">=", value=1.5)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=0.92),
    description="Penalizes players who scored 1.5+ standard deviations above their target/carry/RZ opportunity last season — strong regression candidate. -8% at default weight.",
),
Rule(
    name="Opportunity Under-Producer",
    conditions=[RuleCondition(field="opportunity_score_z", operator="<=", value=-1.5)],
    effect=RuleEffect(type=EffectType.MULTIPLIER, value=1.08),
    description="Boosts players who scored 1.5+ standard deviations below their target/carry/RZ opportunity last season — likely positive regression. +8% at default weight.",
),
```

Split into two rules (not one symmetric one) so users can disable one direction independently — over-producer penalty is uncontroversial; under-producer boost is more debated (could be a true talent floor, not a regression candidate).

### Threshold rationale

- `|z| >= 1.5` ≈ top/bottom 7% of the position distribution under normal-ish assumptions. Empirically the gap distribution at positions WR/RB is roughly t-distributed with heavier tails — `1.5σ` captures the meaningful outliers without firing on every player.
- `0.92` / `1.08` = ±8% — calibrated against the existing TD Regression rule (-10%) which is a narrower signal. Bigger sample → more confident → but more contested → land near it, slightly softer.

These are starting values. Calibrate in Step 7 below.

## PlayerContext integration

In whatever code path builds `PlayerContext` from `PlayerStat`, compute `opportunity_score_z` once per player using cached league averages. Find that code path (grep for `PlayerContext(`) and add it there. `None` when:

- `games_played < 8` (insufficient sample for σ contribution)
- Any of `targets`, `rush_att`, `red_zone_looks` is `None` (can't compute xFP)
- Player has no prior-season stats at all

Rules with `None` input simply don't fire (existing rule engine behavior — verify with a test).

## Edge cases — must cover

1. **First-year player.** No prior season → `opportunity_score_z = None` → neither rule fires. ✓
2. **Position with no players** (theoretical). `σ_gap[pos]` denominator = 0 → divide-by-zero. Guard: skip the rule when `σ_gap[pos] == 0` or set to `None`.
3. **Player with zero opportunities.** `targets = rush_att = red_zone_looks = 0` → `xFP = 0`, `gap = FP`, large z-score depending on σ. Probably want to exclude — they're not in the regression distribution. Filter: require `targets + rush_att + red_zone_looks >= some_min` (suggest 50 for WR/RB, 20 for TE).
4. **K and DST.** No opportunity inputs exist for these positions. Rule simply doesn't compute → `None` → doesn't fire. ✓
5. **Injury-shortened high-σ seasons.** A player who got hurt in week 3 has tiny opportunity AND tiny FP → `gap ≈ 0` → `z ≈ 0` → rule won't fire even though the data is uninformative. The `games_played < 8` exclusion catches this. Verify.
6. **Sample-size drift across seasons.** League pass/rush distribution shifts year-over-year. Always use the SAME season's league averages for the SAME season's player gaps. Don't mix.

## Statistical concerns to call out in PR review

- **Non-normality.** Gap distribution is heavy-tailed (a few elite efficiency outliers per season). `1.5σ` is empirically chosen, not a normal-distribution percentile. Pinning a CDF claim on it would be wrong.
- **Independence violation.** `FP` and `xFP` are not independent — `FP` includes the points that `xFP` is trying to predict from opportunity. The variance of the gap is therefore smaller than `var(FP) + var(xFP)`. This is fine for relative ranking but means the z-score is not a clean significance test, just a position-relative scaling. Don't market this as "statistically significant."
- **Survivor bias.** League averages are computed over players who actually played. A "league-average target" is therefore the average target received by a healthy enough player to be in the dataset, not a randomly-sampled target. Mostly fine for our purposes.
- **Position cross-talk.** A target by a pass-catching RB and a target by a WR carry different expected values in PPR vs standard. We compute averages per-position, so this is handled — verify the position bucketing matches the league's scoring format (PPR boosts RB receptions more than standard).

## Calibration

Initial thresholds (`1.5σ`) and multipliers (`±8%`) are educated guesses. Pre-merge, validate on 3 historical seasons:

```python
# Pseudocode for the calibration script
for season in [2022, 2023, 2024]:
    z_scores = compute_z_per_player(season)
    next_season_actuals = load_actuals(season + 1)
    # For players who fired the over-producer rule:
    #   Did their next-season FP drop more than the league-average drop?
    # For under-producer:
    #   Did their next-season FP rise more than the league-average rise?
    plot_distribution(z_scores)
    measure_predictive_lift(z_scores, next_season_actuals)
```

Acceptable result: rule fires for ~5–10% of skill players (combined), and the fired-players' subsequent-season FP movement is in the predicted direction with effect size ≥ the multiplier (i.e., -8% predicted, ≥ -8% observed mean).

If the calibration shows a weaker effect, soften the multiplier. If it shows a stronger effect at a tighter z-threshold, tighten and amplify. Document the calibration result in the PR.

## Test plan

### Unit tests (`backend/tests/test_xfp_rule.py` — new file)

1. **League averages math.** Hardcoded input dict of stats → assert exact league averages computed by hand.
2. **Per-player z-score.** Given known league averages and a single player, assert `z` is computed correctly.
3. **Both rules fire correctly at threshold.** Player with `z = 1.5` → over-producer rule fires. Player with `z = -1.5` → under-producer rule fires. Player with `z = 0` → neither fires.
4. **Both rules apply expected multipliers.** Verify `adjusted_score` after rule application matches `before × multiplier ^ weight`.
5. **Degenerate inputs.** `targets = 0, rush_att = 0, red_zone_looks = 0` → context field is `None`, rule doesn't fire.
6. **Insufficient games.** `games_played = 5` → `z = None`, rule doesn't fire.
7. **Position guard.** K and DST never have z computed (no inputs); rule never fires for them.
8. **σ_gap = 0 guard.** Synthetic input where all players at a position have identical gap → z is undefined → no fire.

### Calibration test (separate, not CI-gated)

`backend/scripts/calibrate_xfp_rule.py` — runs against `nfl_data_py` historical seasons, outputs a JSON report with effect-size measurements. Run pre-merge; commit the JSON output to the PR.

### Tier-level smoke test

Run the full tier pipeline before and after this rule lands on the same input dataset. The rule should:
- Move ~5–10% of skill players up or down by ~8% in `adjusted_score`.
- Not change any tier of a player with `|z| < 1.5`.
- Not change any K/DST tier.

## Implementation handoff

This spec is the math contract. The implementation plan (file paths, exact diffs, test ordering, commit boundaries) belongs to the `autotiers-engineer` agent via the writing-plans skill. Hand this file to it.

### File touch list (for the engineer's plan)

- `backend/app/engine/rules.py` — add `opportunity_score_z` field to `PlayerContext`.
- `backend/app/engine/builtin_rules.py` — add two new `Rule` entries.
- `backend/app/engine/xfp.py` — **new** — compute league averages + per-player z-scores.
- Whatever code path builds `PlayerContext` from `PlayerStat` (grep `PlayerContext(`) — populate the new field.
- `backend/tests/test_xfp_rule.py` — **new** — unit tests per Test plan.
- `backend/scripts/calibrate_xfp_rule.py` — **new** — calibration script. Not CI-gated.
- Frontend: `web/src/components/RuleCategory.tsx` or wherever rule names are surfaced — verify the two new rules appear in the right category. Designer agent owns this verification.

### Out of scope (for follow-up specs)

- Weekly variance / σ (the #1 item from the original ranking).
- De-correlating projection blend weights.
- Replacement multiplier calibration.
- EPA ingestion.

## Open questions for product

1. Should the two rules ship enabled-by-default or opt-in? (Recommendation: over-producer ON by default, under-producer OFF — the latter is more contested.)
2. Should the multiplier scale with `|z|` (continuous) or stay a flat `0.92`/`1.08` (binary)? Flat matches the existing rule engine pattern; continuous would require extending `RuleEffect`. Recommendation: flat for v1, revisit if calibration shows large lift at higher z.
3. Should `z` itself be surfaced in the UI as a player flag (informational, like `Handcuff`)? Recommendation: yes — show "Opportunity +1.8σ" / "Opportunity -1.6σ" on `PlayerRow` so the user understands why the rule fired.
