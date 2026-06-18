"""Regression guard for the claude-implement-issue auto-implement workflow.

Issue #352 proved that putting `PR_AUTHOR_PAT` only on the `actions/checkout`
step (PR #350) does NOT let the pipeline push changes under `.github/workflows/`:
`claude-code-action` re-seats git's persisted credential with its own minted
OIDC App installation token, and GitHub blocks App tokens from writing workflow
files. The fix moves the push into a dedicated step that re-asserts the PAT on
git's transport, after the action, and tells the agent to commit-but-not-push.

These tests pin the structural invariants of that fix so a future edit cannot
silently regress back to the broken arrangement. They assert against the raw
workflow text (no YAML parser) so the suite needs no extra dependency.
"""

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "claude-implement-issue.yml"
)

TEXT = WORKFLOW.read_text()


def test_checkout_persists_pat():
    """Checkout still carries the PAT (kept for pre-action git ops)."""
    assert "token: ${{ secrets.PR_AUTHOR_PAT }}" in TEXT


def test_contents_write_permission_present():
    """Non-workflow auto-implement pushes still need contents:write."""
    assert "contents: write" in TEXT


def test_agent_is_told_to_commit_but_not_push():
    """The prompt must NOT instruct the agent to push the branch itself."""
    assert "Do NOT push" in TEXT
    # Guard against the old wording that had the agent push the branch.
    assert "and push it." not in TEXT


def test_dedicated_push_step_exists_and_is_gated():
    """A dedicated push step, gated like Open-PR so blocker runs push nothing."""
    assert "name: Push implemented branch" in TEXT
    assert "PAT: ${{ secrets.PR_AUTHOR_PAT }}" in TEXT
    # The gate appears for both the push and the Open-PR step.
    assert TEXT.count("if: hashFiles('.pr-body.md') != ''") >= 2


def test_push_uses_correct_git_dash_c_ordering():
    """`-c` is a git-level option and MUST precede the `push` subcommand.

    `git push -c ...` fails with "unknown switch `c`" (the original bug). Pin the
    exact `git -c <config> push` ordering so it cannot regress, and require the
    extraheader clear + PAT-in-URL transport re-seating.
    """
    assert "git -c http.https://github.com/.extraheader= push" in TEXT
    # The broken ordering must never reappear.
    assert "git push \\\n            -c " not in TEXT
    assert "x-access-token:${PAT}" in TEXT, "PAT must authenticate the push"
    assert "HEAD:refs/heads/${BRANCH}" in TEXT


def test_push_runs_before_open_pr():
    """The branch must be on the remote before `gh pr create --head`."""
    assert TEXT.index("name: Push implemented branch") < TEXT.index(
        "name: Open pull request"
    )


def test_open_pr_step_authenticates_as_pat():
    """PR creation stays PAT-authed so Copilot's auto-review fires."""
    assert "GH_TOKEN: ${{ secrets.PR_AUTHOR_PAT }}" in TEXT
