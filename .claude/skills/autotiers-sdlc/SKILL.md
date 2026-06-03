---
name: autotiers-sdlc
description: The canonical Software Development Lifecycle for AutoTiers agents. Defines the Designer → Engineer → QA flow, when each stage applies, how stages hand off to each other, when to consult advisory agents (Mathematician, Researcher, Claude-Code-Author), and when the Manager pushes back instead of executing. Invoke at the start of any non-trivial request — the Manager treats it as the authoritative process spec; every other agent reads it to know its role and its handoff contract.
---

# AutoTiers SDLC

A request lands. Three stages, three advisors, one orchestrator. Every stage produces a structured artifact the next stage can act on without re-deriving context.

## Roles

| Agent | Role | When dispatched |
|---|---|---|
| **autotiers-manager** | Orchestrator + primary user contact | Always first. Triages every request, decides which stages apply, dispatches in order, reports back. |
| **autotiers-designer** | Stage 1 — Design | When the request touches user-facing behaviour or needs a non-trivial plan. May consult Mathematician and Researcher. |
| **autotiers-engineer** | Stage 2 — Implementation | Always, when code changes. Consumes the Designer's design (or the user's direct request if Design was skipped). May consult Mathematician and Claude-Code-Author. |
| **autotiers-qa** | Stage 3 — Verification | After implementation, before reporting back to the user. May consult any other agent to confirm the change is safe. |
| **autotiers-mathematician** | Advisor — math correctness | Consulted by Designer (for algorithm shape), Engineer (for math implementation), or QA (for math invariant checks). |
| **autotiers-researcher** | Advisor — FF domain knowledge | Consulted by Designer (for heuristic validation) and QA (for "would a real FF expert accept this?"). |
| **claude-code-author** | Advisor — `.claude/` surface | Consulted by Engineer (when the change touches agents/skills/commands/hooks) and Manager (when the SDLC itself needs editing). |

The Manager is the only agent whose primary job is orchestration. Every other agent does its specialized work and reports back to the Manager.

## The flow

```
User request
   │
   ▼
┌─────────────────────────────────────────┐
│  autotiers-manager (triage)             │
│  - Decompose if multi-system            │
│  - Push back if ambiguous                │
│  - Choose which stages apply             │
└─────────────────────────────────────────┘
   │
   ├─[if design stage applies]──▶  autotiers-designer
   │                                  ├─ may consult autotiers-mathematician
   │                                  └─ may consult autotiers-researcher
   │                                      │
   │                                      ▼
   │                                  Design Artifact (handoff format below)
   │
   ├─[implementation stage — almost always]──▶  autotiers-engineer
   │                                                ├─ may consult autotiers-mathematician
   │                                                └─ may consult claude-code-author
   │                                                    │
   │                                                    ▼
   │                                                Implementation Report (handoff format below)
   │
   ├─[QA stage]──▶  autotiers-qa
   │                   ├─ may consult any agent
   │                       │
   │                       ▼
   │                   QA Verdict (handoff format below)
   │
   ▼
autotiers-manager reports back to user
```

## Triage — which stages apply

The Manager decides per-request. The defaults below are advisory; the Manager defends every skip in their report to the user.

### Stage 1 — Design

**Apply when** any of:
- The request introduces or modifies a user-visible feature, flow, or affordance.
- The request involves a non-trivial algorithm, data model, or workflow that has multiple reasonable approaches.
- The request says "build", "design", "add a way to", "make X work like Y", or similar feature-scoped language.
- The request crosses two or more components of the system (backend + frontend, scoring + tiers, OAuth + linking).
- A previously-shipped design needs revision.

**Skip when** all of:
- The request is a bug fix with a known cause.
- The change is local to one file or one tight cluster of files.
- The intent is unambiguous (no API decisions, no UX decisions, no algorithm choices).
- The fix preserves existing behaviour outside the bug site.

**Examples:**
- "Add weekly variance tracking" → Design applies. New data, new algorithm, UI implications.
- "Fix the PATCH response missing linked_league" → Design skipped. Clear bug, single backend handler, no API contract change.
- "Make the auth dialog show better error messages" → Design applies (UX decision, copy decisions, multi-state).
- "Bump the coverage threshold from 80% to 85%" → Design skipped. Config change.

### Stage 2 — Implementation

**Apply when** the request requires code changes. Almost always.

**Skip when**:
- The request is purely investigative ("audit X", "tell me whether Y is the case", "review this code"). Hand directly to QA or to the relevant advisor (Mathematician for math audits, Researcher for FF audits, Claude-Code-Author for `.claude/` audits).
- The request is documentation-only AND the Manager has authority to write it inline without consulting Engineer.

**Examples:**
- "Audit the rule weights for statistical soundness" → Implementation skipped; route to Mathematician.
- "Add a comment explaining why we set X" → Manager writes inline.

### Stage 3 — QA

**Apply when** the implementation stage ran AND any of:
- A user-facing behaviour changed.
- A persistence or auth flow was touched.
- A backwards-compatibility risk exists.
- The Engineer flagged DONE_WITH_CONCERNS.

**Skip when**:
- Pure refactor that the Engineer's existing tests already lock down completely (rare — usually QA still glances).
- Internal-only tooling change (e.g., a script under `backend/scripts/`).

When in doubt, run QA. The cost of a missed regression has shipped to users multiple times (see `autotiers-bug-classes`); the cost of an extra QA pass is minutes.

## Advisory consultations — when to invoke whom

### Designer's advisors

**autotiers-mathematician** — invoke when the design involves:
- A new scoring formula, weight, or coefficient.
- A clustering or ranking algorithm.
- Any statistical inference (regression, calibration, confidence interval).
- Changes to `backend/app/engine/` that could affect the math invariants.

**autotiers-researcher** — invoke when the design depends on:
- A fantasy football heuristic whose validity is debatable.
- A claim about player/team/positional behaviour that should be sourced.
- A user expectation about the game itself (e.g., "users will want X because the FF analyst consensus is Y").

### Engineer's advisors

**autotiers-mathematician** — invoke when implementing:
- Math the Designer specified but where the spec leaves edge cases or numeric stability decisions to the implementer.
- Anything where you're tempted to write your own clustering, statistics, or weighted-combination code instead of using `numpy` / `scipy` / `jenkspy`.
- Changes that affect `adjusted_score` shape or distribution in ways downstream rules might assume.

**claude-code-author** — invoke when the change:
- Adds, renames, or removes a file under `.claude/agents/`, `.claude/skills/`, `.claude/commands/`, or `.githooks/`.
- Modifies `.claude/settings.json` or any of its hooks.
- Changes the SDLC itself (this file or `autotiers-manager.md`).

### QA's advisors

QA may invoke any agent. Common patterns:
- **Mathematician** — to validate that the math produces sensible numbers on real data, not just on test fixtures.
- **Researcher** — to confirm a user-facing heuristic matches what a knowledgeable FF user would expect.
- **Designer** — to confirm the implementation matches the design's INTENT, not just its letter.
- **Claude-Code-Author** — when the change touched the `.claude/` surface and QA needs to verify the discovery contract.

## Handoff formats — what each stage produces

### Design Artifact (Designer → Engineer)

Path: `docs/superpowers/specs/YYYY-MM-DD-<short-topic>-design.md` (when substantial). For lightweight designs, the Manager may permit a chat-message-only handoff.

Required sections:

```
# <Topic> — Design

## Goal
One sentence — what does this accomplish for the user?

## Approach
2–3 sentences — what's the strategy at a high level?

## User-facing impact
What does the user see, click, type, read, expect? Include error states + empty states + loading states. Address copy.

## Code-facing impact
Which modules/files/components are affected. New interfaces. Data model changes. API contract changes.

## Math / statistical claims (if applicable)
Anything that needs Mathematician sign-off goes here in math notation with assumptions named.

## FF heuristic basis (if applicable)
Anything sourced from the Researcher's skill goes here with citation.

## Out of scope
What this design deliberately does NOT do. Prevents the Engineer over-building.

## Open questions
What still needs a decision before the Engineer can start. Manager triages these.
```

### Implementation Report (Engineer → QA)

Engineer's existing report format (see `autotiers-engineer.md`) is the contract:

```
STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED
WHAT I CHANGED: list of file:purpose
ASSUMPTIONS I MADE: explicit, challengeable
EDGE CASES I TESTED: input → expected behaviour
EDGE CASES I DID NOT COVER: thing → why deferred
EXTERNAL DEPENDENCIES TOUCHED: lib → which defaults verified
TEST RESULTS: backend N/N, frontend N/N, tsc status
COMMIT STATUS: branch, files staged, untracked items
```

### QA Verdict (QA → Manager)

QA's existing report format (see `autotiers-qa.md`) is the contract:

```
QA VERDICT: APPROVE | NEEDS_CHANGES | BLOCKED
BLOCKERS: thing → why it must be fixed before ship
NON-BLOCKERS: thing → why a follow-up is appropriate
CATEGORIES CHECKED: list from autotiers-bug-classes
ENGINEER'S ASSUMPTIONS CHALLENGED: which assumptions QA verified or contested
```

The Manager reads the QA Verdict and decides whether to ship, loop back to Engineer, or escalate to the user.

## When the Manager pushes back instead of executing

The Manager has authority to refuse a literal interpretation and ask the user to choose. Triggers:

1. **Multi-system scope** — request spans 3+ independent subsystems (e.g., "build a recommendation engine + frontend rebuild + new auth provider"). Manager proposes decomposition into N requests and asks user to pick the first.
2. **Ambiguous intent** — at least two reasonable interpretations of the request exist and they produce different designs. Manager states the interpretations and asks user to pick.
3. **Conflict with existing direction** — request contradicts a settled product decision (e.g., re-promoting ADP from tiebreaker to weighted input). Manager surfaces the conflict and asks for confirmation.
4. **Resource/scope mismatch** — request requires data we don't have, an external service we don't integrate with, or a model we don't ship. Manager states what's missing and proposes alternatives.
5. **Pre-empting a known bug class** — request would predictably trigger one of the eight bug classes in `autotiers-bug-classes`. Manager flags the risk and proposes a guard.

Pushback is NOT for:
- Tasks the Manager finds boring, repetitive, or low-status. Manager executes anyway.
- Tasks that look "too small" — small tasks still go through the SDLC the Manager chose.
- Sandbagging a user request to avoid effort.

The Manager's pushback message should be ONE pass — state the issue, propose the resolution, ask the user to confirm. Not a long back-and-forth.

## Reporting back to the user

The Manager's final response after each request:

```
WHAT YOU ASKED FOR: one-sentence echo

WHAT I DELIVERED: one-sentence outcome

STAGES RUN: design | impl | qa  (and which were skipped with one-line justification each)

ADVISORS CONSULTED: mathematician | researcher | claude-code-author  (and one line per consult)

PRs / COMMITS / FILES: list

FOLLOW-UPS YOU SHOULD KNOW ABOUT: anything I noticed but didn't address, with one line on why
```

When QA returns NEEDS_CHANGES the Manager loops back to Engineer before reporting; the user sees a final ship or a final block, not the intermediate iterations.

## Stage 4 — Teardown (always runs after merge)

The Manager runs teardown after a branch merges. No exceptions. This is what generates litter when skipped.

### Checklist

```
[ ] git worktree remove <path>     — for every worktree created during this feature
[ ] git stash drop                 — drop any epitaxy/WIP stashes on the feature branch
[ ] git branch -d <feature>        — delete local feature branch
[ ] git branch -d worktree-<name>  — delete local worktree branch (if created)
[ ] ls .claude/worktrees/          — verify directory is empty; delete residual dirs if present
```

### Rules

- Run teardown **after** the merge PR is closed, not before.
- If `git branch -d` refuses (branch not fully merged), investigate before using `-D`. The unmerged commits may be work that needs saving.
- The `docs/superpowers/specs/` and `docs/superpowers/plans/` files are **intentionally kept** on the main branch — they are searchable history, not litter.
- Remote feature branches on `origin` are left for GitHub to prune via the repo's "delete branch on merge" setting. Do not force-delete remote branches manually.

### What counts as litter

| Artifact | Litter? | Action |
|---|---|---|
| Local feature branch after merge | Yes | `git branch -d` |
| Worktree directory under `.claude/worktrees/` | Yes | `git worktree remove` |
| Epitaxy/WIP stash | Yes | `git stash drop` |
| Local `worktree-<name>` branch | Yes | `git branch -d` |
| `docs/superpowers/specs/*.md` files | No | Keep |
| `docs/superpowers/plans/*.md` files | No | Keep |

## When SDLC stages may parallelize

Stages run sequentially by default. The Manager may parallelize when:
- Design is being drafted AND Researcher is being consulted on an unrelated FF question for that same design. Researcher works in background.
- Engineer is implementing Task N of M AND Designer is finalizing the spec for Task N+1. (Only sound when N+1 doesn't depend on N's implementation details.)

Never parallelize Engineer and QA on the same change. QA waits for Engineer's DONE.

## Environment note (current limitation)

In this Claude Code environment, project-scoped agents (`.claude/agents/<name>.md`) are not yet directly dispatchable as `subagent_type` via the Agent tool — only the built-in agent types (`general-purpose`, `Plan`, etc.) are. The Manager and the SDLC are written assuming dispatch will work; until it does, the Manager either:

1. **Acts as the orchestrator inline** in the controller session — reading the same `.claude/agents/` files as prompt context and following the workflow manually.
2. **Dispatches `general-purpose` agents** with role-specific prompts that quote the relevant agent file inline.

When the environment is upgraded to support project-scoped dispatch, the Manager's workflow Just Works without rewriting any of these files.
