"""Regression guard for the claude-implement-issue auto-implement workflow.

Issue #352 proved that putting `PR_AUTHOR_PAT` only on the `actions/checkout`
step (PR #350) does NOT let the pipeline push changes under `.github/workflows/`:
`claude-code-action` re-seats git's persisted credential with its own minted
OIDC App installation token, and GitHub blocks App tokens from writing workflow
files. The fix moves the push into a dedicated step that re-asserts the PAT on
git's transport, after the action, and tells the agent to commit-but-not-push.

These tests pin the structural invariants of that fix so a future edit cannot
silently regress back to the broken arrangement.
"""

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "claude-implement-issue.yml"
)


def _load():
    return yaml.safe_load(WORKFLOW.read_text())


def _steps():
    wf = _load()
    return wf["jobs"]["implement"]["steps"]


def _step(name_substr):
    for step in _steps():
        if name_substr in (step.get("name") or "") or name_substr in (
            step.get("uses") or ""
        ):
            return step
    raise AssertionError(f"no step matching {name_substr!r}")


def test_checkout_persists_pat():
    """Checkout still carries the PAT (kept for pre-action git ops)."""
    step = _step("actions/checkout")
    assert step["with"]["token"] == "${{ secrets.PR_AUTHOR_PAT }}"


def test_contents_write_permission_present():
    """Non-workflow auto-implement pushes still need contents:write."""
    wf = _load()
    assert wf["permissions"]["contents"] == "write"


def test_agent_is_told_to_commit_but_not_push():
    """The prompt must NOT instruct the agent to push the branch itself."""
    prompt = _step("Implement issue")["with"]["prompt"]
    assert "Do NOT push" in prompt
    # Guard against the old wording that had the agent push.
    assert "commit the work,\n" not in prompt and "and push it." not in prompt


def test_dedicated_push_step_uses_pat_on_transport():
    """A dedicated push step must re-assert the PAT on git's transport.

    `GH_TOKEN` is not enough: it steers `gh`, not raw `git push`. The step must
    clear the action's persisted App-token header and carry the PAT in the URL.
    """
    step = _step("Push implemented branch")
    assert step["if"] == "hashFiles('.pr-body.md') != ''"
    assert step["env"]["PAT"] == "${{ secrets.PR_AUTHOR_PAT }}"
    run = step["run"]
    assert "extraheader=" in run, "must clear the action's persisted auth header"
    assert "x-access-token:${PAT}" in run, "PAT must authenticate the push"
    assert "HEAD:refs/heads/" in run


def test_push_runs_before_open_pr():
    """The branch must be on the remote before `gh pr create --head`."""
    names = [s.get("name") for s in _steps()]
    assert names.index("Push implemented branch") < names.index("Open pull request")


def test_open_pr_step_authenticates_as_pat():
    """PR creation stays PAT-authed so Copilot's auto-review fires."""
    step = _step("Open pull request")
    assert step["if"] == "hashFiles('.pr-body.md') != ''"
    assert step["env"]["GH_TOKEN"] == "${{ secrets.PR_AUTHOR_PAT }}"
