# github-cleanup skill — design

**Date:** 2026-06-16
**Status:** Approved, pre-implementation

## Purpose

A `gh`-based workflow skill that tidies a GitHub repo: deletes merged branches
(remote + local) and closes open issues that are demonstrably done, duplicated,
or stale. It always presents a single dry-run plan and waits for one batch
approval before any destructive action.

It belongs to the same family as `resolve-pr-comments` and `fix-pr-checks`:
step-by-step `gh`/`git` commands, a triage/plan table, an end-of-run summary.
Works in any repo with `gh` auth configured.

## Scope

- **Repo:** current repo only. Owner/repo inferred via `gh repo view --json owner,name`.
- **One repo per run.** No multi-repo, no named-repo argument.
- **Out of scope:** PRs (closing/reopening), tags, releases, milestones, labels,
  protected-branch changes, anything that pushes commits.

## Arguments

- `--stale-days N` — age threshold for the stale-issue detector. Default `90`.
- `--skip-issues` — branches only.
- `--skip-branches` — issues only.

## Flow

```
scan → build plan → print dry-run plan table → ONE batch approval → execute all → summary table
```

Nothing destructive happens before approval. If the user declines, the skill
stops having changed nothing.

## Stage 1 — Preflight

```bash
gh repo view --json owner,name,defaultBranchRef
gh auth status
git status            # warn if dirty; local prune touches the working clone
```

Capture: `OWNER`, `REPO`, `DEFAULT_BRANCH`.

## Stage 2 — Branch scan

Goal: remote branches that are fully merged into the default branch, plus the
local branches safe to prune.

**Merged remote branches** = union of two signals (the union catches
squash-merges, which break ancestor-based detection):

1. Head branches of merged PRs:
   `gh pr list --state merged --json headRefName,number --limit 200`
2. Branches whose tip is contained in the default branch:
   for each live branch, `gh api "repos/$OWNER/$REPO/compare/$DEFAULT_BRANCH...$branch_enc" --jq .status`
   → keep when status is `identical` or `behind`. The head ref **must** be
   URL-encoded (`/` → `%2F`, e.g. via `urllib.parse.quote`) — the compare
   endpoint reads `BASE...HEAD` as one path segment, so an un-encoded
   `feat/foo` 404s / miscompares and the merged branch is silently missed.

Live branch list: `gh api repos/$OWNER/$REPO/branches --paginate --jq '.[].name'`.

**Exclusions (never propose for deletion):**
- the default branch
- protected branches: `gh api repos/$OWNER/$REPO/branches --paginate --jq '.[]|select(.protected)|.name'`
- any branch that currently has an **open** PR:
  `gh pr list --state open --json headRefName --jq '.[].headRefName'`

**Local prune candidates:**
```bash
git fetch --prune
git branch --merged "$DEFAULT_BRANCH" --format '%(refname:short)'
```
minus the current branch and the default branch. These are deleted with
`git branch -d` (safe delete; refuses if not actually merged).

Each branch row records a reason: `merged PR #N` or `contained in $DEFAULT_BRANCH`.

## Stage 3 — Issue scan (3 detectors)

Each detected issue carries a **confidence** tag so the user can scan the plan
and veto low-confidence rows before the single approval.

**3a. Fixed-by-merged-PR — confidence: high**
- Pull merged PRs: `gh pr list --state merged --json number,title,body --limit 200`.
- Regex closing keywords against title+body, case-insensitive:
  `\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#(\d+)`
- Collect referenced issue numbers, keep those still open
  (`gh issue view N --json state,number` → `state == OPEN`).
- Reason: `resolved by #<pr>`.

**3b. Duplicate by similarity — confidence: low**
- `gh issue list --state open --json number,title,body --limit 300`.
- Normalize titles (lowercase, strip punctuation, tokenize) and cluster by
  token-overlap (Jaccard over title tokens, threshold ~0.6; body used as a
  tiebreaker only).
- Propose the newer issue of each pair as the duplicate, pointing at the older
  (`Duplicate of #M`). Always shown low-confidence — the user eyeballs it.

**3c. Stale — confidence: low**
- `gh issue list --state open --json number,title,updatedAt,isPinned --limit 300`.
- Flag issues with `updatedAt` older than `--stale-days` (default 90).
- **Skip pinned issues.**
- Reason: `no activity since <date>`.

If the same issue is caught by more than one detector, the highest-confidence
detector wins and it appears once.

## Stage 4 — Dry-run plan

Print a single table covering branches and issues together:

| action | target | reason | confidence |
|--------|--------|--------|------------|
| delete remote branch | `feat/old-x` | merged PR #210 | high |
| delete local branch | `feat/old-x` | merged into default branch | high |
| close issue | #88 | resolved by #284 | high |
| close issue (dup) | #91 → #74 | duplicate of #74 | low |
| close issue (stale) | #45 | no activity since 2026-01-10 | low |

Then ask for one approval to execute the whole plan. No per-item, no
per-category prompting.

## Stage 5 — Execute (only after approval)

- Remote branch: `gh api -X DELETE repos/$OWNER/$REPO/git/refs/heads/<branch>`
- Local branch: `git branch -d <branch>` (prune already ran in Stage 2)
- Fixed issue: `gh issue close N -c "Resolved by #<pr>."`
- Duplicate: `gh issue close N -c "Duplicate of #M." -r "not planned"`
- Stale: `gh issue close N -c "Closing as stale — no activity since <date>. Reopen if still relevant."`

Each action wrapped so one failure (e.g. a branch already deleted, an issue
already closed) is recorded and the run continues.

## Stage 6 — Summary

Final table: what was deleted/closed, and what was **skipped** with the reason
(protected branch, open PR, pinned issue, API error). Mirrors the
`resolve-pr-comments` end-of-run summary style.

## Safety invariants

1. Dry-run plan is mandatory; nothing destructive before the single approval.
2. Default and protected branches are never proposed.
3. Branches with an open PR are never proposed.
4. Local deletes use `git branch -d` (merge-safe), never `-D`.
5. Duplicate and stale detection are heuristics → always low-confidence,
   always visible in the plan for veto.
6. Pinned issues are exempt from the stale detector.
7. A dirty working tree is warned about before local prune.

## Testing

Following the `fix-pr-checks` precedent (it ships an `evals/` dir), the skill
gets an `evals/` directory with scenario fixtures:
- merged-branch detection incl. a squash-merged branch (ancestor check fails,
  PR-head check catches it)
- protected / open-PR / default branch exclusions hold
- fixed-by-PR regex matches each closing keyword variant
- stale threshold honors `--stale-days` and skips pinned issues
- dry-run produces a plan but performs no mutation (assert no `DELETE`/`close`
  calls fire before approval)
