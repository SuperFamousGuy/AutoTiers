---
name: github-cleanup
description: Tidy a GitHub repo end-to-end — delete merged branches (remote + local prune) and close issues that are resolved-by-a-merged-PR, duplicates, or stale. Builds one dry-run plan and waits for a single batch approval before any destructive action. Works in any repo with `gh` auth configured.
when_to_use: Invoke when the user says "clean up github", "tidy the repo", "delete merged branches", "close stale/duplicate issues", "prune branches", or any similar phrase asking to remove orphaned branches or close done/duplicate/stale issues.
---

# Cleaning up a GitHub repo

Deletes merged branches and closes done/duplicate/stale issues. Always presents
ONE dry-run plan and waits for a single batch approval before touching anything.

**Arguments (optional):**
- `--stale-days N` — age threshold for the stale-issue detector. Default `90`.
- `--skip-issues` — only clean branches.
- `--skip-branches` — only clean issues.

## Stage 1: Preflight

```bash
gh auth status
gh repo view --json owner,name,defaultBranchRef
git status   # warn the user if the working tree is dirty — Stage 2 prunes local branches
```

Capture `OWNER`, `REPO`, and `DEFAULT_BRANCH` (the `defaultBranchRef.name`) from
the `gh repo view` output. If `jq` is unavailable, parse with:

```bash
gh repo view --json owner,name,defaultBranchRef \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['owner']['login'], d['name'], d['defaultBranchRef']['name'])"
```

## Stage 2: Branch scan (skip entirely if `--skip-branches`)

Goal: remote branches fully merged into the default branch, plus local branches
safe to prune. Nothing is deleted in this stage — only collected.

**2a. List live remote branches:**

```bash
gh api repos/$OWNER/$REPO/branches --paginate --jq '.[].name'
```

**2b. Merged-PR head branches** (catches squash-merges, which break the
ancestor check in 2c):

```bash
# --limit caps results silently — set it well above the repo's merged-PR count,
# or old squash-merged branches (only catchable here) get skipped
gh pr list --state merged --json headRefName,number --limit 1000
```

**2c. Branches contained in the default branch** — for each live branch from 2a,
check whether its tip is already in the default branch:

```bash
# Branch names contain "/" (e.g. feat/foo). The compare endpoint reads
# BASE...HEAD as a single path segment, so the head ref's slashes MUST be
# URL-encoded or the request 404s / miscompares and the merged branch is missed.
branch_enc=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "<branch>")
gh api "repos/$OWNER/$REPO/compare/$DEFAULT_BRANCH...$branch_enc" --jq '.status'
# keep the branch when status is "identical" or "behind"
```

The set of merge-deletable remote branches is the **union** of 2b's head
branches and 2c's contained branches.

**2d. Exclusions — never propose these for deletion:**
- the default branch (`$DEFAULT_BRANCH`)
- protected branches:
  ```bash
  gh api repos/$OWNER/$REPO/branches --paginate --jq '.[] | select(.protected) | .name'
  ```
- branches with an open PR:
  ```bash
  gh pr list --state open --json headRefName --jq '.[].headRefName'
  ```

**2e. Local prune candidates:**

```bash
git fetch --prune
# Compare against the freshly-fetched remote tip, not a possibly-stale local
# $DEFAULT_BRANCH (which may not be checked out or pulled) — that ref can
# under- or over-prune.
git branch --merged "origin/$DEFAULT_BRANCH" --format '%(refname:short)'
# drop the current branch and $DEFAULT_BRANCH from this list
```

Record each branch with a reason: `merged PR #N` (from 2b) or
`contained in $DEFAULT_BRANCH` (from 2c).

## Stage 3: Issue scan (skip entirely if `--skip-issues`)

Three detectors. Each issue gets a **confidence** tag so the user can veto the
low-confidence rows in the single plan. If an issue is caught by more than one
detector, keep the highest-confidence hit and list it once.

**3a. Fixed-by-merged-PR — confidence: high**

```bash
# Raise --limit above the repo's merged-PR count; older PRs are dropped
# silently otherwise, and their closing-keyword references go undetected.
gh pr list --state merged --json number,title,body --limit 1000
```

Scan each PR's title+body for closing keywords (case-insensitive):

```
\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#(\d+)
```

Collect the referenced issue numbers, then keep only those still open:

```bash
gh issue view "<N>" --json state,number --jq '.state'   # keep if "OPEN"
```

Reason: `resolved by #<pr>`.

**3b. Duplicate by similarity — confidence: low**

```bash
# --limit caps silently; set it above the repo's open-issue count or
# duplicate detection only sees the first N and produces an incomplete plan.
gh issue list --state open --json number,title,body --limit 1000
```

Normalize titles (lowercase, strip punctuation, tokenize) and cluster by
title-token Jaccard overlap (threshold ~0.6; use body only to break ties).
For each near-duplicate pair, propose closing the **newer** issue, pointing at
the older one. Always low confidence — the user eyeballs these in the plan.
Reason: `duplicate of #<older>`.

**3c. Stale — confidence: low**

```bash
# --limit caps silently; set it above the repo's open-issue count or stale
# issues beyond the first N are missed, producing a surprising no-op run.
gh issue list --state open --json number,title,updatedAt,isPinned --limit 1000
```

Flag issues whose `updatedAt` is older than `--stale-days` (default 90).
**Skip pinned issues** (`isPinned == true`). Reason: `no activity since <date>`.

## Stage 4: Dry-run plan — STOP and get ONE approval

Print a single table covering branches and issues together. Do not split by
category; do not ask per item.

```
action                | target        | reason                        | confidence
----------------------|---------------|-------------------------------|------------
delete remote branch  | feat/old-x    | merged PR #210                | high
delete local branch   | feat/old-x    | merged into main              | high
close issue           | #88           | resolved by #284              | high
close issue (dup)     | #91 -> #74    | duplicate of #74              | low
close issue (stale)   | #45           | no activity since 2026-01-10  | low
```

Then ask the user to approve the **entire** plan in one go. Examples of the
prompt: *"Approve this plan? I'll delete N branches and close M issues."*

**Hard gate:** perform NO deletion or close until the user approves. If the user
declines or only wants a subset, stop and report that nothing was changed (they
can re-run with `--skip-issues` / `--skip-branches` or a different
`--stale-days`).

## Stage 5: Execute (only after approval)

Run each action defensively — wrap so one failure (branch already gone, issue
already closed) is recorded and the run continues to the next item.

- Delete remote branch:
  ```bash
  gh api -X DELETE "repos/$OWNER/$REPO/git/refs/heads/<branch>"
  ```
- Delete local branch (prune already ran in Stage 2e):
  ```bash
  git branch -d "<branch>"   # safe delete; refuses if not actually merged
  ```
- Close a resolved issue:
  ```bash
  gh issue close "<N>" -c "Resolved by #<pr>."
  ```
- Close a duplicate:
  ```bash
  gh issue close "<N>" -c "Duplicate of #<older>." -r "not planned"
  ```
- Close a stale issue:
  ```bash
  gh issue close "<N>" -c "Closing as stale — no activity since <date>. Reopen if still relevant."
  ```

## Stage 6: Summary

Print a final table: what was deleted/closed, and what was **skipped** with the
reason (protected branch, open PR, pinned issue, API error).

```
result   | item                 | detail
---------|----------------------|----------------------------------
deleted  | branch feat/old-x    | remote + local
closed   | issue #88            | resolved by #284
closed   | issue #45            | stale (no activity since 2026-01-10)
skipped  | branch release/v2    | protected
skipped  | issue #12            | pinned (stale detector)
failed   | branch feat/gone     | 422 reference does not exist
```

If nothing matched, say so and stop.

## Safety invariants

1. The dry-run plan is mandatory; nothing destructive happens before the single approval.
2. The default branch and protected branches are never proposed for deletion.
3. Branches with an open PR are never proposed.
4. Local deletes use `git branch -d` (merge-safe), never `-D`.
5. Duplicate and stale detection are heuristics → always low-confidence and always visible in the plan for veto.
6. Pinned issues are exempt from the stale detector.
7. A dirty working tree is flagged in Stage 1 before the local prune.

## Common failure modes

- **Squash-merged branches look unmerged:** their commits are not ancestors of
  the default branch, so the Stage 2c `compare` check returns `diverged`. This
  is exactly why Stage 2b (merged-PR head branches) is unioned in — do not drop it.
- **`git branch -d` refuses a branch:** that means git does not consider it
  merged into the *currently checked-out* branch. Check `git branch --merged origin/$DEFAULT_BRANCH` was computed against the remote default tip, not the current one.
- **Deleting a remote branch returns 422 "reference does not exist":** it was
  already deleted (e.g. GitHub's auto-delete-on-merge). Record as skipped/already-gone, continue.
- **Closing-keyword false positives:** `"see #12 for context"` is not a close;
  only the listed keywords (`close/fix/resolve` + variants) count. Do not close
  issues merely *mentioned* in a PR.
- **An issue closed by GitHub auto-close still shows in 3a:** always re-check
  `state == OPEN` right before proposing a close — the merged-PR scan can name
  issues that GitHub already closed.
- **`jq` not installed:** parse JSON with `python3 -c "import sys,json; ..."`
  instead, as shown in Stage 1.
- **Pinned issue swept as stale:** the stale detector MUST filter
  `isPinned == true`; pinned issues are intentionally long-lived.
- **`--paginate` matters:** repos with >30 branches will silently truncate
  without `--paginate` on the `gh api .../branches` call, leaving live branches
  unseen (and so never cleaned).
