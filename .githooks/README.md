# Git hooks

Project-scoped hooks that catch classes of mistakes the repo has actually shipped.

## Activate (one-time per clone, re-run after the hook source changes)

```bash
./.githooks/setup.sh
```

The setup script **copies** each hook from `.githooks/` into `.git/hooks/` and marks it executable. The copy install (rather than `core.hooksPath`) is deliberate: `core.hooksPath` only finds the hook when the current branch's working tree contains it, so branches that diverged before the hook landed get no protection. The copy lives in the git dir, which is per-clone rather than per-branch, so every branch in this clone is covered including legacy ones.

Re-run the script after pulling updates to `.githooks/*` — the `.git/hooks/` copies don't auto-refresh.

## Active hooks

### `pre-push`

Refuses to push commits to a branch whose PR has already been **MERGED** or **CLOSED** on GitHub. Without this, a habit of "push the follow-up commits" produces orphan branches and confusing review history — every push to a dead branch requires moving the work to a new branch and force-cleaning the remote.

Requires the [`gh` CLI](https://cli.github.com/) authenticated against this repo. If `gh` is missing or the network is down, the hook fails open (allows the push) and prints a warning — better to ship one bad push than to block legit work offline.

To bypass deliberately (rarely correct):

```bash
git push --no-verify
```

## Adding a new hook

1. Drop the script in this directory with the standard git hook name (`pre-commit`, `pre-push`, `commit-msg`, etc.).
2. `chmod +x <hook-name>`.
3. Update this README with what it does and why.
4. Anyone already set up needs to re-run `./.githooks/setup.sh` to copy the new hook into their `.git/hooks/`.
