"""Guard against the frontend RulesPanel allowlist desyncing from the backend.

RulesPanel.tsx renders kicker rules via an ALLOWLIST: it iterates
POSITION_RULES_MAP["K"] in web/src/lib/positionRulesMap.ts and only renders
rule names present there. Any backend rule with positions=["K"] whose name is
missing from that K array is silently dropped from the kicker tab (the original
bug: Dome Kicker, Mile High Kicker, Cold-Weather Kicker were all invisible).

This test is the authoritative cross-boundary guard. It holds the real
BUILTIN_RULES (not a hand-maintained fixture, which could itself drift) and
parses the K array out of the TypeScript map, asserting every backend rule that
*explicitly* targets kickers appears in the frontend allowlist.

Scope of the assertion (deliberate):
  * Only rules whose ``positions`` list explicitly contains "K" are required.
    Rules with ``positions=None`` (e.g. "Projection Unavailable", "Favorites")
    apply to all positions by convention; the frontend lists them for K display
    but they are not kicker-specific, so they are not required by this guard.
  * Flag-effect rules are excluded: RulesPanel filters out
    ``effect.type === "flag"`` (informational, no score change), so they never
    render in any position tab and must not be required here.
"""

import re
from pathlib import Path

import app
from app.engine.builtin_rules import BUILTIN_RULES
from app.engine.rules import EffectType

_REPO_ROOT = Path(app.__file__).resolve().parents[2]
_TS_MAP = _REPO_ROOT / "web" / "src" / "lib" / "positionRulesMap.ts"


def _frontend_k_rule_names() -> set[str]:
    """Extract the rule-name strings from the K: [...] block of the TS map."""
    src = _TS_MAP.read_text()
    # Strip line comments FIRST: a comment may contain `]` (e.g. a reference to
    # `positions=["K"]`), which would otherwise truncate the non-greedy array
    # match below and drop every real name.
    src = re.sub(r"//[^\n]*", "", src)
    # Match the K array body: `K: [ ... ],` (non-greedy up to the closing `],`).
    m = re.search(r"\bK:\s*\[(.*?)\]", src, re.DOTALL)
    assert m, f"Could not find a `K: [ ... ]` array in {_TS_MAP}"
    body = m.group(1)
    return set(re.findall(r'"([^"]+)"', body))


def _backend_k_explicit_nonflag_rules() -> set[str]:
    return {
        r.name
        for r in BUILTIN_RULES
        if r.positions is not None
        and "K" in r.positions
        and r.effect.type != EffectType.FLAG
    }


def test_ts_map_file_exists():
    assert _TS_MAP.exists(), f"Expected frontend map at {_TS_MAP}"


def test_every_backend_kicker_rule_is_in_frontend_allowlist():
    backend_k = _backend_k_explicit_nonflag_rules()
    frontend_k = _frontend_k_rule_names()
    missing = backend_k - frontend_k
    assert not missing, (
        "Backend rules with positions=['K'] are missing from "
        "POSITION_RULES_MAP['K'] in web/src/lib/positionRulesMap.ts and will be "
        f"silently dropped from the kicker tab: {sorted(missing)}"
    )


def test_guard_covers_the_three_originally_dropped_rules():
    # Sincerity anchor: these three were the actual bug. If any drops out of
    # the backend's explicit-K set (e.g. someone changes positions), this fails
    # loudly rather than the guard silently checking nothing.
    backend_k = _backend_k_explicit_nonflag_rules()
    for name in ("Dome Kicker", "Mile High Kicker", "Cold-Weather Kicker"):
        assert name in backend_k, (
            f"{name!r} is no longer a backend positions=['K'] non-flag rule; "
            "update this guard if that change was intentional."
        )
