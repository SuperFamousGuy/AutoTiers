---
name: learn-from-experience
description: Post-session retrospective that reviews what happened, cleans up artifacts, and improves the system configuration (agents, skills, memory, SDLC). ALWAYS invoke when the user says "learn from this", "capture lessons", "retrospective", "don't let this happen again", "improve the operation", or "learn from experience". Also invoke when stale worktrees, orphaned branches, or outdated memory entries are discovered, or at the end of any significant multi-agent session.
---

# Learn from Experience

After a session — especially one with errors, churn, or visible waste — run this retrospective to make the system smarter for next time. The goal: reduce the probability of the same class of error recurring, not just fix the instance.

## Step 1 — Survey the scene

Gather facts before drawing conclusions.

```bash
git log --oneline -20
git worktree list
git status
ls .claude/worktrees/ 2>/dev/null
```

Also read:
- `MEMORY.md` index
- Any skill or agent file that was involved in recent work
- Recent session transcript context (what failed, what was repeated)

## Step 2 — Classify what went wrong

| Class | Description | Example |
|---|---|---|
| **Artifact leak** | Resources created but not cleaned up | Stale locked worktrees, temp files, orphaned branches |
| **Memory gap** | Something learned that should be captured | User preference, recurring error pattern |
| **Stale memory** | Memory that no longer reflects reality | File path renamed, function removed |
| **Skill gap** | A skill with missing steps, wrong assumptions, or unclear triggers | Stage 4 teardown skipped → worktrees pile up |
| **Process gap** | An SDLC step that's unclear or routinely skipped | Cleanup checklist buried, not visible at handoff |
| **Bug class** | New category of recurring error not in autotiers-bug-classes | New mistake pattern that has hit users |

For each issue found, name the class and the specific evidence.

## Step 3 — Apply improvements

Work top-down: cleanup first (removes noise), then memory, then skills/SDLC.

### Artifact cleanup

For locked/stale worktrees — check before removing:

```bash
# See if branch has unmerged commits
git log main..<branch-name> --oneline

# Check for open PR before removing
gh pr list --head <branch-name>
```

**Safe to remove**: branch fully merged into main (empty log diff) OR PR is merged/closed.

**Leave alone**: open PR still in review, or last commit < 1 hour ago (may be active).

```bash
git worktree remove -f -f .claude/worktrees/<name>
# Agent-locked worktrees require -f -f (double-force); --force alone fails with "cannot remove a locked working tree"
git branch -d <branch-name>          # -D only if branch is gone remotely too
```

After cleanup, verify: `git worktree list` should show no unexpected locked entries.

### Memory updates

- **Add**: write new memory file → update `MEMORY.md` index (one line, under 150 chars)
- **Update**: edit existing file if facts changed
- **Remove**: delete file + remove line from `MEMORY.md` if stale or wrong

Don't add memory for things derivable from reading the code (file structure, conventions). Add memory for surprises, preferences, and decisions that aren't visible in the code.

### Skill / agent improvements

Read the relevant SKILL.md or agent `.md` before editing. Make surgical edits:
- Fix the specific gap — don't rewrite everything
- Explain the WHY behind the change, not just what to do — the model executes better with intent than rules
- If adding a checklist item, add it at the point in the flow where it's actually needed, not in a distant appendix
- If a step is routinely skipped, ask: is it buried? Is the trigger unclear? Fix those, don't just add a MUST

For changes to `.claude/` surface: consult the `claude-code-author` agent if the change is non-trivial.

### SDLC process improvements

If the gap is in the AutoTiers SDLC (`autotiers-sdlc` skill), edit `.claude/skills/autotiers-sdlc/SKILL.md`. Common fix patterns:
- Teardown not happening → make the teardown checklist visible at the point where agents complete work, not just at the end of the doc
- Stage 5 not triggered → add an explicit trigger condition the Manager can't miss

## Step 4 — Report

One compact block after all changes are applied:

```
Cleaned:  <artifacts removed>
Memory:   <entries added / updated / removed>
Skills:   <files changed and the specific gap fixed>
Open:     <anything that couldn't be fixed here>
```

No prose summary. Facts only.

## Guardrails

- Don't remove worktrees with open PRs or commits < 1 hour old
- Don't delete memory entries just because they're old — only if wrong or stale
- Don't rewrite whole skills from one bad run — surgical edits only
- Don't create new bug classes without a concrete canonical case to anchor it
- Don't add memory for things git log or the codebase already captures
