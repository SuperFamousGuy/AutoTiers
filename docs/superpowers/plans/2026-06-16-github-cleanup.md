# github-cleanup Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `gh`-based skill, `github-cleanup`, that deletes merged branches (remote + local) and closes done/duplicate/stale issues, gated behind a single dry-run-then-batch approval.

**Architecture:** A single `SKILL.md` of prose + copy-paste `gh`/`git` command blocks, in the same family as the existing `resolve-pr-comments` and `fix-pr-checks` skills. Behavior is specified up front as eval scenarios in `evals/evals.json`. Verification is twofold: (1) every read-only scan command is smoke-run live against the AutoTiers repo to prove it returns sane output, and (2) every bash block is `shellcheck`-clean.

**Tech Stack:** Markdown, `gh` CLI, `git`, `jq`/`python3` for JSON, `shellcheck` for verification.

---

## Important context for the implementer

- **Skill location:** `.claude/skills/github-cleanup/`, relative to the repo root. This repo versions its skills in-tree under `.claude/skills/` (next to `resolve-pr-comments` and `fix-pr-checks`), so the skill IS committed to the repo like any other file. All paths in this plan are repo-relative; run commands from the repo root (`cd "$(git rev-parse --show-toplevel)"`).
- **Plan/spec location:** the design spec is `docs/superpowers/specs/2026-06-16-github-cleanup-design.md` inside the repo. Read it before starting.
- **The skill is prose, not a program.** There is no application to run. "Tests" for a skill are: eval scenarios (define intended behavior), `shellcheck` on the embedded bash (catch syntax errors), and live smoke-runs of the *read-only* commands against a real repo (prove the commands actually work). NEVER run the destructive commands (branch delete / issue close) during implementation.
- **Frontmatter contract** (match the sibling skills exactly): `name`, `description`, `when_to_use` keys, all on the top YAML block.
- **JSON parsing:** `gh`'s built-in `-q/--jq` flag does NOT require the standalone `jq` binary, so `gh ... --jq` works regardless. Only a raw pipe into `jq` needs the binary — and `jq` is not installed on this machine, so any such step (and the SKILL.md itself) must use a `python3 -c` fallback, exactly like `resolve-pr-comments` does.

## File Structure

- Create: `.claude/skills/github-cleanup/SKILL.md` — the whole skill (frontmatter + 6 stages + summary + failure modes). Built up section by section across Tasks 2–7.
- Create: `.claude/skills/github-cleanup/evals/evals.json` — scenario prompts + expected outputs. Task 1.
- Verification scratch: a temp file holding extracted bash for `shellcheck`. Task 7. Not committed.

Because the skill is one cohesive document, tasks append sections to the same `SKILL.md` in stage order. Each task ends by smoke-testing the read-only commands it introduced. All skill and doc files are committed to the repo as a normal change.

---

### Task 1: Scaffold + eval scenarios (behavior-first)

**Files:**
- Create: `.claude/skills/github-cleanup/evals/evals.json`

- [ ] **Step 1: Create the skill directory**

```bash
cd "$(git rev-parse --show-toplevel)"
mkdir -p .claude/skills/github-cleanup/evals
```

The `.claude/skills/` tree is part of this repo (the sibling skills are committed there). The skill files are committed alongside the plan/spec docs as a normal repo change — there is no separate VCS concern.

- [ ] **Step 2: Write the eval scenarios**

These define what "done" means for the skill — write them before the prose, then make the prose satisfy them.

Create `.claude/skills/github-cleanup/evals/evals.json`:

```json
{
  "skill_name": "github-cleanup",
  "evals": [
    {
      "id": 1,
      "prompt": "Clean up this repo's GitHub — kill the merged branches and close any issues that are already done.",
      "expected_output": "Skill infers owner/repo, scans for merged remote branches (union of merged-PR head branches and branches contained in the default branch), excludes default/protected/open-PR branches, finds local prune candidates, detects fixed-by-merged-PR issues, prints ONE dry-run plan table with action/target/reason/confidence columns, waits for a single batch approval, then executes and prints a summary. No destructive action before approval.",
      "files": []
    },
    {
      "id": 2,
      "prompt": "tidy up github, also look for duplicate and stale issues, stale meaning older than 60 days",
      "expected_output": "Skill runs with --stale-days 60, includes the duplicate-by-similarity (low confidence) and stale (low confidence, pinned issues skipped) detectors alongside branch cleanup and fixed-by-PR issues, presents the combined dry-run plan, batch-approves, executes, summarizes skips.",
      "files": []
    },
    {
      "id": 3,
      "prompt": "delete merged branches only, leave the issues alone",
      "expected_output": "Skill runs with --skip-issues, scans and deletes only merged remote branches plus local prune candidates after the single approval, never touches issues, reports a branches-only summary.",
      "files": []
    },
    {
      "id": 4,
      "prompt": "github-cleanup but don't actually delete anything yet, I just want to see what it would do",
      "expected_output": "Skill performs the scan and prints the dry-run plan table, then stops at the approval gate without executing anything when the user does not approve. Confirms nothing was changed.",
      "files": []
    }
  ]
}
```

- [ ] **Step 3: Validate the JSON parses**

Run: `python3 -c "import json; print(len(json.load(open('.claude/skills/github-cleanup/evals/evals.json'))['evals']), 'evals OK')"`
Expected: `4 evals OK`

- [ ] **Step 4: Commit the eval scenarios**

```bash
git add .claude/skills/github-cleanup/evals/evals.json
git commit -m "test(skills): add github-cleanup eval scenarios"
```

---

### Task 2: Frontmatter + Preflight + Branch scan

**Files:**
- Create: `.claude/skills/github-cleanup/SKILL.md`

- [ ] **Step 1: Write the frontmatter and intro**

Create `.claude/skills/github-cleanup/SKILL.md` with:

````markdown
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

## Stage 2: Branch scan

Goal: remote branches fully merged into the default branch, plus local branches
safe to prune. Nothing is deleted in this stage — only collected.

**2a. List live remote branches:**

```bash
gh api repos/$OWNER/$REPO/branches --paginate --jq '.[].name'
```

**2b. Merged-PR head branches** (catches squash-merges, which break the
ancestor check in 2c):

```bash
gh pr list --state merged --json headRefName,number --limit 200
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
git branch --merged "$DEFAULT_BRANCH" --format '%(refname:short)'
# drop the current branch and $DEFAULT_BRANCH from this list
```

Record each branch with a reason: `merged PR #N` (from 2b) or
`contained in $DEFAULT_BRANCH` (from 2c).
````

- [ ] **Step 2: Smoke-test the read-only branch commands against AutoTiers**

These are safe (read-only). Run from the AutoTiers repo to prove they work.
Expected: each returns without error and produces plausible output.

```bash
cd "$(git rev-parse --show-toplevel)"
gh repo view --json owner,name,defaultBranchRef
gh pr list --state merged --json headRefName,number --limit 5
gh api repos/$(gh repo view --json owner --jq .owner.login)/$(gh repo view --json name --jq .name)/branches --paginate --jq '.[].name' | head
git branch --merged main --format '%(refname:short)'
```

Expected: owner/name/default branch printed; a short list of merged-PR branch names; a list of remote branch names; local merged branches. If `jq` errors ("command not found"), confirm the `python3` fallback in the frontmatter intro works instead.

- [ ] **Step 3: Commit the branch-scan stage**

```bash
git add .claude/skills/github-cleanup/SKILL.md
git commit -m "feat(skills): github-cleanup preflight + branch scan"
```

---

### Task 3: Issue scan — three detectors

**Files:**
- Modify: `.claude/skills/github-cleanup/SKILL.md` (append Stage 3)

- [ ] **Step 1: Append the issue-scan stage**

Append to `SKILL.md`:

````markdown
## Stage 3: Issue scan (skip entirely if `--skip-issues`)

Three detectors. Each issue gets a **confidence** tag so the user can veto the
low-confidence rows in the single plan. If an issue is caught by more than one
detector, keep the highest-confidence hit and list it once.

**3a. Fixed-by-merged-PR — confidence: high**

```bash
gh pr list --state merged --json number,title,body --limit 200
```

Scan each PR's title+body for closing keywords (case-insensitive):

```
\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#(\d+)
```

Collect the referenced issue numbers, then keep only those still open:

```bash
gh issue view <N> --json state,number --jq '.state'   # keep if "OPEN"
```

Reason: `resolved by #<pr>`.

**3b. Duplicate by similarity — confidence: low**

```bash
gh issue list --state open --json number,title,body --limit 300
```

Normalize titles (lowercase, strip punctuation, tokenize) and cluster by
title-token Jaccard overlap (threshold ~0.6; use body only to break ties).
For each near-duplicate pair, propose closing the **newer** issue, pointing at
the older one. Always low confidence — the user eyeballs these in the plan.
Reason: `duplicate of #<older>`.

**3c. Stale — confidence: low**

```bash
gh issue list --state open --json number,title,updatedAt,isPinned --limit 300
```

Flag issues whose `updatedAt` is older than `--stale-days` (default 90).
**Skip pinned issues** (`isPinned == true`). Reason: `no activity since <date>`.
````

- [ ] **Step 2: Smoke-test the read-only issue commands against AutoTiers**

```bash
cd "$(git rev-parse --show-toplevel)"
gh pr list --state merged --json number,title,body --limit 3
gh issue list --state open --json number,title,updatedAt,isPinned --limit 5
```

Expected: merged PRs with bodies (verify the closing-keyword regex would match e.g. a "closes #88" body if present); open issues with `updatedAt` + `isPinned` fields present. No errors.

- [ ] **Step 3: Mark complete.**

---

### Task 4: Dry-run plan table (the approval gate)

**Files:**
- Modify: `.claude/skills/github-cleanup/SKILL.md` (append Stage 4)

- [ ] **Step 1: Append the dry-run plan stage**

````markdown
## Stage 4: Dry-run plan — STOP and get ONE approval

Print a single table covering branches and issues together. Do not split by
category; do not ask per item.

```
action                | target        | reason                        | confidence
----------------------|---------------|-------------------------------|------------
delete remote branch  | feat/old-x    | merged PR #210                | high
delete local branch   | feat/old-x    | merged into default branch    | high
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
````

- [ ] **Step 2: Verify the gate language is unambiguous**

Re-read the Stage 4 text. Confirm it states (a) one table, (b) one approval, (c) nothing destructive before approval. No command to run — this is a prose check.

- [ ] **Step 3: Mark complete.**

---

### Task 5: Execute + Summary

**Files:**
- Modify: `.claude/skills/github-cleanup/SKILL.md` (append Stages 5 & 6 + safety invariants)

- [ ] **Step 1: Append execute, summary, and safety sections**

````markdown
## Stage 5: Execute (only after approval)

Run each action defensively — wrap so one failure (branch already gone, issue
already closed) is recorded and the run continues to the next item.

- Delete remote branch:
  ```bash
  gh api -X DELETE repos/$OWNER/$REPO/git/refs/heads/<branch>
  ```
- Delete local branch (prune already ran in Stage 2e):
  ```bash
  git branch -d <branch>   # safe delete; refuses if not actually merged
  ```
- Close a resolved issue:
  ```bash
  gh issue close <N> -c "Resolved by #<pr>."
  ```
- Close a duplicate:
  ```bash
  gh issue close <N> -c "Duplicate of #<older>." -r "not planned"
  ```
- Close a stale issue:
  ```bash
  gh issue close <N> -c "Closing as stale — no activity since <date>. Reopen if still relevant."
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
````

- [ ] **Step 2: Mark complete.**

---

### Task 6: Common failure modes

**Files:**
- Modify: `.claude/skills/github-cleanup/SKILL.md` (append failure-modes section)

- [ ] **Step 1: Append the failure-modes section**

Match the `resolve-pr-comments` precedent of a concrete gotcha list.

````markdown
## Common failure modes

- **Squash-merged branches look unmerged:** their commits are not ancestors of
  the default branch, so the Stage 2c `compare` check returns `diverged`. This
  is exactly why Stage 2b (merged-PR head branches) is unioned in — do not drop it.
- **`git branch -d` refuses a branch:** that means git does not consider it
  merged into the *currently checked-out* branch. Check `git branch --merged $DEFAULT_BRANCH` was computed against the default branch, not the current one.
- **Deleting a remote branch returns 422 "reference does not exist":** it was
  already deleted (e.g. GitHub's auto-delete-on-merge). Record as skipped/already-gone, continue.
- **Closing-keyword false positives:** `"see #12 for context"` is not a close;
  only the listed keywords (`close/fix/resolve` + variants) count. Do not close
  issues merely *mentioned* in a PR.
- **An issue closed by GitHub auto-close still shows in 3a:** always re-check
  `state == OPEN` right before proposing a close — the merged-PR scan can name
  issues that GitHub already closed.
- **Don't rely on the standalone `jq` binary:** `gh`'s built-in `-q/--jq`
  flag works without it, but a raw pipe into `jq` does not — and `jq` may be
  absent. Parse those with `python3 -c "import sys,json; ..."`, as shown in Stage 1.
- **Pinned issue swept as stale:** the stale detector MUST filter
  `isPinned == true`; pinned issues are intentionally long-lived.
- **`--paginate` matters:** repos with >30 branches will silently truncate
  without `--paginate` on the `gh api .../branches` call, leaving live branches
  unseen (and so never cleaned).
````

- [ ] **Step 2: Mark complete.**

---

### Task 7: shellcheck pass + discoverability + self-review

**Files:**
- Read: `.claude/skills/github-cleanup/SKILL.md`

- [ ] **Step 1: Extract and shellcheck every bash block**

Pull the fenced `bash` blocks out of the finished SKILL.md and lint them for
syntax errors. The `$OWNER` / `<branch>` placeholders will trip "undefined"
style warnings — those are fine; you are looking for genuine syntax errors
(unbalanced quotes, bad redirects).

```bash
python3 - <<'PY' > /tmp/github-cleanup-blocks.sh
import re
src = open('.claude/skills/github-cleanup/SKILL.md').read()
for block in re.findall(r'```bash\n(.*?)```', src, re.S):
    print(block)
PY
shellcheck -S error /tmp/github-cleanup-blocks.sh || true
```

Expected: no `error`-severity findings. If `shellcheck` is not installed, run
`bash -n /tmp/github-cleanup-blocks.sh` instead to at least catch syntax errors.
Fix any real syntax errors in SKILL.md, not in the temp file.

- [ ] **Step 2: Verify the skill is discoverable**

Confirm the frontmatter parses and the skill shows up. From a fresh skill listing
(restart the Claude Code session or re-scan), the `github-cleanup` skill should
appear with its `when_to_use` text. At minimum, validate the YAML frontmatter:

```bash
python3 - <<'PY'
import re
src = open('.claude/skills/github-cleanup/SKILL.md').read()
m = re.match(r'^---\n(.*?)\n---\n', src, re.S)
assert m, "no frontmatter block"
fm = m.group(1)
for key in ('name:', 'description:', 'when_to_use:'):
    assert key in fm, f"missing {key}"
print("frontmatter OK")
PY
```

Expected: `frontmatter OK`.

- [ ] **Step 3: Self-review against the spec**

Open `docs/superpowers/specs/2026-06-16-github-cleanup-design.md` and confirm
every section maps to skill content:
- Stage 1–6 present and in order
- 3 issue detectors with correct confidence tags
- single dry-run-then-batch approval (no per-item/per-category prompting leaked in)
- all 7 safety invariants present
- args `--stale-days` / `--skip-issues` / `--skip-branches` documented

Fix any gaps inline.

- [ ] **Step 4: Commit any final fixes**

Commit any spec tweaks or skill fixes made during the self-review (the
per-task commits above already cover the bulk of the skill):

```bash
cd "$(git rev-parse --show-toplevel)"
git add .claude/skills/github-cleanup/ docs/superpowers/
git commit -m "docs: github-cleanup skill final review fixes"
```

---

## Self-Review (plan author)

**Spec coverage:** Stage 1 → Task 2; branch scan (2a–2e) → Task 2; 3 issue detectors → Task 3; dry-run plan → Task 4; execute + summary + invariants → Task 5; failure modes (new, additive) → Task 6; args documented in Task 2 intro; testing via evals (Task 1) + shellcheck/smoke (Tasks 2,3,7). All spec sections covered.

**Placeholder scan:** `<branch>`, `<N>`, `<pr>`, `<older>` are intentional skill-template placeholders shown to the end user, not plan gaps — each is explained where it appears. No "TBD"/"TODO" in actionable steps.

**Type/name consistency:** `$OWNER`/`$REPO`/`$DEFAULT_BRANCH` used consistently from Stage 1 capture through Stages 2–5. Confidence tags (`high`/`low`) consistent between Task 3 detectors and the Task 4 plan table. `git branch -d` (never `-D`) consistent between Stage 5 and invariant 4.
