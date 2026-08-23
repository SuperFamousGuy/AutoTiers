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


HEAD_OID = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
OLD_OID = "0123456789abcdef0123456789abcdef01234567"


def _copilot_review(oid: str | None = HEAD_OID, **overrides) -> dict:
    """A Copilot review tied to `oid` (default: the fixture's head commit).

    Pass ``oid=None`` to model a review whose ``commit`` GraphQL field came
    back null.
    """
    review = {
        "author": {"login": "copilot-pull-request-reviewer"},
        "state": "COMMENTED",
        "submittedAt": "2020-01-01T00:00:00Z",
        "commit": {"oid": oid} if oid is not None else None,
    }
    review.update(overrides)
    return review


def _clean_pull(**overrides) -> dict:
    """A PR that passes predicates 1,2,4 (and 6 collab); caller sets author
    and reviews. committedDate is far in the past so the BOT quiet window
    passes; the head commit carries HEAD_OID so a caller-supplied Copilot
    review can be pinned to it for the HUMAN path."""
    pull = {
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "labels": {"nodes": []},
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "oid": HEAD_OID,
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
        reviews={"nodes": [_copilot_review()]},
    )
    assert _verdict(pull) == "NEEDS_COLLAB:alice"


# --- Predicate 5, HUMAN path: "Copilot signed off on THIS code" -------------
#
# The blanket quiet window is GONE for humans. A Copilot review pinned to the
# CURRENT head commit, with predicate 4 already guaranteeing zero unresolved
# threads, IS the approval -- so there is nothing left to wait for and the PR
# merges on the next tick instead of QUIET_HOURS later.
#
# Two invariants keep that safe, and these tests run the SHIPPED predicate.py:
#   * the review must be tied to the head commit (a push after a clean review
#     de-qualifies the PR until Copilot re-reviews); and
#   * "clean" means no OUTSTANDING Copilot comments, not a literally
#     0-comment review -- threads that were addressed and RESOLVED still
#     count, otherwise a PR whose comments were resolved without a subsequent
#     push would park forever (the capped-PR livelock).


def test_human_recent_commit_merges_when_copilot_reviewed_head():
    """THE headline change: a human PR pushed MINUTES ago is eligible as soon as
    Copilot has reviewed that head commit -- no quiet window at all."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review(submittedAt=_iso(0.05))]},
    )
    pull["commits"]["nodes"][0]["commit"].update(
        committedDate=_iso(0.1), authoredDate=_iso(0.1)
    )
    assert _verdict(pull) == "NEEDS_COLLAB:alice"


def test_human_copilot_review_on_older_commit_is_not_current():
    """A clean Copilot review of a PREVIOUS commit does not clear the new head:
    otherwise pushing after a clean review would merge unreviewed code."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review(oid=OLD_OID)]},
    )
    assert _verdict(pull) == "SKIP:copilot-review-not-current"


def test_human_copilot_review_with_null_commit_is_not_current():
    """Defensive: a review whose `commit` came back null fails CLOSED (skip)."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review(oid=None)]},
    )
    assert _verdict(pull) == "SKIP:copilot-review-not-current"


def test_human_stale_review_plus_current_review_is_current():
    """Copilot's re-review of the new head qualifies even though the earlier
    review of the old commit is still in the list (the normal push+re-review
    sequence, where `reviews` accumulates)."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review(oid=OLD_OID), _copilot_review()]},
    )
    assert _verdict(pull) == "NEEDS_COLLAB:alice"


def test_human_resolved_copilot_threads_count_as_clean():
    """Copilot commented, the comments were addressed and RESOLVED, and Copilot
    has not posted a fresh 0-comment review. Still eligible -- requiring a
    literal 0-comment review would park this PR forever (final-resolve at cap
    resolves threads WITHOUT pushing, so no re-review is ever triggered)."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review()]},
        reviewThreads={
            "nodes": [
                {
                    "isResolved": True,
                    "comments": {"nodes": [{"createdAt": "2020-01-01T00:00:00Z"}]},
                }
            ]
        },
    )
    assert _verdict(pull) == "NEEDS_COLLAB:alice"


def test_human_unresolved_thread_still_blocks_despite_current_review():
    """Predicate 4 survives the rewrite: an OUTSTANDING thread blocks even when
    Copilot has reviewed the head commit."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review()]},
        reviewThreads={
            "nodes": [
                {
                    "isResolved": False,
                    "comments": {"nodes": [{"createdAt": "2020-01-01T00:00:00Z"}]},
                }
            ]
        },
    )
    assert _verdict(pull) == "SKIP:unresolved-threads"


def test_human_changes_requested_still_blocks_despite_current_review():
    """Predicate 4's second half survives too: a human CHANGES_REQUESTED review
    blocks even with a current Copilot review."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={
            "nodes": [
                _copilot_review(),
                {
                    "author": {"login": "bob"},
                    "state": "CHANGES_REQUESTED",
                    "submittedAt": "2020-01-02T00:00:00Z",
                    "commit": {"oid": HEAD_OID},
                },
            ]
        },
    )
    assert _verdict(pull) == "SKIP:changes-requested"


def test_human_missing_head_oid_is_not_eligible():
    """Defensive: no head oid to compare against => fail closed."""
    pull = _clean_pull(
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review()]},
    )
    del pull["commits"]["nodes"][0]["commit"]["oid"]
    assert _verdict(pull) == "SKIP:no-head-oid"


# --- Predicate 5, BOT path: the quiet window (now bot-only) -----------------
#
# Copilot never reviews bot-authored PRs (predicate 3 is waived for them), so
# there is no review signal to key the new human path off and the quiet window
# stays their only settling gate. The rebase exemption below was always
# bot-only, so it lives entirely in this branch now.
#
# When Dependabot rebases a PR onto an updated main (e.g. after a sibling PR
# merges), it force-pushes a commit whose COMMITTER date is "now" but whose
# AUTHOR date is preserved from the original bump. Counting committedDate resets
# the quiet clock on every sibling merge, so a repeatedly-rebased PR never
# ages into eligibility. The fix uses authoredDate for BOT authors, which only
# advances on genuinely new authorship. These tests run the SHIPPED predicate.py
# so they fail if that logic regresses -- not a copy of it.


def _iso(hours_ago: float) -> str:
    """An ISO-8601 "Z" timestamp `hours_ago` hours before now."""
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pull_with_commit(committed: str, *, authored=None, **overrides) -> dict:
    """A clean PR whose head commit carries the given date metadata."""
    commit = {
        "oid": HEAD_OID,
        "committedDate": committed,
        "statusCheckRollup": {"state": "SUCCESS"},
    }
    if authored is not None:
        commit["authoredDate"] = authored
    pull = _clean_pull(**overrides)
    pull["commits"] = {"nodes": [{"commit": commit}]}
    return pull


def test_bot_rebase_only_push_does_not_reset_quiet_clock():
    """A Dependabot rebase (fresh committer date, preserved old author date) is
    EXEMPT from resetting the quiet clock -> the PR stays ELIGIBLE."""
    pull = _pull_with_commit(
        committed=_iso(1),  # rebased 1h ago -> committer date is recent
        authored="2020-01-01T00:00:00Z",  # original bump, long quiet
        author={"__typename": "Bot", "login": "dependabot"},
    )
    assert _verdict(pull) == "ELIGIBLE"


def test_bot_fresh_bump_still_waits_quiet_window():
    """A genuinely new bump (author AND committer date both recent) is NOT
    exempted -- it must still wait out the quiet window."""
    pull = _pull_with_commit(
        committed=_iso(1),
        authored=_iso(1),  # authored 1h ago -> substantive, not a rebase
        author={"__typename": "Bot", "login": "dependabot"},
    )
    assert _verdict(pull).startswith("SKIP:active-")


def test_bot_recent_comment_still_resets_quiet_clock():
    """The quiet window still counts NON-commit activity for bots: a fresh
    comment on an otherwise-old Dependabot PR keeps it parked."""
    pull = _pull_with_commit(
        committed="2020-01-01T00:00:00Z",
        authored="2020-01-01T00:00:00Z",
        author={"__typename": "Bot", "login": "dependabot"},
        comments={"nodes": [{"createdAt": _iso(1)}]},
    )
    assert _verdict(pull).startswith("SKIP:active-")


def test_human_quiet_window_no_longer_applies():
    """The quiet window is now BOT-ONLY. A human's commit from 1h ago -- which
    used to park the PR for QUIET_HOURS -- is eligible immediately, because
    Copilot has reviewed that exact head commit."""
    pull = _pull_with_commit(
        committed=_iso(1),  # human pushed 1h ago
        authored="2020-01-01T00:00:00Z",
        author={"__typename": "User", "login": "alice"},
        reviews={"nodes": [_copilot_review()]},
    )
    assert _verdict(pull) == "NEEDS_COLLAB:alice"


def test_bot_missing_authored_date_falls_back_to_committed():
    """Defensive: if authoredDate is absent for a bot, fall back to committedDate
    (an old committer date here still yields ELIGIBLE, no crash)."""
    pull = _pull_with_commit(
        committed="2020-01-01T00:00:00Z",
        authored=None,  # omitted entirely
        author={"__typename": "Bot", "login": "dependabot"},
    )
    assert _verdict(pull) == "ELIGIBLE"


GQL_START = "data=\"$(gh api graphql -f query='"
GQL_END = "' -F owner="


def test_query_selects_authored_date():
    """The GraphQL query must request authoredDate so the predicate can read it.

    Scope the assertion to the GraphQL query text only — ``authoredDate`` also
    appears in the predicate code and comments elsewhere in the file, so an
    unscoped ``in TEXT`` check would pass even if the query stopped selecting it.
    """
    start = TEXT.index(GQL_START) + len(GQL_START)
    end = TEXT.index(GQL_END, start)
    query = TEXT[start:end]
    assert "authoredDate" in query


def _graphql_query() -> str:
    start = TEXT.index(GQL_START) + len(GQL_START)
    return TEXT[start : TEXT.index(GQL_END, start)]


def test_query_selects_head_commit_oid():
    """Predicate 5's human path compares the head commit oid, so the query must
    select it. Scoped to the query text (``oid`` appears in comments too)."""
    query = _graphql_query()
    head_block = query[query.index("commits(last:1)") : query.index("comments(last:100)")]
    assert "oid" in head_block


def test_query_selects_review_commit_oid():
    """...and the oid of the commit each review was made against, which is how
    a stale Copilot review is told apart from a current one."""
    query = _graphql_query()
    reviews_block = query[query.index("reviews(last:100)") : query.index("reviewThreads(first:100)")]
    assert "commit{ oid }" in reviews_block or "commit { oid }" in reviews_block


# --- Behavioural test of the REAL mergeable-UNKNOWN retry loop ---------------
#
# GitHub computes `mergeable` lazily/async; a first GraphQL read is often UNKNOWN
# and a plain read does NOT force the recompute, so eligible PRs sat at UNKNOWN
# forever and never merged (stuck Dependabot #439 et al.). The fix re-polls the
# single PR up to MERGEABLE_RETRIES times on UNKNOWN before giving up; the act of
# fetching kicks the background computation, so a later poll usually resolves.
#
# SAFETY INVARIANT: a still-UNKNOWN PR after the retries must SKIP (never merge),
# and a CONFLICTING read must stop the retry immediately (it is not UNKNOWN) and
# SKIP. UNKNOWN is NEVER treated as mergeable.
#
# These tests EXTRACT the real retry loop between its sentinel markers and run it
# in bash with a STUBBED `gh` on PATH that emits a scripted sequence of GraphQL
# payloads, so they fail if the shipped loop regresses -- not a copy of it. The
# stub also records every invocation, letting us assert the EXACT fetch count
# (bug-class #7: no weak-bound assertions -- we pin fetch counts and final
# mergeable exactly, not ">= something").

RETRY_START = "# >>> mergeable-retry >>>"
RETRY_END = "# <<< mergeable-retry <<<"


def test_retry_markers_present_and_bounded():
    """The retry loop exists, is sentinel-delimited, bounded, and re-checks
    mergeable -- structural guard so the extract-and-run tests can find it."""
    assert RETRY_START in TEXT
    assert RETRY_END in TEXT
    block = TEXT[TEXT.index(RETRY_START) : TEXT.index(RETRY_END)]
    # Bounded: compares an attempt counter against the retry cap.
    assert 'attempt=$((attempt + 1))' in block
    assert '[ "$attempt" -gt "$MERGEABLE_RETRIES" ]' in block
    # Re-checks mergeable and only keeps looping while UNKNOWN.
    assert '[ "$mergeable" != "UNKNOWN" ]' in block
    # Empty (API error) break must precede the UNKNOWN check so an error is
    # never conflated with UNKNOWN.
    empty_pos = block.index('if [ -z "$data" ]; then')
    unknown_pos = block.index('[ "$mergeable" != "UNKNOWN" ]')
    assert empty_pos < unknown_pos


def test_retry_loop_does_not_treat_unknown_as_mergeable():
    """The retry block never emits a merge decision itself; it only re-fetches.
    The unchanged predicate.py is what SKIPs UNKNOWN -- assert the block contains
    no merge call and does not rewrite mergeable to MERGEABLE."""
    block = TEXT[TEXT.index(RETRY_START) : TEXT.index(RETRY_END)]
    assert "gh pr merge" not in block
    assert 'mergeable="MERGEABLE"' not in block


def _extract_retry_block() -> str:
    """Pull the shell between the retry sentinel markers, de-indented for bash."""
    start = TEXT.index(RETRY_START)
    end = TEXT.index(RETRY_END)
    block = TEXT[start:end]
    lines = [line[12:] if line.startswith(" " * 12) else line for line in block.splitlines()]
    return "\n".join(lines)


def _run_retry(
    sequence: list[str], retries: str = "3", backoff: str = "0", budget: str = "1000000"
):
    """Execute the REAL extracted retry loop with a stubbed `gh` that emits, on
    each call, the next payload in `sequence` (a mergeable string, or the literal
    "" for an empty/API-error response). Returns (final_mergeable, gh_call_count,
    final_data_nonempty).

    backoff defaults to 0 so the test does not actually sleep (and a no-op `sleep`
    stub is on PATH so even a nonzero backoff never blocks). budget defaults to an
    effectively-infinite value so the global retry-budget cap (issue #474) never
    fires for the non-budget tests; the budget tests pass a small value.
    """
    import os
    import tempfile
    import textwrap

    block = _extract_retry_block()
    tmp = tempfile.mkdtemp()
    # A fake `gh` on PATH. Each call reads+increments a counter file and prints
    # the payload for that 1-based call index (or empty past the end of the
    # sequence). It ignores all args (the real invocation is `gh api graphql`).
    payloads = []
    for m in sequence:
        if m == "":
            payloads.append("")  # empty response == API error
        else:
            payloads.append(
                '{"data":{"repository":{"pullRequest":{"mergeable":"%s"}}}}' % m
            )
    counter = os.path.join(tmp, "n")
    with open(counter, "w") as fh:
        fh.write("0")
    seq_file = os.path.join(tmp, "seq")
    with open(seq_file, "w") as fh:
        # one payload per line; blank line == empty payload
        fh.write("\n".join(p if p else "<<EMPTY>>" for p in payloads) + "\n")
    gh = os.path.join(tmp, "gh")
    with open(gh, "w") as fh:
        fh.write(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            n=$(cat {counter}); n=$((n+1)); printf '%s' "$n" > {counter}
            line=$(sed -n "${{n}}p" {seq_file})
            if [ -z "$line" ] || [ "$line" = "<<EMPTY>>" ]; then
              exit 0
            fi
            printf '%s' "$line"
        """))
    os.chmod(gh, 0o755)
    _write_sleep_stub(tmp)

    # Drive the loop, then report the final mergeable + fetch count. The budget
    # var + `retry_sleep_spent` counter are declared here so the extracted block
    # -- which references both (they live OUTSIDE the marker block in the real
    # workflow, initialized before the candidate loop) -- runs under `set -u`.
    script = textwrap.dedent(f"""\
        set -euo pipefail
        export PATH="{tmp}:$PATH"
        MERGEABLE_RETRIES={retries}
        MERGEABLE_BACKOFF_SECONDS={backoff}
        MERGEABLE_TOTAL_RETRY_BUDGET_SECONDS={budget}
        retry_sleep_spent=0
        OWNER=o; repo_name=r; pr=1
        {block}
        final_mergeable="$(printf '%s' "$data" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{{}}"); print((((d.get("data") or {{}}).get("repository") or {{}}).get("pullRequest") or {{}}).get("mergeable") or "")' 2>/dev/null || true)"
        echo "FINAL_MERGEABLE=${{final_mergeable}}"
        echo "GH_CALLS=$(cat {counter})"
        echo "RETRY_SLEEP_SPENT=${{retry_sleep_spent}}"
        if [ -n "$data" ]; then echo "DATA=nonempty"; else echo "DATA=empty"; fi
    """)
    try:
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, check=True
        )
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    out = dict(
        line.split("=", 1) for line in result.stdout.strip().splitlines() if "=" in line
    )
    return out["FINAL_MERGEABLE"], int(out["GH_CALLS"]), out["DATA"] == "nonempty"


def _write_sleep_stub(tmp: str) -> None:
    """Drop a no-op `sleep` on PATH so the extracted loop never actually blocks
    even with a nonzero MERGEABLE_BACKOFF_SECONDS -- the budget accounting adds
    the backoff to `retry_sleep_spent` arithmetically, independent of real time."""
    import os

    sl = os.path.join(tmp, "sleep")
    with open(sl, "w") as fh:
        fh.write("#!/usr/bin/env bash\nexit 0\n")
    os.chmod(sl, 0o755)


def test_retry_exhausted_stays_unknown_and_fetches_retries_plus_one():
    """AC: mergeable never resolves -> after RETRIES retries the payload is STILL
    UNKNOWN (so predicate.py will SKIP -- never merges an unresolved PR), and the
    loop made exactly RETRIES+1 fetches (no off-by-one, no infinite loop)."""
    final, calls, nonempty = _run_retry(["UNKNOWN"] * 6, retries="3")
    assert final == "UNKNOWN"      # NEVER coerced to MERGEABLE
    assert calls == 4              # RETRIES+1 == 3+1, exact (bug-class #7)
    assert nonempty is True


def test_retry_resolves_to_mergeable_stops_early():
    """AC: UNKNOWN then MERGEABLE -> loop stops on the resolve, final==MERGEABLE,
    exactly 2 fetches (1 UNKNOWN + 1 resolve)."""
    final, calls, _ = _run_retry(["UNKNOWN", "MERGEABLE", "MERGEABLE"], retries="3")
    assert final == "MERGEABLE"
    assert calls == 2


def test_retry_resolves_to_conflicting_stops_immediately_and_skips():
    """AC: UNKNOWN then CONFLICTING -> loop stops on CONFLICTING (it is not
    UNKNOWN); final==CONFLICTING so predicate.py SKIPs. NEVER merges a conflict.
    Exactly 2 fetches."""
    final, calls, _ = _run_retry(["UNKNOWN", "CONFLICTING", "MERGEABLE"], retries="3")
    assert final == "CONFLICTING"
    assert calls == 2


def test_retry_first_read_mergeable_no_extra_fetches():
    """A PR that is MERGEABLE on the first read never retries: exactly 1 fetch."""
    final, calls, _ = _run_retry(["MERGEABLE"], retries="3")
    assert final == "MERGEABLE"
    assert calls == 1


def test_retry_first_read_conflicting_never_retries():
    """A CONFLICTING first read stops immediately: 1 fetch, final CONFLICTING
    (predicate.py SKIPs). The retry must not 'rescue' a real conflict."""
    final, calls, _ = _run_retry(["CONFLICTING", "MERGEABLE"], retries="3")
    assert final == "CONFLICTING"
    assert calls == 1


def test_retry_api_error_breaks_without_conflation():
    """AC (API error mid-retry): an empty/errored response breaks the loop with
    empty data (caller's empty-guard -> NOT eligible). It is NOT looped on as if
    UNKNOWN, and NEVER produces a merge. Empty on the FIRST read == 1 fetch."""
    final, calls, nonempty = _run_retry([""], retries="3")
    assert final == ""             # nothing extracted
    assert nonempty is False       # data empty -> caller skips PR
    assert calls == 1              # did not spin


def test_retry_api_error_after_unknown_breaks():
    """UNKNOWN then an API error: the error breaks the loop (empty data), does not
    keep retrying as if UNKNOWN. 2 fetches, empty final data."""
    final, calls, nonempty = _run_retry(["UNKNOWN", ""], retries="3")
    assert nonempty is False
    assert calls == 2


# --- Global UNKNOWN-retry BUDGET cap (issue #474) ----------------------------
#
# The per-PR retry above is bounded (MERGEABLE_RETRIES+1 fetches), but a
# pathological tick where every one of up to 100 candidates is stuck-UNKNOWN
# would accumulate MERGEABLE_RETRIES*MERGEABLE_BACKOFF_SECONDS of sleep PER PR
# (~600s worst case), pressing against the 10-min job timeout. #474 adds a global
# budget (MERGEABLE_TOTAL_RETRY_BUDGET_SECONDS): a `retry_sleep_spent` counter
# initialized ONCE before the candidate loop and shared across every PR. The loop
# only sleeps when doing so keeps the running total within budget; once spent,
# this and every later UNKNOWN PR skip re-polling (payload stays UNKNOWN ->
# predicate.py SKIPs) and get retried next run.
#
# These tests drive the REAL extracted retry block: the single-PR ones through
# `_run_retry` with a small budget, and the cross-PR accounting through a
# multi-PR harness that shares one `retry_sleep_spent` across N sequential PRs --
# exactly how the shipped candidate loop threads it. Fetch counts and total sleep
# are pinned EXACTLY (bug-class #7: no weak ">= something" bounds).


def test_budget_cap_wired_into_loop():
    """Structural: the global budget env var exists, the counter is initialized
    OUTSIDE the retry marker block (before the candidate loop), and the block
    gates the sleep on the budget and accumulates spend."""
    assert "MERGEABLE_TOTAL_RETRY_BUDGET_SECONDS:" in TEXT  # env declared
    # Counter initialized before the per-PR loop, NOT inside the marker block
    # (else it would reset every PR and the cap would be per-PR, not global).
    init_pos = TEXT.index("retry_sleep_spent=0")
    loop_pos = TEXT.index("for pr in $(echo")
    block_start = TEXT.index(RETRY_START)
    assert init_pos < loop_pos < block_start
    block = TEXT[TEXT.index(RETRY_START) : TEXT.index(RETRY_END)]
    # The sleep is gated on the running total + next backoff vs the budget...
    assert '(retry_sleep_spent + MERGEABLE_BACKOFF_SECONDS))" -gt "$MERGEABLE_TOTAL_RETRY_BUDGET_SECONDS"' in block
    # ...and the spend is accumulated only after an actual sleep.
    assert "retry_sleep_spent=$((retry_sleep_spent + MERGEABLE_BACKOFF_SECONDS))" in block


def test_budget_cuts_single_pr_short():
    """A tiny budget stops re-polling an all-UNKNOWN PR before MERGEABLE_RETRIES:
    budget=2s / backoff=2s permits exactly ONE sleep, so 2 fetches (not 4), and
    the payload stays UNKNOWN (predicate.py SKIPs -- never merges unresolved)."""
    final, calls, _ = _run_retry(["UNKNOWN"] * 6, retries="3", backoff="2", budget="2")
    assert final == "UNKNOWN"  # never coerced to MERGEABLE
    assert calls == 2          # 1 initial fetch + 1 re-poll, then budget stops it


def test_budget_zero_disables_repoll_entirely():
    """Budget 0: no UNKNOWN re-poll sleep is ever affordable, so an UNKNOWN PR is
    fetched exactly once and skipped (retried next run). The safety invariant
    holds: UNKNOWN stays UNKNOWN."""
    final, calls, _ = _run_retry(["UNKNOWN"] * 6, retries="3", backoff="2", budget="0")
    assert final == "UNKNOWN"
    assert calls == 1


def test_budget_does_not_shorten_when_ample():
    """A budget larger than the per-PR worst case must NOT change behaviour: the
    per-PR MERGEABLE_RETRIES cap still governs -> RETRIES+1 fetches, budget idle."""
    final, calls, _ = _run_retry(["UNKNOWN"] * 6, retries="3", backoff="2", budget="1000")
    assert final == "UNKNOWN"
    assert calls == 4  # RETRIES+1, unchanged by the (ample) budget


def _run_retry_budget(
    num_prs: int, retries: str, backoff: str, budget: str, mergeable: str = "UNKNOWN"
):
    """Run the REAL extracted retry block once per PR across `num_prs` sequential
    PRs, sharing a SINGLE `retry_sleep_spent` counter initialized before the loop
    -- mirroring the shipped candidate loop. A stubbed `gh` always returns a
    payload with the given `mergeable` (models every candidate stuck at that
    state); a no-op `sleep` keeps it instant. Returns (retry_sleep_spent,
    total_gh_calls, per_pr_fetch_counts)."""
    import os
    import tempfile
    import textwrap

    block = _extract_retry_block()
    tmp = tempfile.mkdtemp()
    payload = '{"data":{"repository":{"pullRequest":{"mergeable":"%s"}}}}' % mergeable
    counter = os.path.join(tmp, "n")
    with open(counter, "w") as fh:
        fh.write("0")
    gh = os.path.join(tmp, "gh")
    with open(gh, "w") as fh:
        fh.write(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            n=$(cat {counter}); n=$((n+1)); printf '%s' "$n" > {counter}
            printf '%s' '{payload}'
        """))
    os.chmod(gh, 0o755)
    _write_sleep_stub(tmp)

    # One shared counter, then the extracted block per PR -- deltas in the fetch
    # counter give each PR's fetch count so we can prove later PRs stop cold.
    script = textwrap.dedent(f"""\
        set -euo pipefail
        export PATH="{tmp}:$PATH"
        MERGEABLE_RETRIES={retries}
        MERGEABLE_BACKOFF_SECONDS={backoff}
        MERGEABLE_TOTAL_RETRY_BUDGET_SECONDS={budget}
        OWNER=o; repo_name=r
        retry_sleep_spent=0
        for pr in $(seq 1 {num_prs}); do
          before="$(cat {counter})"
          {block}
          after="$(cat {counter})"
          echo "PR_FETCHES=$((after - before))"
        done
        echo "RETRY_SLEEP_SPENT=${{retry_sleep_spent}}"
        echo "TOTAL_GH_CALLS=$(cat {counter})"
    """)
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    per_pr = []
    spent = total = None
    for line in result.stdout.strip().splitlines():
        if line.startswith("PR_FETCHES="):
            per_pr.append(int(line.split("=", 1)[1]))
        elif line.startswith("RETRY_SLEEP_SPENT="):
            spent = int(line.split("=", 1)[1])
        elif line.startswith("TOTAL_GH_CALLS="):
            total = int(line.split("=", 1)[1])
    return spent, total, per_pr


def test_budget_bounds_total_sleep_across_prs():
    """The whole point of #474: with EVERY candidate stuck-UNKNOWN, total re-poll
    sleep is capped at the budget no matter how many PRs there are. budget=8s,
    backoff=2s over 4 all-UNKNOWN PRs -> total sleep == 8s (== budget), never the
    unbounded 4*3*2 == 24s it would be without the cap."""
    spent, _total, per_pr = _run_retry_budget(4, retries="3", backoff="2", budget="8")
    assert spent == 8               # exactly the budget, not a byte over
    assert spent <= 8               # invariant restated: never exceeds budget
    assert len(per_pr) == 4


def test_budget_spent_makes_later_prs_skip_without_sleeping():
    """Once the budget is exhausted, subsequent UNKNOWN PRs do their single
    initial fetch and skip -- exactly 1 fetch each, no re-poll. Proves the cap is
    GLOBAL (shared across PRs), not reset per PR."""
    spent, _total, per_pr = _run_retry_budget(4, retries="3", backoff="2", budget="8")
    # PR1 exhausts its per-PR retries (4 fetches, 3 sleeps -> 6s), PR2 spends the
    # last 2s (2 fetches, 1 sleep), then PR3/PR4 are shut out at 1 fetch each.
    assert per_pr == [4, 2, 1, 1]
    assert spent == 8


def test_budget_untouched_when_all_resolve_first_read():
    """No PR is UNKNOWN -> the budget is never drawn down: 1 fetch per PR, zero
    sleep spent. The cap must not penalize the common all-clean tick."""
    spent, total, per_pr = _run_retry_budget(
        5, retries="3", backoff="2", budget="8", mergeable="MERGEABLE"
    )
    assert spent == 0
    assert total == 5
    assert per_pr == [1, 1, 1, 1, 1]
