"""Property-based tests for the documented invariants of ``scoring._games_scale``.

The docstring of ``_games_scale`` (backend/app/engine/scoring.py) states a set of
invariants "enforced in tests": non-decreasing in ``games``; ``scale(0) == 0``;
``scale(games >= full_season_games) == 1``; ``steep <= linear`` on the open
interval; ``full_season_games <= 0`` disables the discount; an unknown
``ramp_shape`` raises. The example-based tests in test_scoring.py cover a handful
of points; these Hypothesis tests exercise the *prose* invariants over generated
inputs so boundary cases (extreme games, edges near ``full_season_games``,
negative games) can't quietly regress.

To confirm these fail when an invariant breaks, temporarily invert a comparison
in ``_games_scale`` (e.g. return ``base`` for STEEP) and re-run: the
monotonicity / steep<=linear tests go red.
"""
from hypothesis import given, strategies as st
import pytest

from app.engine.scoring import _games_scale, PriorYearRamp


# Bounded to a generous superset of the API-validated [1, 17] range so we cover
# the production window plus a margin, without generating pathologically large
# denominators that add nothing to the invariant coverage.
_full_seasons = st.integers(min_value=1, max_value=40)
# Include negative games: the clamp is documented to floor them at scale 0, and
# that boundary is one of the "previously-unverified edge cases" (#609).
_games = st.integers(min_value=-5, max_value=60)
_shapes = st.sampled_from([PriorYearRamp.LINEAR, PriorYearRamp.STEEP])


@given(games=_games, full=_full_seasons, shape=_shapes)
def test_scale_is_bounded_unit_interval(games, full, shape):
    """scale always lands in [0, 1] regardless of how extreme games is."""
    s = _games_scale(games, full, shape)
    assert 0.0 <= s <= 1.0


@given(games_a=_games, games_b=_games, full=_full_seasons, shape=_shapes)
def test_non_decreasing_in_games(games_a, games_b, full, shape):
    """Invariant: non-decreasing in ``games`` (for a fixed shape/full_season)."""
    lo, hi = sorted((games_a, games_b))
    assert _games_scale(lo, full, shape) <= _games_scale(hi, full, shape)


@given(full=_full_seasons, shape=_shapes)
def test_scale_zero_at_zero_games(full, shape):
    """Invariant: ``scale(0) == 0`` when the discount is active."""
    assert _games_scale(0, full, shape) == 0.0


@given(games=_games, full=_full_seasons, shape=_shapes)
def test_negative_games_floor_at_zero(games, full, shape):
    """Edge case (#609): games < 0 clamp to scale 0 — confirmed safe, not a crash.

    ``games`` is typed ``int`` and callers pass a non-negative count, but the
    ``max(0.0, ...)`` clamp means a stray negative can never produce a negative
    weight (which would flip the sign of the prior-year term). This asserts that
    guardrail holds rather than relying on callers.
    """
    if games < 0:
        assert _games_scale(games, full, shape) == 0.0


@given(games=st.integers(min_value=0, max_value=200), full=_full_seasons, shape=_shapes)
def test_scale_one_at_or_above_full_season(games, full, shape):
    """Invariant: ``scale(games >= full_season_games) == 1``.

    Includes the exact boundary ``games == full``: ``games / full`` is true
    division, so 14/14 == 1.0 exactly with no float drift — the float edge the
    issue flags as previously-unverified.
    """
    if games >= full:
        assert _games_scale(games, full, shape) == 1.0


@given(games=st.integers(min_value=1, max_value=200), full=_full_seasons)
def test_steep_le_linear_and_strict_on_open_interval(games, full):
    """Invariant: ``steep <= linear`` everywhere, strict on ``0 < games < full``.

    STEEP is ``base ** 2`` and ``base in [0, 1]``, so it never exceeds LINEAR;
    on the open interval ``base in (0, 1)`` the square is *strictly* smaller.
    """
    linear = _games_scale(games, full, PriorYearRamp.LINEAR)
    steep = _games_scale(games, full, PriorYearRamp.STEEP)
    assert steep <= linear
    if 0 < games < full:
        assert steep < linear


@given(
    games=_games,
    full=st.integers(min_value=-20, max_value=0),
    shape=_shapes,
)
def test_non_positive_full_season_disables_discount(games, full, shape):
    """Invariant: ``full_season_games <= 0`` returns 1.0, games irrelevant."""
    assert _games_scale(games, full, shape) == 1.0


@given(games=_games, full=_full_seasons, bad=st.text())
def test_unknown_ramp_shape_raises(games, full, bad):
    """Invariant: an unrecognized ``ramp_shape`` raises rather than defaulting."""
    if bad in (PriorYearRamp.LINEAR.value, PriorYearRamp.STEEP.value):
        return  # a valid enum value, not an error case
    with pytest.raises(ValueError):
        _games_scale(games, full, bad)
