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

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


# --- Behavioural test of the REAL predicate (Copilot waiver for bots) ------
#
# GitHub's automatic Copilot review never fires on bot-authored PRs (it requires
# a Copilot-licensed author), so predicate 3 is permanently unsatisfiable for
# Dependabot. The waiver skips predicate 3 for Bot authors while still enforcing
# it for humans. These tests extract and run the SHIPPED predicate.py, so they
# fail if the waiver logic regresses -- not a copy of it.

PRED_START = "sed 's/^          //' > /tmp/predicate.py <<'PY'"
PRED_END = "\n          PY\n"


def _extract_predicate() -> str:
    """Pull the predicate.py heredoc body, de-indented for python."""
    start = TEXT.index(PRED_START) + len(PRED_START)
    end = TEXT.index(PRED_END, start)
    body = TEXT[start:end]
    # The heredoc body is indented 10 spaces under the YAML scalar (sed strips
    # it at runtime); strip the same common indent here.
    lines = [line[10:] if line.startswith(" " * 10) else line for line in body.splitlines()]
    return "\n".join(lines).strip("\n") + "\n"


def _verdict(pull: dict) -> str:
    """Run the extracted predicate against a GraphQL `pullRequest` payload."""
    payload = json.dumps({"data": {"repository": {"pullRequest": pull}}})
    result = subprocess.run(
        [sys.executable, "-c", _extract_predicate()],
        input=payload,
        capture_output=True,
        text=True,
        env={
            "QUIET_HOURS": "24",
            "COPILOT_REVIEWER_LOGIN": "copilot-pull-request-reviewer[bot]",
            "HOLD_LABELS": "do-not-merge,hold",
            "PATH": "/usr/bin:/bin",
        },
        check=True,
    )
    return result.stdout.strip()


def _clean_pull(**overrides) -> dict:
    """A PR that passes predicates 1,2,4,5 (and 6 collab); caller sets author
    and reviews. committedDate is far in the past so quiet-24h passes."""
    pull = {
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "labels": {"nodes": []},
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "committedDate": "2020-01-01T00:00:00Z",
                        "authoredDate": "2020-01-01T00:00:00Z",
                        "statusCheckRollup": {"state": "SUCCESS"},
                    }
                }
            ]
        },
        "comments": {"nodes": []},
        "reviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
        "author": {"__typename": "User", "login": "someone"},
    }
    pull.update(overrides)
    return pull


def test_bot_author_waives_copilot_review():
    """A Dependabot PR with NO Copilot review is ELIGIBLE (predicate 3 waived)."""
    pull = _clean_pull(author={"__typename": "Bot", "login": "dependabot"})
    assert _verdict(pull) == "ELIGIBLE"


def test_bot_suffix_login_waives_copilot_review():
    """A "[bot]"-suffixed login is treated as a bot even if __typename is off."""
    pull = _clean_pull(author={"__typename": "User", "login": "dependabot[bot]"})
    assert _verdict(pull) == "ELIGIBLE"


def test_human_author_still_requires_copilot_review():
    """A human PR with NO Copilot review is NOT eligible -- waiver is bot-only."""
    pull = _clean_pull(author={"__typename": "User", "login": "alice"})
    assert _verdict(pull) == "SKIP:no-copilot-review"


def test_human_with_copilot_review_reaches_collab_check():
    """A human PR WITH a Copilot review passes predicate 3 and falls through to
    the collaborator check (proving the waiver did not break the human path)."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [{"author": {"login": "copilot-pull-request-reviewer"}, "state": "COMMENTED", "submittedAt": "2020-01-01T00:00:00Z"}]},
    )
    assert _verdict(pull) == "NEEDS_COLLAB:alice"


# --- Behavioural test of predicate 5's rebase exemption (issue #473) --------
#
# When Dependabot rebases a PR onto an updated main (e.g. after a sibling PR
# merges), it force-pushes a commit whose COMMITTER date is "now" but whose
# AUTHOR date is preserved from the original bump. Counting committedDate resets
# the 24h quiet clock on every sibling merge, so a repeatedly-rebased PR never
# ages into eligibility. The fix uses authoredDate for BOT authors, which only
# advances on genuinely new authorship. These tests run the SHIPPED predicate.py
# so they fail if that logic regresses -- not a copy of it.


def _iso(hours_ago: float) -> str:
    """An ISO-8601 "Z" timestamp `hours_ago` hours before now."""
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pull_with_commit(committed: str, *, authored=None, **overrides) -> dict:
    """A clean PR whose head commit carries the given date metadata."""
    commit = {"committedDate": committed, "statusCheckRollup": {"state": "SUCCESS"}}
    if authored is not None:
        commit["authoredDate"] = authored
    pull = _clean_pull(**overrides)
    pull["commits"] = {"nodes": [{"commit": commit}]}
    return pull


def test_bot_rebase_only_push_does_not_reset_quiet_clock():
    """A Dependabot rebase (fresh committer date, preserved old author date) is
    EXEMPT from resetting the 24h clock -> the PR stays ELIGIBLE."""
    pull = _pull_with_commit(
        committed=_iso(1),  # rebased 1h ago -> committer date is recent
        authored="2020-01-01T00:00:00Z",  # original bump, long quiet
        author={"__typename": "Bot", "login": "dependabot"},
    )
    assert _verdict(pull) == "ELIGIBLE"


def test_bot_fresh_bump_still_waits_quiet_window():
    """A genuinely new bump (author AND committer date both recent) is NOT
    exempted -- it must still wait out the 24h quiet window."""
    pull = _pull_with_commit(
        committed=_iso(1),
        authored=_iso(1),  # authored 1h ago -> substantive, not a rebase
        author={"__typename": "Bot", "login": "dependabot"},
    )
    assert _verdict(pull).startswith("SKIP:active-")


def test_human_new_commit_still_resets_quiet_clock():
    """The exemption is bot-only: a human's recent commit still resets the clock
    via committedDate even if its author date is old (e.g. a cherry-pick)."""
    pull = _pull_with_commit(
        committed=_iso(1),  # human pushed 1h ago
        authored="2020-01-01T00:00:00Z",
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [{"author": {"login": "copilot-pull-request-reviewer"}, "state": "COMMENTED", "submittedAt": "2020-01-01T00:00:00Z"}]},
    )
    assert _verdict(pull).startswith("SKIP:active-")


def test_bot_missing_authored_date_falls_back_to_committed():
    """Defensive: if authoredDate is absent for a bot, fall back to committedDate
    (an old committer date here still yields ELIGIBLE, no crash)."""
    pull = _pull_with_commit(
        committed="2020-01-01T00:00:00Z",
        authored=None,  # omitted entirely
        author={"__typename": "Bot", "login": "dependabot"},
    )
    assert _verdict(pull) == "ELIGIBLE"


def test_query_selects_authored_date():
    """The GraphQL query must request authoredDate so the predicate can read it."""
    assert "authoredDate" in TEXT
