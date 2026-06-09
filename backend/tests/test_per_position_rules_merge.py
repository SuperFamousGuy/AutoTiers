"""Tests for the per-position rules merge logic in generate.py.

Covers:
- LOCKED_POSITIONS enforcement: 370 Touches and Handcuff RB always keep
  the built-in positions regardless of the client override.
- Non-locked rules: client override is respected when positions field is
  explicitly provided (including null and []).
- Fallback: when the client OMITS the positions field entirely, the built-in
  default is kept.  Pydantic model_fields_set distinguishes "sent null"
  (apply to all) from "field absent" (no preference; keep default).
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
    """Build a minimal RuleSchema with an EXPLICIT positions field (including null).

    This places 'positions' in model_fields_set, meaning the client sent it
    intentionally — null means "apply to all positions", not "no preference".
    """
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


def _schema_no_positions(name: str) -> RuleSchema:
    """Build a minimal RuleSchema with the positions field OMITTED.

    This leaves 'positions' out of model_fields_set, meaning the client
    expressed no preference — _merge_positions should fall back to the
    built-in default.
    """
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


def test_non_locked_rule_client_explicit_null_applies_to_all():
    """Client explicitly sending positions=null means 'apply to all positions'.

    This overrides even a non-null built-in default (e.g. Target Share Premium
    defaults to ["WR", "TE"]).  The user chose "All" in the UI and that choice
    must be persisted — result should be None (apply everywhere).
    """
    builtin = _builtin("Target Share Premium")
    override = _schema_override("Target Share Premium", None)
    result = _merge_positions(builtin, override)
    assert result is None  # explicit null = apply to all


def test_non_locked_rule_field_omitted_keeps_builtin_default():
    """When the client omits the positions field, keep the built-in default.

    The client expressed no preference; _merge_positions should fall back to
    the built-in value rather than wiping it.
    """
    builtin = _builtin("Target Share Premium")
    override = _schema_no_positions("Target Share Premium")
    assert "positions" not in override.model_fields_set
    result = _merge_positions(builtin, override)
    assert result == ["WR", "TE"]  # built-in default preserved


def test_non_locked_rule_client_empty_list_applies_to_all():
    """Client explicitly sending positions=[] means 'apply to all positions'.

    [] and null are semantically equivalent at the engine (both falsy), so
    the explicit override is applied and the built-in default is not kept.
    """
    builtin = _builtin("Target Share Premium")
    override = _schema_override("Target Share Premium", [])
    result = _merge_positions(builtin, override)
    assert result == []  # explicit [] = apply everywhere (engine treats [] as all)


def test_non_locked_rule_no_builtin_default_with_client_null():
    """For a rule with positions=None as built-in default, explicit null is a no-op."""
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
