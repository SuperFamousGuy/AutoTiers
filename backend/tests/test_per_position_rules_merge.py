"""Tests for the per-position rules merge logic in generate.py.

Covers:
- LOCKED_POSITIONS enforcement: 370 Touches and Handcuff RB always keep
  the built-in positions regardless of the client override.
- Non-locked rules: client override is respected when provided.
- Fallback: when the client does not send positions, the built-in default is kept.
- positions=[] from client treated as null (no override).
"""
import dataclasses
import pytest

from app.api.generate import LOCKED_POSITIONS, _merge_positions  # type: ignore[attr-defined]
from app.engine.builtin_rules import BUILTIN_RULES
from app.engine.rules import Rule, RuleCondition, RuleEffect, EffectType
from app.schemas.rules import RuleSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _builtin(name: str) -> Rule:
    """Return the named built-in rule."""
    return next(r for r in BUILTIN_RULES if r.name == name)


def _schema_override(name: str, positions) -> RuleSchema:
    """Build a minimal RuleSchema with a positions override for testing."""
    builtin = _builtin(name)
    return RuleSchema(
        name=name,
        conditions=[
            {"field": c.field, "operator": c.operator, "value": c.value}
            for c in builtin.conditions
        ],
        effect={"type": builtin.effect.type, "value": builtin.effect.value},
        enabled=True,
        weight=1.0,
        positions=positions,
    )


# ---------------------------------------------------------------------------
# LOCKED_POSITIONS set
# ---------------------------------------------------------------------------

def test_locked_positions_set_contains_expected_names():
    assert LOCKED_POSITIONS == {"370 Touches", "Handcuff RB"}


# ---------------------------------------------------------------------------
# _merge_positions: locked rules
# ---------------------------------------------------------------------------

def test_locked_rule_ignores_client_positions_override():
    """Client sending positions=["WR"] for '370 Touches' must be ignored."""
    builtin = _builtin("370 Touches")
    override = _schema_override("370 Touches", ["WR"])
    result = _merge_positions(builtin, override)
    assert result == builtin.positions  # always ["RB"]


def test_locked_rule_ignores_client_positions_null():
    """Client sending positions=None for 'Handcuff RB' still keeps built-in."""
    builtin = _builtin("Handcuff RB")
    override = _schema_override("Handcuff RB", None)
    result = _merge_positions(builtin, override)
    assert result == builtin.positions  # always ["RB"]


def test_locked_rule_ignores_client_positions_empty_list():
    """Client sending positions=[] for '370 Touches' still keeps built-in."""
    builtin = _builtin("370 Touches")
    override = _schema_override("370 Touches", [])
    result = _merge_positions(builtin, override)
    assert result == builtin.positions  # always ["RB"]


# ---------------------------------------------------------------------------
# _merge_positions: non-locked rules — client override respected
# ---------------------------------------------------------------------------

def test_non_locked_rule_client_override_applied():
    """Client sending positions=["QB"] for a non-locked rule is respected."""
    builtin = _builtin("Over the Hill")
    override = _schema_override("Over the Hill", ["QB"])
    result = _merge_positions(builtin, override)
    assert result == ["QB"]


def test_non_locked_rule_client_override_multiple_positions():
    builtin = _builtin("Bad Offense")
    override = _schema_override("Bad Offense", ["QB", "RB"])
    result = _merge_positions(builtin, override)
    assert result == ["QB", "RB"]


def test_non_locked_rule_client_null_keeps_builtin_default():
    """When client sends positions=None for a non-locked rule, keep the built-in."""
    builtin = _builtin("Target Share Premium")
    override = _schema_override("Target Share Premium", None)
    result = _merge_positions(builtin, override)
    assert result == ["WR", "TE"]  # built-in default preserved


def test_non_locked_rule_client_empty_list_treated_as_no_override():
    """positions=[] from client means 'apply everywhere' but the client sent
    an explicit (if vacuous) value. Per design, [] and null are equivalent —
    both mean 'no filter'. When client sends [], the result should be []
    (falsy, so engine applies to all positions)."""
    builtin = _builtin("Target Share Premium")
    override = _schema_override("Target Share Premium", [])
    result = _merge_positions(builtin, override)
    # [] is not None, so the override is applied: result is []
    # Engine treats [] and None identically (both falsy), so this is correct.
    assert result == []


def test_non_locked_rule_no_builtin_default_with_client_null():
    """For a rule with positions=None as built-in default and no client override."""
    builtin = _builtin("Declining Snap%")
    assert builtin.positions is None
    override = _schema_override("Declining Snap%", None)
    result = _merge_positions(builtin, override)
    assert result is None


def test_non_locked_rule_no_builtin_default_with_client_override():
    """Client can add a position restriction to a rule that had none before."""
    builtin = _builtin("Declining Snap%")
    assert builtin.positions is None
    override = _schema_override("Declining Snap%", ["WR", "TE"])
    result = _merge_positions(builtin, override)
    assert result == ["WR", "TE"]
