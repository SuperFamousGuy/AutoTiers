"""Tests for the per-position rules build logic in generate.py.

Covers:
- Override applied: when a position override exists, its enabled/weight are used.
- Default preserved: when no override exists for a rule, the built-in default is kept.
- Unknown position: _build_rules_for_position returns built-in defaults without crashing.
- Unknown rule name in override: silently ignored; built-in defaults are used for all rules.
"""
import pytest

from app.api.generate import _build_rules_for_position  # type: ignore[attr-defined]
from app.engine.builtin_rules import BUILTIN_RULES
from app.schemas.generate import GenerateRequest
from app.schemas.rules import RuleOverrideSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(rules: dict | None = None) -> GenerateRequest:
    """Build a minimal valid GenerateRequest with the given per-position rules."""
    return GenerateRequest(
        scoring_format="standard",
        league_type="standard",
        league_size=12,
        weight_prior_year=0.30,
        weight_espn=0.0,
        weight_consensus=0.70,
        rules=rules or {},
    )


def _builtin_by_name(name: str):
    return next(r for r in BUILTIN_RULES if r.name == name)


# ---------------------------------------------------------------------------
# Override applied (enabled/weight changed for a rule with an override)
# ---------------------------------------------------------------------------

def test_override_applied_enabled_false():
    """An override that disables a rule is respected."""
    req = _make_request({
        "RB": [RuleOverrideSchema(name="RB Committee Penalty", enabled=False, weight=1.0)],
    })
    rules = _build_rules_for_position("RB", req)
    rb_committee = next(r for r in rules if r.name == "RB Committee Penalty")
    assert rb_committee.enabled is False


def test_override_applied_weight_changed():
    """An override that changes weight is respected."""
    req = _make_request({
        "WR": [RuleOverrideSchema(name="Target Share Premium", enabled=True, weight=2.0)],
    })
    rules = _build_rules_for_position("WR", req)
    tsp = next(r for r in rules if r.name == "Target Share Premium")
    assert tsp.weight == 2.0
    assert tsp.enabled is True


def test_override_applied_both_fields():
    """Both enabled and weight from override are applied simultaneously."""
    req = _make_request({
        "QB": [RuleOverrideSchema(name="New Team Penalty", enabled=False, weight=0.5)],
    })
    rules = _build_rules_for_position("QB", req)
    rule = next(r for r in rules if r.name == "New Team Penalty")
    assert rule.enabled is False
    assert rule.weight == 0.5


def test_override_does_not_change_builtin_positions():
    """Applying an override does not change the built-in positions field on the rule."""
    builtin = _builtin_by_name("RB Committee Penalty")
    req = _make_request({
        "RB": [RuleOverrideSchema(name="RB Committee Penalty", enabled=False, weight=1.0)],
    })
    rules = _build_rules_for_position("RB", req)
    rb_committee = next(r for r in rules if r.name == "RB Committee Penalty")
    # positions field must be preserved from the built-in
    assert rb_committee.positions == builtin.positions


# ---------------------------------------------------------------------------
# Default preserved when no override for that rule
# ---------------------------------------------------------------------------

def test_default_preserved_when_no_override():
    """Rules with no override keep their built-in enabled and weight."""
    req = _make_request({})
    rules = _build_rules_for_position("RB", req)
    for builtin in BUILTIN_RULES:
        rule = next(r for r in rules if r.name == builtin.name)
        assert rule.enabled == builtin.enabled
        assert rule.weight == builtin.weight


def test_default_preserved_for_unoverridden_rules_when_some_are_overridden():
    """Only the explicitly overridden rule changes; others keep their defaults."""
    req = _make_request({
        "RB": [RuleOverrideSchema(name="RB Committee Penalty", enabled=False, weight=1.0)],
    })
    rules = _build_rules_for_position("RB", req)
    # Target Share Premium was NOT overridden — must keep its builtin default
    builtin_tsp = _builtin_by_name("Target Share Premium")
    tsp = next(r for r in rules if r.name == "Target Share Premium")
    assert tsp.enabled == builtin_tsp.enabled
    assert tsp.weight == builtin_tsp.weight


# ---------------------------------------------------------------------------
# Unknown position string returns builtin defaults (no crash)
# ---------------------------------------------------------------------------

def test_unknown_position_returns_builtin_defaults():
    """An unrecognised position string returns all BUILTIN_RULES at their defaults."""
    req = _make_request({})
    rules = _build_rules_for_position("FLEX", req)
    assert len(rules) == len(BUILTIN_RULES)
    for builtin in BUILTIN_RULES:
        rule = next(r for r in rules if r.name == builtin.name)
        assert rule.enabled == builtin.enabled
        assert rule.weight == builtin.weight


def test_unknown_position_with_overrides_only_applies_to_known_positions():
    """Overrides keyed to 'RB' are not applied when querying a different position."""
    req = _make_request({
        "RB": [RuleOverrideSchema(name="RB Committee Penalty", enabled=False, weight=1.0)],
    })
    # Querying 'QB' — the RB overrides must NOT bleed into QB's rule list
    rules = _build_rules_for_position("QB", req)
    builtin_rbc = _builtin_by_name("RB Committee Penalty")
    rbc = next(r for r in rules if r.name == "RB Committee Penalty")
    assert rbc.enabled == builtin_rbc.enabled
    assert rbc.weight == builtin_rbc.weight


# ---------------------------------------------------------------------------
# Unknown rule name in override is silently ignored
# ---------------------------------------------------------------------------

def test_unknown_rule_name_in_override_is_ignored():
    """An override for a non-existent rule name is silently discarded."""
    req = _make_request({
        "RB": [RuleOverrideSchema(name="Not A Real Rule", enabled=False, weight=0.5)],
    })
    # Should not raise; should return exactly BUILTIN_RULES count
    rules = _build_rules_for_position("RB", req)
    assert len(rules) == len(BUILTIN_RULES)
    # No rule named "Not A Real Rule" in output
    assert all(r.name != "Not A Real Rule" for r in rules)
    # All other rules at their defaults
    for builtin in BUILTIN_RULES:
        rule = next(r for r in rules if r.name == builtin.name)
        assert rule.enabled == builtin.enabled
        assert rule.weight == builtin.weight


def test_unknown_rule_mixed_with_known_override():
    """Unknown rule name ignored; known override still applies."""
    req = _make_request({
        "WR": [
            RuleOverrideSchema(name="Bogus Rule Name", enabled=False, weight=0.1),
            RuleOverrideSchema(name="Target Share Premium", enabled=True, weight=1.5),
        ],
    })
    rules = _build_rules_for_position("WR", req)
    tsp = next(r for r in rules if r.name == "Target Share Premium")
    assert tsp.weight == 1.5


# ---------------------------------------------------------------------------
# Result completeness — always returns all BUILTIN_RULES
# ---------------------------------------------------------------------------

def test_result_always_contains_all_builtin_rules():
    """_build_rules_for_position always returns exactly len(BUILTIN_RULES) rules."""
    req = _make_request({
        "RB": [
            RuleOverrideSchema(name="RB Committee Penalty", enabled=False, weight=1.0),
            RuleOverrideSchema(name="Target Share Premium", enabled=True, weight=2.0),
        ],
    })
    rules = _build_rules_for_position("RB", req)
    assert len(rules) == len(BUILTIN_RULES)
    rule_names = {r.name for r in rules}
    builtin_names = {r.name for r in BUILTIN_RULES}
    assert rule_names == builtin_names
