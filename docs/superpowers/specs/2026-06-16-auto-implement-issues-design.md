# Design: Auto-implement issues via Claude Code Action

**Date:** 2026-06-16
**Status:** Approved (pending spec review)
**Repo:** SuperFamousGuy/AutoTiers (public)

## Goal

When a trusted author opens a GitHub issue, Claude implements it end-to-end on a
branch and opens a pull request that closes the issue. The maintainer reviews and
merges. No human involvement between "issue opened" and "PR ready for review".

## Decisions (from brainstorming)

| Question | Decision |
| --- | --- |
| Trigger | Every issue `opened`, runs to completion, opens a PR |
| Auth | `ANTHROPIC_API_KEY` stored as a GitHub Actions secret |
| Safety gate | Trusted authors only: `author_association` in OWNER/MEMBER/COLLABORATOR |
| Process depth | Full AutoTiers SDLC (implement, write + run tests, self-QA, PR) |
| Merge | No auto-merge — human reviews and merges the PR |
| Cost brake | Author gate only (no extra label) |

## Why the author gate matters

The repo is **public**. Without the gate, any GitHub user could open an issue whose
body becomes Claude's instructions, executed with the repo's `ANTHROPIC_API_KEY`
(billing) and a repo-write `GITHUB_TOKEN` (can push branches / open PRs). That is a
prompt-injection and billing-abuse hole.

`github.event.issue.author_association` resolves to `OWNER`/`MEMBER`/`COLLABORATOR`
only for trusted accounts; outside contributors get `CONTRIBUTOR`/`NONE`, and the
`github-actions[bot]` gets `NONE` (which also prevents the action recursing on issues
it might file). The job-level `if` is the single enforcement point.

## Architecture

One new workflow file, no existing workflow modified.

**File:** `.github/workflows/claude-implement-issue.yml`

```yaml
name: claude-implement-issue

on:
  issues:
    types: [opened]

concurrency:
  group: claude-issue-${{ github.event.issue.number }}
  cancel-in-progress: false

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  implement:
    name: implement issue
    runs-on: ubuntu-latest
    timeout-minutes: 30
    if: contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      # Pre-provision the toolchain so the SDLC's test step is fast and reliable,
      # mirroring versions in .github/workflows/tests.yml.
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: backend/pyproject.toml
      - name: Install backend deps
        working-directory: backend
        run: pip install -e ".[dev]"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install web deps
        working-directory: web
        run: npm ci

      - name: Implement issue
        uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: |
            <see Prompt section>
          claude_args: |
            <see claude_args section>
```

> Exact `anthropics/claude-code-action@v1` input names (`prompt`, `claude_args`,
> `anthropic_api_key`) must be verified against the action's current README during
> implementation — the action's schema has changed across versions. Pin to the
> latest stable major tag.

## Prompt (intent — final wording set during implementation)

The prompt instructs the CI Claude to:

1. Read the triggering issue: `#${{ github.event.issue.number }}` — title and body.
2. Follow the `autotiers-sdlc` skill for the implementation lifecycle.
3. Implement the change; write tests alongside it.
4. Run the relevant suites using the `autotiers-test-running` skill
   (pytest for backend, vitest + tsc for web). Do not open a PR if tests fail —
   instead comment on the issue explaining the blocker.
5. Open a PR whose body closes the issue (`Closes #<n>`) and summarizes the change,
   assumptions, and any known gaps.

The `.claude/skills/` and `.claude/agents/` directories are present in the checkout,
so the skills are available to the CI Claude without extra setup.

## claude_args (intent)

- Pin the model (latest Claude Opus).
- Allow the tools the SDLC needs: Bash (scoped to the test/build commands + git),
  Edit, Write, Read, Grep, Glob.
- Set a branch-name convention, e.g. `claude/issue-<n>-<slug>`.

## Data flow

```
issue opened (trusted author)
        │  author_association gate
        ▼
checkout → setup python/node → install deps
        ▼
claude-code-action: read issue → SDLC implement → write+run tests → push branch
        ▼
PR opened (Closes #n) + progress/summary comment
        ▼
human review → merge
```

## Error handling

- **Tests fail:** Claude comments the blocker on the issue, no PR. Human decides.
- **Untrusted author:** job skipped by the `if` gate (no run, no cost).
- **Duplicate trigger / re-open:** `concurrency` group per issue number serializes
  runs; `cancel-in-progress: false` lets an in-flight implementation finish.
- **Timeout:** 30-minute job cap bounds worst-case cost on a runaway run.
- **Missing secret:** the action step fails fast; no partial repo writes.

## Testing / verification

This is a CI-config change; it cannot be exercised by the existing test suites.
Verification plan:

1. Lint the workflow YAML (`actionlint` if available, else schema sanity check).
2. Confirm `ANTHROPIC_API_KEY` secret exists in repo settings (manual prerequisite).
3. Live smoke test: open a throwaway issue describing a tiny, safe change
   (e.g. a doc typo), confirm the action runs, opens a PR, and the PR closes the
   issue. Close the PR/issue without merging if it was only a smoke test.

## Prerequisites (manual, by maintainer)

- Add `ANTHROPIC_API_KEY` as a repository **Actions secret**.
- Ensure GitHub Actions is allowed to create pull requests
  (Settings → Actions → General → "Allow GitHub Actions to create and approve pull
  requests").

## Out of scope (YAGNI)

- Auto-merge of the resulting PR (human gate stays).
- `@claude` mention loops on issue/PR comments.
- Label-based gating (author gate is the only brake).
- A root `CLAUDE.md` (prompt + existing skills cover guidance).
- Bedrock / OAuth auth paths.

## Cost note

Each qualifying issue spends real Anthropic tokens (deps install + implement + test +
QA). The author gate is the cost fence: only issues you or a collaborator open will
spend. No in-workflow hard cap is possible; monitor usage in the Anthropic console.
