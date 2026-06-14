# Blend Renormalization Design

**Date:** 2026-06-14
**Author:** autotiers-mathematician
**Status:** Ready for Engineering — pending ESPN auth spike go/no-go
**Scope:** `backend/app/engine/scoring.py` — `blend_scores` function

---

## Context and Motivation

`blend_scores` (`scoring.py:95-118`) performs a weighted sum over up to three projection
sources: `prior_year_actual`, `espn_projection`, and `consensus_projection`. When a source
is `None`, its term is dropped and its weight is silently lost — the function returns a
sum over weights that may total less than 1.0. This is the intentional design: the docstring
at line 101 explicitly calls it out as a penalty for missing data.

That penalty is defensible today because ESPN coverage is hardcoded to `None` in the
generate pipeline (`generate.py:308-313`), and `weight_espn` defaults to `0.0` in the
schema (`schemas/generate.py:18`). The only real-world missing-source case is a player
with no `prior_year_actual` (rookie, or no historical stats loaded), which loses 30% of
the blend weight (the `weight_prior_year` default). The "Projection Unavailable" rule
(`builtin_rules.py:118-120`) applies a further 0.50x multiplier when `avg_proj` is also
`None`, providing a coarser penalty on top.

When ESPN becomes a live source, partial coverage breaks this model catastrophically.
ESPN does not project every player. Any player ESPN does not cover loses `weight_espn`
(e.g., 30%) of their total score budget, relative to a player ESPN does cover. That is
a structural ranking distortion, not a meaningful signal about player quality. The fix
is renormalization: redistribute the missing source's weight across the sources that
are present.

---

## Assumptions

1. **Weights sum to 1.0 before the call.** The `GenerateRequest` validator
   (`schemas/generate.py:47-58`) enforces `abs(sum - 1.0) <= 0.01`. This is a
   pre-condition of `blend_scores`; the function does not re-validate it.

2. **Projection sources are in principle interchangeable as linear inputs.** The blend is
   a weighted average of fantasy-point-scale numbers from different sources, so linear
   renormalization preserves scale. If sources were on different scales (e.g., z-scores
   mixed with raw points), renormalization would not suffice; they are not.

3. **"Missing" means `None`.** A source returning `0.0` is not missing — it is a
   legitimate projection of zero fantasy points. `None` means the source was never
   fetched or does not cover this player.

4. **A weight of `0.0` means the user disabled the source.** A user who sets
   `weight_espn=0.0` does not want ESPN data to contribute, even if ESPN data exists.
   This is distinct from ESPN returning `None` for a player it covers. The renorm
   implementation must respect both the `None` check and the `weight > 0` check.

5. **Fantasy projection distributions are heavy-tailed and not Gaussian.** The
   renormalization formula is a weighted average — it makes no distributional assumption
   and is valid regardless of shape.

6. **ADP remains a tiebreaker only.** The renormalization fix does not touch ADP.
   ADP fields are not inputs to `blend_scores`. This was a deliberate product
   decision and is not revisited here.

---

## Section 1 — Exact Formula Change

### Current formula (`scoring.py:111-117`)

```
score = 0.0
if prior_year_actual is not None:
    score += prior_year_actual * W_p
if espn_projection is not None:
    score += espn_projection * W_e
if consensus_projection is not None:
    score += consensus_projection * W_c
return round(score, 2)
```

Where `W_p + W_e + W_c = 1.0` (pre-condition).

The effective denominator is `W_p * I_p + W_e * I_e + W_c * I_c`, where `I_x` is 1 if
source x is present, 0 otherwise. When all are present this equals 1.0. When one is
absent, the denominator is less than 1.0 and the output is systematically depressed.

### Proposed formula

Define the active set as sources that are both non-`None` AND have a weight strictly
greater than zero:

```
active = [(V_p, W_p), (V_e, W_e), (V_c, W_c)]
    filtered to entries where V_x is not None and W_x > 0

W_active = sum(W_x for x in active)

if W_active == 0.0:
    return 0.0

return round(sum(V_x * W_x / W_active for x in active), 2)
```

This is algebraically equivalent to: compute a weighted mean over the active sources
using the original user-configured weights as relative importance within the active pool.

### Worked numeric examples

In all examples: `W_p=0.40, W_e=0.30, W_c=0.30`.

**All sources present (`W_active = 1.0`):**
```
blend(300, 350, 340) = (300*0.40 + 350*0.30 + 340*0.30) / 1.0
                     = (120 + 105 + 102) / 1.0
                     = 327.00
```
Current output: 327.00. No change — renormalization is a no-op when all sources
are present.

**ESPN missing (`W_active = 0.70`):**
```
blend(300, None, 340) = (300*0.40 + 340*0.30) / 0.70
                      = (120 + 102) / 0.70
                      = 222 / 0.70
                      = 317.14
```
Current output: 222.00. Delta: +95.14. The player's score is no longer punished
for a data-sourcing gap that says nothing about their talent.

Effective weights after renorm: `W_p_eff = 0.40/0.70 = 0.5714`, `W_c_eff = 0.30/0.70 = 0.4286`.
The ratio of prior-year to consensus influence is preserved (4:3 before, 4:3 after).

**Only one source present (`prior_year only`):**
```
blend(300, None, None) = (300*0.40) / 0.40 = 300.00
```
Current output: 120.00. The player scores at full prior-year value, not at
40% of it. This is the intended correction: if prior year is the only evidence
available, the algorithm should use it as a complete signal, not penalize the
player for data gaps elsewhere.

**Only consensus present (rookie, no prior, no ESPN):**
```
blend(None, None, 200) = (200*0.30) / 0.30 = 200.00
```
Current output: 60.00. The rookie's consensus projection is now treated as the
full signal, same as a veteran who happened to have only consensus available.

---

## Section 2 — Conditional vs Unconditional; Default

**Decision: renormalization is unconditional and not a toggle.**

Rationale:

1. **No toggle in the current API.** `LeagueSettings` has no `renormalize` flag.
   Adding a flag creates a dual code path that must be tested, documented, and
   explained to users. The math case for the raw-weight behavior is weak.

2. **The raw-weight penalty conflates two different signals.** The docstring at
   `scoring.py:101` argues that a partial-data player is genuinely riskier.
   That is true, but the "Projection Unavailable" rule (`builtin_rules.py:118-120`)
   already applies a 0.50x multiplier when `consensus_projection` is `None`. That
   rule is the right mechanism for encoding data-confidence uncertainty, because it
   is explicit, configurable by position, and visible in the `rules_applied` field
   in the API response. The implicit penalty from non-renormalization is none of
   those things.

3. **ESPN partial coverage is not "legitimately missing projection."** A player
   ESPN doesn't project is not necessarily a player with no outlook — it may be a
   late-season add, an UDFA, or simply outside ESPN's coverage. Penalizing them at
   the scoring level for a third-party data gap is wrong.

4. **The distinction the docstring tries to preserve is better served by the
   "Projection Unavailable" rule.** That rule fires when `avg_proj is None`, which
   captures the case where no current-season projection from any source exists.
   Renormalization does not affect this: if `consensus_projection=None` and
   `espn_projection=None`, both are absent from the active set, and if
   `prior_year_actual` is also `None`, `W_active = 0.0` and the function returns
   `0.0` (same as current). The rule's penalty is still applied downstream.

**Default:** renormalization is always active. No flag needed.

---

## Section 3 — Interaction Effects

### 3a. Absolute adjusted_score scale

When ESPN is enabled with a non-zero weight, players missing ESPN will see a lift in
their `projected_score_raw` (the pre-rule blend) and therefore in `adjusted_score`
(which is `projected_score_raw` after rule multipliers). Players with all three sources
are unaffected.

The magnitude depends on how many players lack ESPN. In a typical 12-team pool with
`weight_espn=0.30`:

- A player with only consensus (`W_active = 0.30`) goes from `score * 0.30` to `score * 1.0` — a 3.33x lift.
- A player with prior + consensus (`W_active = 0.70`) goes from `sum * 0.70` to `sum / 0.70` — approximately a 1.43x lift.
- A player with all three sources is unaffected.

This is intentional: the absolute scale of `adjusted_score` is not constrained. VBD
(value over replacement) is computed as `adjusted_score - replacement_adjusted_score`,
so as long as renormalization is applied uniformly to all players (it is), VBD
differences are preserved even as absolute values shift.

### 3b. VBD replacement baseline impact

`_compute_vbd` (`tiers.py:160-181`) selects the replacement player at rank
`round(league_size * multiplier)` within the position and subtracts that player's
`adjusted_score` from every player in the position. If both the target player and the
replacement player have the same coverage pattern (both missing ESPN), renormalization
raises both scores by the same multiplicative factor, and the VBD gap is unchanged.

The case where VBD gaps change meaningfully is when coverage is mixed within a
position: elite players have all-source coverage (ESPN does project top-12 players at
every position), while replacement-level players lack ESPN. In that case:

- Elite player's score is unchanged.
- Replacement player's score is lifted.
- VBD gap narrows.

This is the correct outcome. Under the current raw-weight scheme, replacement-level
players are artificially depressed relative to elites who have ESPN coverage, making
elites look even more dominant than they are. Renormalization closes that gap in a
principled way.

**Concrete example** (12-team league, `W_p=0.30, W_e=0.30, W_c=0.40`, replacement RB = rank 30):

| Player | prior | espn | consensus | current blend | renorm blend |
|--------|-------|------|-----------|---------------|--------------|
| Elite RB (all sources) | 310 | 320 | 300 | 309.00 | 309.00 |
| Starter RB (consensus only) | None | None | 200 | 80.00 | 200.00 |
| Starter RB (prior+consensus) | 180 | None | 195 | 132.00 | 188.57 |
| Replacement RB (consensus only) | None | None | 100 | 40.00 | 100.00 |

VBD of Starter RB (consensus only):
- Current: `80 - 40 = +40`
- Renorm: `200 - 100 = +100`

Both the player and the replacement moved up by the same 2.5x factor (100 / 40), so
the VBD ratio is preserved even though absolute values increased. This is the
mathematically correct outcome.

### 3c. Cap selection and the F4 ordering issue

The cap selection in `generate.py:448-473` runs **before** `assign_tiers` and therefore
before VBD is computed. The cap sorts by `adjusted_score` (line 457, 469), which is
the post-rule score derived from `blend_scores`. After renormalization, `adjusted_score`
values for partial-source players will be higher, which means they are more likely to
survive the cap and appear in the final output. This is the correct behavior: the
pre-VBD cap is meant to include all players who might be draftable, and partial-source
players should not be artificially excluded.

**F4 (cap/VBD ordering) must NOT be fixed simultaneously.** F4 is the observation that
the cap is applied pre-VBD, meaning players who would have high VBD (e.g., strong WRs
in a positional scarcity year) can be excluded by a cap that only sees raw
`adjusted_score`. That is an independent design issue. Renormalization makes the
`adjusted_score` values more accurate as inputs to the cap, which mitigates F4's
worst-case severity (partial-source players are no longer artificially excluded), but
does not fix F4 structurally. Fix renormalization first; evaluate F4 independently.

---

## Section 4 — Edge Cases

### Zero sources present

`W_active = 0.0`. Return `0.0`. This matches the current behavior for `blend_scores(None, None, None, ...)`.
Downstream: the "Projection Unavailable" rule fires (if enabled) because `avg_proj is
None` and `prior_actual is None` → `projection_unavailable=True` in `PlayerContext`.

### Source present but weight is zero

Example: `espn_projection=350.0`, `weight_espn=0.0`. The source is excluded from the
active set because `W_e = 0`. The renorm pool is `{prior, consensus}` only. Output
is identical to the case where `espn_projection=None`.

This is correct: `weight_espn=0.0` means the user does not want ESPN to affect scoring.
That intent must be respected even when the data exists. The ESPN value is still stored
in `TieredPlayer.espn_projection` for display in the UI and CSV.

### Single source, weight < 1.0

Example: `blend_scores(300, None, None, w_prior=0.40, w_espn=0.30, w_cons=0.30)`.
Active set: `{(300, 0.40)}`. `W_active = 0.40`. Output: `300 * 0.40 / 0.40 = 300.0`.
The single available source is treated as complete information.

### All weights zero

`W_active = 0.0`. Return `0.0`. This is a degenerate user configuration (weights must
sum to 1.0 per the schema validator, so all-zero is prevented at the API boundary, but
the function should not crash if called directly in tests or via internal tooling).

### Negative scores

Renormalization preserves sign. `blend_scores(-10, None, 280, w_prior=0.40, w_espn=0.30, w_cons=0.30)`
produces `(-10 * 0.40 + 280 * 0.30) / 0.70 = (-4 + 84) / 0.70 = 114.29`. The
negative prior-year score is correctly weighted (it drags the blend down relative to
a player with an equivalent consensus but a positive prior year). No special-casing
needed.

### Player with `prior_year_actual=0.0` (played, scored zero)

`0.0` is not `None`. The source is active. This is correct: a player who played and
scored zero points is different from a player with no stats on record.

---

## Section 5 — Implementation

### Change to `scoring.py:blend_scores`

Replace lines 111-117 of `backend/app/engine/scoring.py` with:

```python
active: list[tuple[float, float]] = []
if prior_year_actual is not None and settings.weight_prior_year > 0:
    active.append((prior_year_actual, settings.weight_prior_year))
if espn_projection is not None and settings.weight_espn > 0:
    active.append((espn_projection, settings.weight_espn))
if consensus_projection is not None and settings.weight_consensus > 0:
    active.append((consensus_projection, settings.weight_consensus))

total_weight = sum(w for _, w in active)
if total_weight == 0.0:
    return 0.0
return round(sum(v * w / total_weight for v, w in active), 2)
```

Update the docstring to reflect renormalization as the new behavior. Delete the
paragraph explaining "RAW weights" and "penalty" — the "Projection Unavailable" rule
is now the sole carrier of that semantic.

No changes required to:
- `tiers.py` — VBD math is unchanged; it consumes `adjusted_score` which is downstream.
- `generate.py` — No change to call sites; `blend_scores` signature is unchanged.
- `schemas/generate.py` — The `weights_sum_to_one` validator is still correct.
- `builtin_rules.py` — "Projection Unavailable" rule remains the signal for no-projection players.

### No new fields required

`TieredPlayer` already stores `espn_projection` as a display field (set directly from
the DB lookup, not from `blend_scores`). No schema migration needed.

---

## Section 6 — Test Plan

All tests go in `backend/tests/test_scoring.py`. The engineer should:

1. Rename the existing test `test_blend_does_not_renormalize_missing_sources` to
   `test_blend_renormalizes_missing_sources` and flip the assertion.
2. Add the new cases below.

### Test cases with exact expected values

**T1 — All sources present: output equals current raw blend (no change)**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(300.0, 350.0, 340.0, settings)
# 300*0.40 + 350*0.30 + 340*0.30 = 327.00
assert result == pytest.approx(327.0)
```

**T2 — ESPN missing: weights redistributed over prior + consensus**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(300.0, None, 340.0, settings)
# (300*0.40 + 340*0.30) / 0.70 = 222 / 0.70 = 317.142857...
assert result == pytest.approx(317.14, abs=0.01)
```
This is the primary regression test. Under the old code, this returns 222.0.
The test **must fail** against the old implementation.

**T3 — Only prior_year present: full prior-year value returned**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(300.0, None, None, settings)
# 300 * (0.40 / 0.40) = 300.0
assert result == pytest.approx(300.0)
```
Old code returns 120.0. Test must fail against old code.

**T4 — Only consensus present (rookie scenario)**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(None, None, 200.0, settings)
# 200 * (0.30 / 0.30) = 200.0
assert result == pytest.approx(200.0)
```
Old code returns 60.0. Test must fail against old code.

**T5 — Only ESPN present**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(None, 350.0, None, settings)
# 350 * (0.30 / 0.30) = 350.0
assert result == pytest.approx(350.0)
```
Old code returns 105.0. Test must fail against old code.

**T6 — All sources missing: returns 0.0**
```python
result = blend_scores(None, None, None, settings=_settings())
assert result == 0.0
```
Behavior unchanged from current. Test passes against both old and new code.
Keep it to guard against regressions.

**T7 — weight_espn=0.0 (source disabled by user), all data present**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.0, weight_consensus=0.60)
result = blend_scores(300.0, 350.0, 340.0, settings)
# ESPN excluded from active set (w=0); active_w = 0.40 + 0.60 = 1.0
# 300*(0.40/1.0) + 340*(0.60/1.0) = 120 + 204 = 324.0
assert result == pytest.approx(324.0)
```
ESPN data exists but its weight is zero; it must not influence the output.
Behavior is the same as old code in this case (old code skips zero-weight terms
implicitly because `espn_projection * 0.0 = 0.0`). Test passes against both.

**T8 — All weights zero: returns 0.0**
```python
# weights_sum_to_one validator blocks this at the API, but blend_scores can
# be called directly in internal tooling; must not crash or divide by zero.
settings = LeagueSettings(
    scoring_format=ScoringFormat.PPR,
    league_type=LeagueType.STANDARD,
    league_size=12,
    qb_td_points=4.0,
    bonus_100yd_rushing=False,
    bonus_100yd_receiving=False,
    bonus_first_downs=False,
    weight_prior_year=0.0,
    weight_espn=0.0,
    weight_consensus=0.0,
)
result = blend_scores(300.0, 350.0, 340.0, settings)
assert result == 0.0
```

**T9 — Negative prior-year score is correctly weighted**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(-10.0, None, 280.0, settings)
# (-10*0.40 + 280*0.30) / 0.70 = (-4 + 84) / 0.70 = 80 / 0.70 = 114.285...
assert result == pytest.approx(114.29, abs=0.01)
```

**T10 — prior_year_actual=0.0 is not treated as missing**
```python
settings = _settings(weight_prior_year=0.40, weight_espn=0.30, weight_consensus=0.30)
result = blend_scores(0.0, None, 200.0, settings)
# 0.0 is not None; active = {(0.0, 0.40), (200.0, 0.30)}; W_active=0.70
# (0.0*0.40 + 200.0*0.30) / 0.70 = 60 / 0.70 = 85.714...
assert result == pytest.approx(85.71, abs=0.01)
# This must NOT equal blend_scores(None, None, 200.0, settings) = 200.0
```

### Test that must be updated

The existing test `test_blend_does_not_renormalize_missing_sources`
(`test_scoring.py:89-110`) asserts `result == 20.0` for a single-source player with
`weight_prior_year=0.20`. After renormalization, the expected value is `100.0`
(`100.0 * 0.20 / 0.20`). The test name and assertion must both be updated. The test
fixture inputs can remain the same.

---

## Relationship to Previous Findings

- **F21 (Finding 2 from prior audit):** Rookies and players without prior-year stats are
  penalized by the raw-weight scheme. This fix directly resolves F21 for the ESPN case
  and reduces its severity for the prior-year case (though the prior-year missing case
  is also fixed).

- **F4 (cap/VBD ordering):** Renormalization improves the accuracy of `adjusted_score`
  inputs to the cap selection pass, mitigating the worst case where partial-source
  players were excluded by a depressed score. F4 as a structural issue (cap runs
  pre-VBD) is not addressed here and should be evaluated in a separate design once
  ESPN coverage data is in hand to measure empirical cap-exclusion rates.

---

## Readiness Gate

This design document is **not an implementation ticket.** It is gated on the ESPN auth
spike returning a confirmed go decision. Once that lands:

1. Engineer implements the `blend_scores` change as specified above.
2. Engineer updates/renames the existing test and adds T2–T10.
3. Mathematician runs `venv/bin/pytest tests/test_scoring.py -q` and confirms all
   tests pass (including that T2–T5 would fail against the old code, verified by
   reverting and running).
4. Engineer opens a PR targeting `main`; QA validates the change on a generate
   request that includes ESPN projections for a mixed-coverage player pool.
