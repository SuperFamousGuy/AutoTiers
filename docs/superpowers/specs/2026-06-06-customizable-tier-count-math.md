# Customizable Overall Tier Count — Math Spec

**Date:** 2026-06-06
**Author:** autotiers-mathematician
**Status:** Approved for implementation

---

## 1. Signature change to `assign_tiers`

### Current signature

```python
def assign_tiers(
    all_players: list[TieredPlayer],
    league_size: int = 12,
    tiebreak_adp_attr: str = "adp_ppr",
) -> list[TieredPlayer]:
```

### Proposed signature

```python
def assign_tiers(
    all_players: list[TieredPlayer],
    league_size: int = 12,
    tiebreak_adp_attr: str = "adp_ppr",
    overall_tier_count: int = 10,
) -> list[TieredPlayer]:
```

**Backward compatibility:** `overall_tier_count=10` matches the current hardcoded `max_classes=10` in line 176. All existing callers that omit the argument continue to get the same result.

**Name choice:** `overall_tier_count` (not `n_tiers` or `max_tiers`) because it is the *requested* count, not a ceiling that Jenks or tie-collapse can reduce. The actual count produced may be lower in degenerate cases (see section 4). The name communicates intent clearly without implying a guarantee.

**Default note:** The API layer will pass `req.draft_rounds` as the default when the user supplies no explicit override. The engine default of 10 is intentional — it stays backward-compatible for any direct callers of `assign_tiers` that do not go through the API (e.g. test fixtures, scripts). The API layer at `_run_generate` is where `draft_rounds` is threaded in.

---

## 2. Algorithm: Jenks vs. Quantile switch

### The two modes

**Jenks natural-breaks (variance-minimising):** Finds break points that minimise within-class sum of squared deviations. Produces tiers of unequal size whose boundaries correspond to natural gaps in the score distribution. Meaningful when the score distribution has genuine clusters — e.g. the elite-tier gap between a top-5 WR and a WR12.

**Quantile (rank-based equal-size split):** Places break points at evenly spaced ranks. Every tier gets approximately `N_players / overall_tier_count` players. Honest when the score distribution is smooth (no natural clusters) — which it is for draft rounds 12+, where the VBD curve is a slowly decaying monotone rather than a stepped function.

### Why the distribution is NOT cluster-shaped at high N

VBD scores for ~270 players follow a distribution that has roughly three regimes:
1. Elite (ranks 1-30): steep decline, ~4.1 points per rank
2. Starters (ranks 31-120): moderate decline, ~1.1 points per rank
3. Handcuffs/backups (ranks 121-270): shallow decline, ~0.3 points per rank

This is a piecewise-linear decay, not a multi-modal distribution. Jenks finds the 2-3 major regime transitions efficiently. At high N it starts slicing within-regime sections that are locally smooth — the "breaks" it finds are driven by local noise, not by genuine player-value discontinuities.

**Goodness-of-Variance Fit (GVF) marginal gain** — the fraction of additional between-class variance captured by adding one more tier — is the right diagnostic. When the marginal gain drops below 0.002 (0.2% of total variance), the added class is capturing noise:

| N | GVF    | Marginal GVF gain | Min class size |
|---|--------|-------------------|----------------|
| 5 | 0.9587 | +0.0256           | 23             |
| 7 | 0.9792 | +0.0076           | 14             |
| 10| 0.9894 | +0.0026           | 9              |
| 11| 0.9917 | **+0.0024**       | 9              |
| 12| 0.9934 | **+0.0016**       | 7              |
| 13| 0.9943 | +0.0010           | 7              |
| 15| 0.9958 | +0.0006           | 4              |
| 18| 0.9973 | +0.0004           | 4              |

Computed on a representative 270-player VBD distribution (piecewise-linear, σ=3 noise, seed 42).

**N\* = 11.** At N=11 the marginal GVF gain is 0.0024, just above 0.002. At N=12 it falls to 0.0016, below the threshold. 11 is the last value where Jenks is capturing a cluster that can be defended as meaningful.

### Switch condition

```python
_JENKS_TIER_THRESHOLD = 11  # overall_tier_count <= this -> use jenks; above -> quantile

def _compute_overall_breaks(scores: list[float], overall_tier_count: int) -> list[float]:
    clamped = min(overall_tier_count, len(scores))
    if clamped <= 1:
        return []
    if clamped <= _JENKS_TIER_THRESHOLD:
        breaks = _jenks_interior_breaks(scores, max_classes=clamped)
        if breaks:
            return breaks
        # jenks failed (all identical or insufficient variance) — fall through
    return _quantile_breaks(scores, clamped)
```

Note the fallback: if `clamped <= 11` but Jenks returns empty (all-identical scores), the function falls through to quantile. This matches the existing positional-clustering fallback pattern in `_cluster_position`.

**Sensitivity of N\* choice:** Moving N\* from 11 to 12 changes the algorithm for exactly one tier count (N=12). At N=12 the GVF delta is 0.0016, which is borderline. A user requesting exactly 12 tiers with a typical draft would see Jenks place some tier boundaries 1-3 players differently than quantile would. This is not material. N\*=11 is the safer, more principled choice because it keeps the default `draft_rounds=15` path deterministically in the quantile branch — no ambiguity about which mode an 8-round redraft triggers.

---

## 3. Required fix to `_quantile_breaks`: deduplication

**Bug found:** When `n_classes > len(players)`, `_quantile_breaks` produces duplicate break values because multiple values of `i` map to the same `idx = (i * n) // n_classes`. Duplicate breaks cause `_assign_tier_from_breaks` to double-count, inflating tier numbers.

Example: 5 players, `n_classes=20` → 16 breaks → tiers 1, 3, 5, 7, 9 (odd-only, up to 9) instead of 1-5.

This is a pre-existing latent bug. It does not manifest in production today because:
- Positional clustering: `desired_tiers = min(max_tiers, len(players))` clamps before calling `_quantile_breaks`.
- Overall clustering: hardcoded `max_classes=10` on ~270 players is never close to the player count.

With `overall_tier_count` potentially equalling `draft_rounds * league_size / positions` in an extreme config, we must not rely on callers to guard this. The fix belongs inside `_quantile_breaks` itself.

**Fix:** deduplicate the `breaks` list using a set-tracking approach:

```python
def _quantile_breaks(scores: list[float], n_classes: int) -> list[float]:
    if n_classes < 2 or len(scores) < 2:
        return []
    sorted_desc = sorted(scores, reverse=True)
    n = len(sorted_desc)
    seen: set[float] = set()
    breaks: list[float] = []
    for i in range(1, n_classes):
        idx = (i * n) // n_classes
        if idx <= 0 or idx >= n:
            continue
        upper = sorted_desc[idx - 1]
        lower = sorted_desc[idx]
        if upper == lower:
            continue
        bp = (upper + lower) / 2
        if bp not in seen:
            seen.add(bp)
            breaks.append(bp)
    return breaks
```

This is a pure defensive fix — it does not change output for any input where `n_classes <= len(players)` (the current always-true condition). Verified: the 270-player / 15-tier path produces identical output with and without the fix.

---

## 4. API / schema threading

### `backend/app/schemas/generate.py`

No schema change required for the default-to-`draft_rounds` behavior. The field `draft_rounds` (line 19) already exists and is validated to `1..30`. The API layer uses it directly.

If the product later wants users to set a *separate* override (e.g. "I want 20 tiers even though my draft is 15 rounds"), add an optional field:

```python
overall_tier_count: Optional[int] = None  # None -> default to draft_rounds

@field_validator("overall_tier_count")
@classmethod
def valid_overall_tier_count(cls, v: Optional[int]) -> Optional[int]:
    if v is not None and not (1 <= v <= 30):
        raise ValueError("overall_tier_count must be between 1 and 30")
    return v
```

For the current feature (tier count = draft_rounds), the schema change is **not required**. The API layer just passes `req.draft_rounds`.

### `backend/app/api/generate.py`

At line 467, the `assign_tiers` call becomes:

```python
return assign_tiers(
    capped,
    league_size=req.league_size,
    tiebreak_adp_attr=tiebreak_adp_attr,
    overall_tier_count=req.draft_rounds,
)
```

That is the only change in the API layer for the minimum viable implementation.

---

## 5. Invariants for QA

The following invariants must hold after any implementation of this feature. QA should assert each one.

### INV-1: Tier numbers are 1..overall_tier_count (no 0, no count+1)

`_assign_tier_from_breaks` starts at `tier=1` and increments for each break the score falls at or below. With N-1 interior breaks, the maximum reachable tier is N. Minimum is 1.

Verify: for all players in output, `1 <= p.overall_tier <= overall_tier_count`.

### INV-2: Tiers are monotonic with VBD score (weak)

If player A has `vbd_score > vbd_score_B`, then `overall_tier_A <= overall_tier_B` (equal or better tier). This is weak monotonicity — tied VBD scores may share a tier or differ by one at a boundary.

Verify by sorting output descending by `vbd_score` and asserting `overall_tier` is non-decreasing.

### INV-3: Every tier 1..k is non-empty (under quantile mode)

When `overall_tier_count > _JENKS_TIER_THRESHOLD`, the quantile path guarantees at least one player in every tier from 1 to `min(overall_tier_count, len(players))`, UNLESS all scores are identical (then only tier 1 exists).

Verify: `set(p.overall_tier for p in result) == set(range(1, actual_tier_count + 1))` where `actual_tier_count = len(breaks) + 1`.

### INV-4: count=1 puts all players in overall_tier=1

With `overall_tier_count=1`, `_compute_overall_breaks` returns `[]`, and every player gets `_assign_tier_from_breaks(score, []) = 1`.

### INV-5: count > player pool degrades gracefully

With `overall_tier_count=30` and 5 players, `clamped=5`, and the algorithm produces at most 5 tiers (one per player).

### INV-6: Default backward compatibility

Calling `assign_tiers(players, league_size=12)` (no `overall_tier_count`) must produce identical output to current production, since `overall_tier_count=10` matches the current hardcoded value.

---

## 6. Edge cases — stated behavior

| Input scenario | Behavior |
|---|---|
| `overall_tier_count <= 0` | Blocked by Pydantic validator (`draft_rounds` already validates 1..30). If called directly, `min(count, len(players))` returns `<= 0`, the `<= 1` guard fires, returns `[]` breaks → everyone in tier 1. Safe. |
| `overall_tier_count = 1` | `clamped = 1`, guard fires, `[]` breaks → all players in tier 1. Correct. |
| `overall_tier_count > len(players)` | `clamped = len(players)`. Jenks capped at `min(max_classes, len(unique))`. Quantile dedup ensures max `len(players) - 1` breaks. Never more tiers than players. |
| All scores identical | Both Jenks and quantile return `[]` → all players tier 1. The all-ties quantile path was already verified. |
| All scores negative | Negative VBD is a valid input (below-replacement players). Both algorithms are scale-invariant. Verified empirically (30 players with VBD in [-50, -5] produce 10 tiers correctly). |
| `overall_tier_count = 2` | One interior break → two tiers. Jenks used (2 <= 11). Well-tested path. |
| Fewer unique scores than `clamped` | Jenks internally caps at `len(unique)`. Quantile dedup produces only `len(unique) - 1` breaks max. Both degrade gracefully to fewer tiers than requested. |
| Tie exactly at a break boundary | The `score <= bp` convention places ties in the lower (worse) tier. This is correct and consistent: ties go to the tier of the player just below the boundary in rank order. |

---

## 7. Assumptions

1. **~250-300 players in `capped` when called from the API.** The threshold N\*=11 was calibrated on 270 players. If the pool were 50 players, Jenks would be meaningful to higher N. The threshold is conservative and will not produce wrong results for smaller pools — only potentially switch to quantile slightly early.

2. **VBD distribution is roughly piecewise-linear (heavy-tailed at top, smooth falloff).** This is well-supported by fantasy scoring data. The distribution is NOT Gaussian — do not apply any method that assumes normality to VBD.

3. **Scores are computed with 2 decimal places (as currently `round(..., 2)` in `_compute_vbd`).** The tie-handling in quantile midpoint uses exact float comparison. With 2dp rounding, accidental near-ties that differ by 0.01 will produce real breaks. This is correct behavior.

4. **`draft_rounds` is validated 1..30 upstream.** The math layer does not re-validate. It relies on `clamped = min(overall_tier_count, len(scores))` as the sole safety guard.

5. **Positional tiers are untouched.** `_cluster_position` and `POSITION_MAX_TIERS` are not modified by this change. Only lines 175-178 of `assign_tiers` are affected.

---

## 8. Implementation checklist for the Engineer

The diff is small and isolated to two functions in `backend/app/engine/tiers.py` plus one call site in `backend/app/api/generate.py`.

1. **`tiers.py`:** Add `_JENKS_TIER_THRESHOLD = 11` constant near `POSITION_MAX_TIERS`.

2. **`tiers.py`:** Add `_compute_overall_breaks(scores, overall_tier_count)` helper (code in section 2 above).

3. **`tiers.py`:** Fix `_quantile_breaks` with the dedup guard (code in section 3 above). This is a separate concern from the feature but must ship with it.

4. **`tiers.py`:** Add `overall_tier_count: int = 10` parameter to `assign_tiers`. Replace lines 176-178:

   Before:
   ```python
   overall_breaks = _jenks_interior_breaks(all_scores, max_classes=10)
   for p in ranked:
       p.overall_tier = _assign_tier_from_breaks(p.vbd_score, overall_breaks)
   ```

   After:
   ```python
   overall_breaks = _compute_overall_breaks(all_scores, overall_tier_count)
   for p in ranked:
       p.overall_tier = _assign_tier_from_breaks(p.vbd_score, overall_breaks)
   ```

5. **`api/generate.py`:** Thread `overall_tier_count=req.draft_rounds` into the `assign_tiers` call at line 467.

6. **`tests/test_tiers.py`:** Add tests for INV-1 through INV-6 (see section 5). In particular:
   - `test_overall_tier_count_one_puts_all_in_tier_1`
   - `test_overall_tier_count_high_uses_quantile_path` (count=15, assert all tiers 1..15 populated)
   - `test_overall_tier_count_low_uses_jenks_path` (count=5, assert score gap creates tier gap)
   - `test_overall_tier_count_exceeds_player_pool` (count=50, 5 players, assert max tier <= 5)
   - `test_overall_tier_numbers_monotonic_with_vbd`
   - `test_quantile_breaks_dedup_no_overflow` (5 players, n_classes=20, assert all tiers 1..5)
   - `test_backward_compat_default_matches_old_hardcoded_10` (existing test remains passing)

---

## 9. What is NOT in scope

- Positional tier count customisation. `POSITION_MAX_TIERS` is not touched.
- Frontend tier label display (stops at 6 by product decision). Not a math concern.
- Re-promoting ADP from tiebreaker to weighted input. Not related.
- Any change to `overall_tier` meaning or range relative to `TieredPlayerOut`. The field continues to be an integer `>= 1`. The range ceiling changes from effectively-10 to `overall_tier_count`.
