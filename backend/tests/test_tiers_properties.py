"""Property-based tests for the break-computation invariants in tiers.py.

``_jenks_interior_breaks`` and ``_quantile_breaks`` (backend/app/engine/tiers.py)
document break-count, ordering, range, and duplicate-stability constraints in
prose. Example-based tests in test_tiers.py hit a few cases; these Hypothesis
tests assert the prose invariants over generated score lists so duplicate-score
clustering, single-value inputs, and ``n_classes > len(scores)`` can't regress.

Both helpers feed ``_assign_tier_from_breaks``, whose contract is that every
break strictly separates two players, breaks stay inside the score range, and no
break is duplicated (a duplicate would create an empty tier). Verify a test bites
by, e.g., deleting the ``if bp not in seen`` dedup in ``_quantile_breaks`` and
re-running ``test_quantile_breaks_are_unique``.
"""
from hypothesis import given, settings, strategies as st

from app.engine.tiers import _jenks_interior_breaks, _quantile_breaks


# Finite floats in a realistic VBD-ish band; no NaN/inf (jenkspy/quantile assume
# orderable finite reals, as production scores always are).
_scores = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-500.0, max_value=500.0, width=32
)
_score_lists = st.lists(_scores, min_size=0, max_size=40)
_classes = st.integers(min_value=0, max_value=15)


# ---------------------------------------------------------------------------
# _jenks_interior_breaks
# ---------------------------------------------------------------------------

@given(scores=_score_lists, max_classes=_classes)
@settings(max_examples=300)
def test_jenks_break_count_bounded(scores, max_classes):
    """Interior breaks number at most ``n_classes - 1`` (min/max dropped).

    ``n_classes = min(max_classes, unique_count)`` and jenks yields
    ``n_classes + 1`` boundaries; dropping the global min and max leaves at most
    ``n_classes - 1`` interior breaks.
    """
    breaks = _jenks_interior_breaks(scores, max_classes)
    n_classes = min(max_classes, len(set(scores)))
    assert len(breaks) <= max(0, n_classes - 1)


@given(scores=_score_lists, max_classes=_classes)
@settings(max_examples=300)
def test_jenks_breaks_sorted_ascending(scores, max_classes):
    """jenkspy returns ascending boundaries, so interior breaks are ascending."""
    breaks = _jenks_interior_breaks(scores, max_classes)
    assert breaks == sorted(breaks)


@given(scores=_score_lists, max_classes=_classes)
@settings(max_examples=300)
def test_jenks_breaks_within_score_range(scores, max_classes):
    """Every interior break lies within ``[min(scores), max(scores)]``."""
    breaks = _jenks_interior_breaks(scores, max_classes)
    if breaks:
        assert min(scores) <= min(breaks)
        assert max(breaks) <= max(scores)


@given(value=_scores, count=st.integers(min_value=0, max_value=20), max_classes=_classes)
def test_jenks_single_value_yields_no_breaks(value, count, max_classes):
    """Fewer than 2 distinct scores → single tier (no breaks)."""
    scores = [value] * count
    assert _jenks_interior_breaks(scores, max_classes) == []


# ---------------------------------------------------------------------------
# _quantile_breaks
# ---------------------------------------------------------------------------

@given(scores=_score_lists, n_classes=_classes)
def test_quantile_break_count_bounded(scores, n_classes):
    """Invariant: at most ``n_classes - 1`` break points."""
    breaks = _quantile_breaks(scores, n_classes)
    assert len(breaks) <= max(0, n_classes - 1)


@given(scores=_score_lists, n_classes=_classes)
def test_quantile_breaks_are_unique(scores, n_classes):
    """Invariant: the seen-set dedup keeps breaks distinct.

    Stability under duplicate scores (#609): even when ``n_classes > len(scores)``
    forces repeated boundary indices, or ties cluster the distribution, no break
    value is emitted twice — a duplicate would otherwise inflate tier numbers.
    """
    breaks = _quantile_breaks(scores, n_classes)
    assert len(breaks) == len(set(breaks))


@given(scores=_score_lists, n_classes=_classes)
def test_quantile_breaks_strictly_within_range(scores, n_classes):
    """Each break is the midpoint of two *distinct* adjacent scores, so it lands
    strictly between the min and max (never equal to either)."""
    breaks = _quantile_breaks(scores, n_classes)
    if breaks:
        assert min(scores) < min(breaks)
        assert max(breaks) < max(scores)


@given(scores=st.lists(_scores, min_size=0, max_size=1), n_classes=_classes)
def test_quantile_needs_two_scores(scores, n_classes):
    """Invariant: fewer than 2 scores → no breaks."""
    assert _quantile_breaks(scores, n_classes) == []


@given(scores=_score_lists, n_classes=st.integers(min_value=-3, max_value=1))
def test_quantile_needs_two_classes(scores, n_classes):
    """Invariant: ``n_classes < 2`` → no breaks."""
    assert _quantile_breaks(scores, n_classes) == []


@given(value=_scores, count=st.integers(min_value=2, max_value=20), n_classes=_classes)
def test_quantile_all_ties_yields_no_breaks(value, count, n_classes):
    """All-identical scores can't be split — every boundary is a pure tie."""
    scores = [value] * count
    assert _quantile_breaks(scores, n_classes) == []
