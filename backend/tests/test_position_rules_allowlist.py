"""Guard against the frontend RulesPanel allowlist desyncing from the backend.

RulesPanel.tsx renders each position's rules via an ALLOWLIST: it iterates
``POSITION_RULES_MAP[position]`` in web/src/lib/positionRulesMap.ts and only
renders rule names present there. Any backend rule whose ``positions`` list
*explicitly* contains a position but whose name is missing from that position's
array is silently dropped from the tab.

This has bitten AutoTiers twice with the same root cause:
  * Kicker rules (Dome Kicker, Mile High Kicker, Cold-Weather Kicker) were all
    invisible until added to POSITION_RULES_MAP["K"].
  * Rookie Draft Capital rules (Rookie RB / Rookie WR) were invisible until
    added to POSITION_RULES_MAP["RB"] / ["WR"] (issue #853).

The original guard only checked the "K" array, so the second bug reappeared
unguarded. This test generalizes it to EVERY position: for each position, every
non-flag BUILTIN_RULES entry that explicitly targets that position must appear
in that position's frontend array.

This test is the authoritative cross-boundary guard. It holds the real
BUILTIN_RULES (not a hand-maintained fixture, which could itself drift) and
parses the arrays out of the TypeScript map.

Scope of the assertion (deliberate):
  * Only rules whose ``positions`` list explicitly contains the position are
    required. Rules with ``positions=None`` (e.g. "Projection Unavailable",
    "Favorites") apply to all positions by convention; the frontend lists them
    per tab for display but they are not position-specific, so they are not
    required by this guard.
  * Flag-effect rules are excluded: RulesPanel filters out
    ``effect.type === "flag"`` (informational, no score change), so they never
    render in any position tab and must not be required here.
  * A small, explicit set of rules is intentionally HIDDEN from every tab by
    product decision (``_INTENTIONALLY_HIDDEN`` below) — e.g. the "370 Touches"
    age bands, which are automatic regressions users don't toggle. These are
    excused from the guard, but the exclusion is itself pinned by a sincerity
    anchor (``test_intentionally_hidden_set_is_accurate``) so it can't silently
    grow to mask a real desync.
"""

import re
from pathlib import Path

import pytest

import app
from app.engine.builtin_rules import BUILTIN_RULES
from app.engine.rules import EffectType

_REPO_ROOT = Path(app.__file__).resolve().parents[2]
_TS_MAP = _REPO_ROOT / "web" / "src" / "lib" / "positionRulesMap.ts"

# The positions RulesPanel renders as tabs. Kept in sync with POSITIONS in the
# TS map (asserted below) so a new position can't slip past this guard.
_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")

# Rules deliberately kept OUT of every position tab despite being non-flag rules
# with an explicit position. These are automatic regressions users don't toggle;
# the frontend locks their absence in positionRulesMap.test.ts ("hidden by
# design"). Adding to this set must be a conscious, reviewed act — it is the one
# escape hatch from the desync guard, so it is itself anchored by
# test_intentionally_hidden_set_is_accurate below.
_INTENTIONALLY_HIDDEN = frozenset(
    {
        "370 Touches (Young RB)",
        "370 Touches (Veteran RB)",
    }
)


def _ts_source_without_comments() -> str:
    src = _TS_MAP.read_text()
    # Strip line comments FIRST: a comment may contain `]` (e.g. a reference to
    # `positions=["K"]`), which would otherwise truncate the non-greedy array
    # match below and drop every real name.
    return re.sub(r"//[^\n]*", "", src)


def _frontend_rule_names(position: str) -> set[str]:
    """Extract the rule-name strings from the ``<position>: [...]`` block."""
    src = _ts_source_without_comments()
    # Match the array body: `QB: [ ... ],` (non-greedy up to the closing `],`).
    # Require the trailing comma so the match anchors on the real array close,
    # not an incidental `]` introduced by a future edit.
    m = re.search(rf"\b{position}:\s*\[(.*?)\]\s*,", src, re.DOTALL)
    assert m, f"Could not find a `{position}: [ ... ]` array in {_TS_MAP}"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _backend_explicit_nonflag_rules(position: str) -> set[str]:
    return {
        r.name
        for r in BUILTIN_RULES
        if r.positions is not None
        and position in r.positions
        and r.effect.type != EffectType.FLAG
    }


def test_ts_map_file_exists():
    assert _TS_MAP.exists(), f"Expected frontend map at {_TS_MAP}"


def test_positions_match_frontend_map():
    """The positions this guard iterates must equal the TS map's POSITIONS."""
    src = _ts_source_without_comments()
    m = re.search(r"POSITIONS\s*=\s*\[(.*?)\]", src, re.DOTALL)
    assert m, f"Could not find a `POSITIONS = [ ... ]` array in {_TS_MAP}"
    ts_positions = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert ts_positions == _POSITIONS, (
        "POSITIONS in positionRulesMap.ts changed; update _POSITIONS in this "
        f"guard so every position is checked. Frontend has {ts_positions}."
    )


@pytest.mark.parametrize("position", _POSITIONS)
def test_every_backend_rule_is_in_frontend_allowlist(position):
    backend = _backend_explicit_nonflag_rules(position) - _INTENTIONALLY_HIDDEN
    frontend = _frontend_rule_names(position)
    missing = backend - frontend
    assert not missing, (
        f"Backend rules with positions=['{position}'] are missing from "
        f"POSITION_RULES_MAP['{position}'] in web/src/lib/positionRulesMap.ts "
        f"and will be silently dropped from the {position} tab: {sorted(missing)}. "
        "If a rule is meant to be hidden, add it to _INTENTIONALLY_HIDDEN with a "
        "reason; otherwise add it to the frontend map."
    )


def test_intentionally_hidden_set_is_accurate():
    # Sincerity anchor for the one escape hatch. Every name in
    # _INTENTIONALLY_HIDDEN must (a) really be a backend explicit-position
    # non-flag rule this guard would otherwise require, and (b) really be absent
    # from every frontend tab. If either stops holding, the exclusion is stale
    # and must be revisited rather than left masking a real desync.
    all_frontend = set()
    for position in _POSITIONS:
        all_frontend |= _frontend_rule_names(position)
    all_backend_explicit = set()
    for position in _POSITIONS:
        all_backend_explicit |= _backend_explicit_nonflag_rules(position)

    for name in _INTENTIONALLY_HIDDEN:
        assert name in all_backend_explicit, (
            f"{name!r} is in _INTENTIONALLY_HIDDEN but is not a backend "
            "explicit-position non-flag rule — the guard would never require it, "
            "so excusing it is meaningless. Remove it from the set."
        )
        assert name not in all_frontend, (
            f"{name!r} is in _INTENTIONALLY_HIDDEN yet appears in a frontend "
            "position tab — it is not actually hidden. Remove it from the set."
        )


def test_guard_covers_the_kicker_regression():
    # Sincerity anchor: these three were the ORIGINAL bug. If any drops out of
    # the backend's explicit-K set (e.g. someone changes positions), this fails
    # loudly rather than the guard silently checking nothing.
    backend_k = _backend_explicit_nonflag_rules("K")
    for name in ("Dome Kicker", "Mile High Kicker", "Cold-Weather Kicker"):
        assert name in backend_k, (
            f"{name!r} is no longer a backend positions=['K'] non-flag rule; "
            "update this guard if that change was intentional."
        )


def test_guard_covers_the_rookie_draft_capital_regression():
    # Sincerity anchor for issue #853: the rookie Draft Capital rules were the
    # second instance of this bug class. Assert they are still the explicit,
    # single-position non-flag rules this guard is meant to protect.
    assert "Rookie RB Draft Capital" in _backend_explicit_nonflag_rules("RB"), (
        "'Rookie RB Draft Capital' is no longer a backend positions=['RB'] "
        "non-flag rule; update this guard if that change was intentional."
    )
    assert "Rookie WR Draft Capital" in _backend_explicit_nonflag_rules("WR"), (
        "'Rookie WR Draft Capital' is no longer a backend positions=['WR'] "
        "non-flag rule; update this guard if that change was intentional."
    )
