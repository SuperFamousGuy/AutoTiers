"""Regression guard for the claude-address-copilot-review sweeper workflow.

PR #358 proved the sweeper could not land a Copilot fix that touches a file under
`.github/workflows/`: the agent's `git push` inside `claude-code-action` goes out
as the action's minted OIDC App installation token (the action re-seats git's
persisted credential AFTER `actions/checkout`), and GitHub blocks App tokens from
writing workflow files. PR #359 broadened the sweeper to ALL open PRs, so this
now fires on any PR whose Copilot fix edits a workflow file.

The fix mirrors the one already shipped for the auto-implement pipeline in
PR #353 (see test_implement_issue_workflow.py): the agent COMMITS but does NOT
push; a dedicated step re-asserts the PAT on git's transport and pushes; and a
SEPARATE step resolves the Copilot threads only AFTER the push lands (so a failed
push never leaves a thread resolved with no fix on the remote).

These tests pin the structural invariants of that fix so a future edit cannot
silently regress to the broken arrangement. They assert against the raw workflow
text (no YAML parser) so the suite needs no extra dependency.
"""

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "claude-address-copilot-review.yml"
)

TEXT = WORKFLOW.read_text()


def test_checkout_persists_pat():
    """Checkout still carries the PAT (kept for pre-action git ops)."""
    assert "token: ${{ secrets.PR_AUTHOR_PAT }}" in TEXT


def test_contents_write_permission_present():
    """Non-workflow pushes still need contents:write."""
    assert "contents: write" in TEXT


def test_agent_is_told_to_commit_but_not_push():
    """The address prompt must instruct commit-but-not-push, and must NOT tell
    the agent to push the branch itself."""
    assert "Do NOT push" in TEXT or "do NOT push" in TEXT
    # The old wording had the agent push to the existing branch from inside the
    # action — exactly the broken arrangement. It must not reappear.
    assert "push to the EXISTING branch" not in TEXT


def test_agent_is_told_not_to_resolve_in_address_step():
    """Threads must NOT be resolved inside the address step — resolution is
    deferred to a post-push step so a failed push never leaves a resolved thread
    with no fix on the remote (the silent-bad-state failure)."""
    assert "do NOT resolve any thread yet" in TEXT


def test_dedicated_push_step_exists_and_is_gated():
    """A dedicated push step, gated on the .addressed.flag sentinel so a
    suites-failed / no-fix run pushes nothing."""
    assert "name: Push addressed branch" in TEXT
    assert "PAT: ${{ secrets.PR_AUTHOR_PAT }}" in TEXT
    assert "hashFiles('.addressed.flag') != ''" in TEXT


def test_push_uses_correct_git_dash_c_ordering():
    """`-c` is a git-level option and MUST precede the `push` subcommand.

    `git push -c ...` fails with "unknown switch `c`". Pin the exact
    `git -c <config> push` ordering and require the extraheader clear (to drop
    the action's App-token header) + PAT-in-URL transport re-seating.
    """
    assert "git -c http.https://github.com/.extraheader= push" in TEXT
    # The broken ordering must never reappear.
    assert "git push \\\n            -c " not in TEXT
    assert "x-access-token:${PAT}" in TEXT, "PAT must authenticate the push"
    assert "HEAD:refs/heads/${REF}" in TEXT


def test_resolve_step_runs_after_push_and_only_on_success():
    """Threads are resolved in a dedicated step that runs AFTER the push and only
    when the push succeeded (if: success()), gated on the same sentinel."""
    assert "name: Resolve Copilot threads (after push)" in TEXT
    assert TEXT.index("name: Push addressed branch") < TEXT.index(
        "name: Resolve Copilot threads (after push)"
    )
    # The resolve step must be guarded by success() so a failed push short-circuits
    # it and leaves the threads open for the next cron tick.
    resolve_idx = TEXT.index("name: Resolve Copilot threads (after push)")
    resolve_block = TEXT[resolve_idx:resolve_idx + 400]
    assert "if: success()" in resolve_block
    assert "hashFiles('.addressed.flag') != ''" in resolve_block


def test_push_runs_before_resolve():
    """The fix must be on the remote before any thread is resolved."""
    assert TEXT.index("name: Push addressed branch") < TEXT.index(
        "name: Resolve Copilot threads (after push)"
    )


def test_pass_label_stamped_before_push():
    """Termination invariant: the pass label is stamped before the push that
    triggers Copilot's re-review, so the next cron tick sees the incremented
    count and stops at the cap."""
    assert TEXT.index("name: Stamp pass label (reserve budget)") < TEXT.index(
        "name: Push addressed branch"
    )


def test_agent_gh_calls_authenticate_as_pat():
    """The address agent's gh reply calls stay PAT-authed (Copilot-seated)."""
    assert "GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}" in TEXT


# --- bash resolve step (issue #361) -----------------------------------------
# The resolve step was a second claude-code-action whose only job was to call
# `resolveReviewThread` on already-replied Copilot threads — deterministic,
# scriptable work that does not need an agent or its subscription quota. These
# guards pin the plain-bash form so it cannot silently regress to a 2nd agent run.


def _resolve_block():
    """The text of the resolve step, from its name to end of file (it is the
    last step in the workflow)."""
    return TEXT[TEXT.index("name: Resolve Copilot threads (after push)") :]


def test_resolve_step_is_plain_bash_not_a_second_agent():
    """The resolve step must be a plain `run:` bash step, NOT a second
    claude-code-action invocation. Only the address step may use the action."""
    block = _resolve_block()
    assert "uses: anthropics/claude-code-action" not in block
    assert "run: |" in block
    # Exactly one agent invocation remains in the whole workflow (the address
    # step). If the resolve step regressed to a 2nd agent run, this would be 2.
    assert TEXT.count("uses: anthropics/claude-code-action@v1") == 1


def test_resolve_step_uses_resolvereviewthread_mutation_by_thread_id():
    """It resolves via the GraphQL `resolveReviewThread` mutation keyed on the
    thread node `id` (threadId), not a comment databaseId."""
    block = _resolve_block()
    assert "gh api graphql" in block
    assert "resolveReviewThread(input: { threadId: $threadId })" in block
    assert "-f threadId=" in block


def test_resolve_step_only_targets_replied_copilot_threads():
    """Only UNRESOLVED threads whose FIRST comment author is Copilot AND that
    already carry a reply (a non-Copilot comment) are resolved."""
    block = _resolve_block()
    assert "select(.isResolved == false)" in block
    # First comment author is one of the three Copilot logins.
    assert "copilot-pull-request-reviewer[bot]" in block
    # Carries a reply: at least one comment author is NOT Copilot.
    assert "length > 0" in block


def test_resolve_step_authenticates_as_pat():
    """The resolve step's gh calls run as PR_AUTHOR_PAT (Copilot-seated)."""
    block = _resolve_block()
    assert "GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}" in block
