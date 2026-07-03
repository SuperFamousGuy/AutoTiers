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
        set -uo pipefail
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
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
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
        set -uo pipefail
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
