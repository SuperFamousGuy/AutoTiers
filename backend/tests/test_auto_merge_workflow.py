"""Regression guard for the claude-auto-merge sweeper's DRY_RUN arm-guard.

Issue #382: the original guard was an exact-string compare
`[ "$dry_run" = "true" ]` -- correct for the shipped `"true"` and for the
`workflow_dispatch` boolean serialization, but it FAILED OPEN. Any value that
was not literally `"true"` (a future hand-edit to `"True"`, `"1"`, `"yes"`, an
empty string, or any typo) would silently ARM the live merge.

The hardened guard normalizes case and arms ONLY on an explicit `false`; every
other value stays report-only, so the failure mode is "does not merge" rather
than "merges unexpectedly".

These tests do two things:
  1. Pin the structural invariants against the raw workflow text (no YAML
     parser needed -- matches the convention in
     test_implement_issue_workflow.py).
  2. Extract the REAL arm-guard shell block from the workflow (between sentinel
     markers) and execute it in bash across the acceptance-criteria inputs, so
     the test fails if the actual shipped logic regresses -- not a copy of it.
"""

import subprocess
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "claude-auto-merge.yml"
)

TEXT = WORKFLOW.read_text()

MARKER_START = "# >>> arm-guard (issue #382) >>>"
MARKER_END = "# <<< arm-guard (issue #382) <<<"


# --- Structural invariants ------------------------------------------------


def test_fragile_exact_true_guard_is_gone():
    """The fail-open `[ "$dry_run" = "true" ]` arm-guard must not return."""
    assert '[ "$dry_run" = "true" ]' not in TEXT


def test_armed_flag_drives_the_merge_decision():
    """Merging is gated on the computed `armed` flag, not on a raw value."""
    assert '[ "$armed" != "true" ]' in TEXT


def test_arm_guard_block_is_present_and_normalizes_case():
    """The hardened block normalizes case and arms only on explicit false."""
    assert MARKER_START in TEXT
    assert MARKER_END in TEXT
    assert "tr '[:upper:]' '[:lower:]'" in TEXT
    assert '[ "${dry_run_normalized}" = "false" ]' in TEXT


# --- Behavioural test of the REAL extracted logic -------------------------


def _extract_arm_guard_block() -> str:
    """Pull the shell between the sentinel markers, de-indented for bash."""
    start = TEXT.index(MARKER_START)
    end = TEXT.index(MARKER_END)
    block = TEXT[start:end]
    # Workflow run-steps are indented under YAML; strip the common leading
    # whitespace so the snippet runs as a standalone script.
    lines = [line[10:] if line.startswith(" " * 10) else line for line in block.splitlines()]
    return "\n".join(lines)


def _armed_for(value: str) -> str:
    """Run the extracted guard for a given dry_run value; return `armed`."""
    block = _extract_arm_guard_block()
    script = f'set -euo pipefail\ndry_run={value!r}\n{block}\nprintf "%s" "$armed"\n'
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_default_true_disarms():
    """AC: the shipped default "true" stays report-only."""
    assert _armed_for("true") == "false"


def test_explicit_false_arms():
    """AC: DRY_RUN="false" arms the merge."""
    assert _armed_for("false") == "true"


def test_workflow_dispatch_boolean_false_arms():
    """AC: the workflow_dispatch boolean serialization `false` still arms."""
    # workflow_dispatch booleans serialize lowercase; this is the same string,
    # asserted separately to document the manual-run path explicitly.
    assert _armed_for("false") == "true"


def test_uppercase_true_disarms():
    """AC: an unexpected "True" does NOT arm the merge."""
    assert _armed_for("True") == "false"


def test_numeric_one_disarms():
    """AC: an unexpected "1" does NOT arm the merge."""
    assert _armed_for("1") == "false"


def test_yes_disarms():
    """A "yes" style truthy value must not arm the merge."""
    assert _armed_for("yes") == "false"


def test_empty_value_disarms():
    """An empty DRY_RUN must fail safe to report-only."""
    assert _armed_for("") == "false"


def test_uppercase_false_still_arms():
    """Case-insensitive normalization: "FALSE" arms just like "false"."""
    assert _armed_for("FALSE") == "true"


def test_garbage_disarms():
    """Any unrecognized value fails safe to report-only."""
    assert _armed_for("maybe") == "false"
