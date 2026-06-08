---
name: autotiers-sdlc
description: The canonical Software Development Lifecycle for AutoTiers agents. Defines the Designer → Engineer → QA flow, when each stage applies, how stages hand off to each other, when to consult advisory agents (Mathematician, Researcher, Claude-Code-Author), and when the Manager pushes back instead of executing. Invoke at the start of any non-trivial request — the Manager treats it as the authoritative process spec; every other agent reads it to know its role and its handoff contract.
---

# AutoTiers SDLC

A request lands. Five primary stages (1–5), three advisors, one orchestrator. Stages 3.5 and 3.6 are sub-stages of Stage 3. Every stage produces a structured artifact the next stage can act on without re-deriving context.

## Roles

| Agent | Role | When dispatched |
|---|---|---|
| **autotiers-manager** | Orchestrator + primary user contact | Always first. Triages every request, decides which stages apply, dispatches in order, reports back. |
| **autotiers-designer** | Stage 1 — Design | When the request touches user-facing behaviour or needs a non-trivial plan. May consult Mathematician and Researcher. |
| **autotiers-engineer** | Stage 2 — Implementation | Always, when code changes. Consumes the Designer's design (or the user's direct request if Design was skipped). May consult Mathematician and Claude-Code-Author. |
| **autotiers-qa** | Stage 3 — Verification | After implementation, before reporting back to the user. May consult any other agent to confirm the change is safe. |
| **autotiers-mathematician** | Advisor — math correctness | Consulted by Designer (for algorithm shape), Engineer (for math implementation), or QA (for math invariant checks). |
| **autotiers-researcher** | Advisor — FF domain knowledge | Consulted by Designer (for heuristic validation) and QA (for "would a real FF expert accept this?"). |
| **claude-code-author** | Advisor — `.claude/` surface | Consulted by Engineer (when the change touches agents/skills/commands/hooks), Manager (when the SDLC itself needs editing), and Manager again in Stage 5 (Retrospective Learning) when post-run updates touch the `.claude/` surface. |

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
   ├─[PR — always when code changed]──▶  Manager opens PR via `gh pr create`
   │                                         │
   │                                         ▼
   │                                     PR URL (included in final report)
   │
   ├─[issue filing — always]──▶  Manager files GitHub issues for out-of-scope items
   │                                  │
   │                                  ▼
   │                              Issue URLs (included in final report)
   │
   ▼
autotiers-manager reports back to user
   │
   ├─[teardown — after merge]──▶  Manager cleans worktrees, branches, stashes
   │
   └─[retrospective learning — after teardown]──▶  Manager updates skills/agents/SDLC
                                                       ├─ may consult claude-code-author
                                                           │
                                                           ▼
                                                       Learning updates (via PR to main)
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

### Stage 3.5 — PR Opening (always runs when code changed)

After QA approves (or when QA is skipped), the Manager opens a pull request. No exceptions. The user must never have to ask.

**Rules:**
- Target branch is always `main`.
- Title: conventional-commit style, under 70 characters.
- Body: 3-bullet summary + test plan checklist + `🤖 Generated with Claude Code` footer.
- If a PR for this branch already exists, link it — do not open a duplicate.
- PR URL is always included in the Manager's final report to the user.

**Skip only when:**
- The branch has no commits beyond `main` (nothing to PR).
- The user explicitly says "don't open a PR."

### Stage 3.6 — Out-of-Scope Issue Filing (always runs)

Every request surfaces work that was deliberately not done. That work must become a GitHub issue — not a note in the chat, not a bullet in the PR body, not a mental note. If it isn't filed, it doesn't exist.

**What gets filed:**

| Source | What to file |
|--------|-------------|
| Design Artifact — "Out of scope" section | Every bullet that defers real user value |
| Engineer's report — "EDGE CASES I DID NOT COVER" | Every deferred case (not trivial type exhaustion) |
| QA Verdict — "NON-BLOCKERS" | Every non-blocker that would improve correctness or coverage |
| PR review comments — "Defer" decisions | Each one, if it hasn't already been filed |

**What does NOT get filed:**
- Trivial code style observations with no user impact
- Things the Manager already decided are wrong directions
- Duplicate of an existing open issue (link instead)

**Issue format** (`gh issue create`):

```
Title: conventional-commit style, under 70 characters
Body:
  ## Background
  One sentence linking to the PR or feature that surfaced this.

  ## What to do
  Concrete description of the gap or feature.

  ## Acceptance criteria
  Bulleted checklist a future engineer can implement against.

  ## Notes
  Dependencies, constraints, or context a future implementer needs.
```

**Rules:**
- File issues BEFORE reporting back to the user. The user sees issue URLs, not promises.
- One issue per distinct concern. Don't batch unrelated gaps into one issue.
- If the deferred item is a stretch goal from the original request, link the original issue in the background section.
- Issue URLs always appear in the "ISSUES FILED" section of the Manager's final report.

**Skip only when:**
- There are genuinely no out-of-scope items (rare — say so explicitly in the report).
- The user explicitly says "don't file issues."

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
Each item here that defers real user value MUST become a GitHub issue (filed by the Manager in Stage 3.6).

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

The Manager reads the QA Verdict and decides whether to ship, loop back to Engineer, or escalate to the user. Every NON-BLOCKER in the QA Verdict MUST become a GitHub issue (filed in Stage 3.6) — it is not sufficient to note it in the final report.

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

STAGES RUN: design | impl | qa | pr-open  (and which were skipped with one-line justification each)

ADVISORS CONSULTED: mathematician | researcher | claude-code-author  (and one line per consult)

PR: <url> (always present when code changed — Manager opens before reporting)

ISSUES FILED: <url> — one line per issue created in Stage 3.6 (or "none" if no out-of-scope items)

TEARDOWN PENDING: <branch-name> → <worktree-path> (run Stage 4 after PR merges, or ask me to clean up) (or "none" if no worktrees were created)
```

Stage 5 (Retrospective Learning) runs after merge and teardown — it is a quiet post-merge step that produces commits, not a line in this report.

When QA returns NEEDS_CHANGES the Manager loops back to Engineer before reporting; the user sees a final ship or a final block, not the intermediate iterations.

## Stage 4 — Teardown (always runs after merge)

The Manager runs teardown after a branch merges. No exceptions. This is what generates litter when skipped.

### When to trigger

Stage 4 runs **in the same session** the PR is opened if the user merges immediately, OR in the next session the user returns after merging. If the Manager reports back and the session ends, the Manager should include "TEARDOWN PENDING" in its final report (see report format below) so the next session knows cleanup is waiting.

To trigger from a future session, the user asks: "clean up after <feature>" or invokes the `learn-from-experience` skill, which walks through the worktree/branch inventory and removes entries whose PRs are merged.

### Checklist

```
[ ] git worktree remove -f -f <path>  — for every worktree created during this feature
    NOTE: agent-locked worktrees require -f -f (not just --force); one -f is insufficient
[ ] git stash drop                    — drop any WIP stashes on the feature branch
[ ] git branch -d <feature>           — delete local feature branch
[ ] git branch -d worktree-<name>     — delete local worktree branch (if created)
[ ] ls .claude/worktrees/             — verify directory clean; remove any residual dirs
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

## Stage 5 — Retrospective Learning (always runs after teardown)

After cleanup, the Manager pauses and asks: _what should the agents, skills, and process know now that they didn't know before?_ Then makes those updates — for real, as committed changes — not as chat notes.

This is the stage that makes the system smarter over time. Skip it and the next team member (human or agent) repeats the same mistakes.

### What to look for

Scan the full SDLC run — Design Artifact, Implementation Report, QA Verdict, any advisor outputs, any pushback exchanges — and identify signals:

| Signal | Target artifact |
|--------|----------------|
| A bug type appeared that has no entry in `autotiers-bug-classes` | Add a new bug class |
| A bug class entry proved too vague to catch the actual failure | Sharpen it |
| Researcher surfaced a validated FF heuristic that isn't in the knowledge base | Append to `autotiers-ff-knowledge` |
| A triage rule (Design/QA apply/skip) fired incorrectly — stage was skipped when it shouldn't have been, or ran unnecessarily | Update the triage section of this file |
| A pushback trigger arose that isn't on the Manager's pushback list | Add it |
| An agent overstepped or understepped its stated role | Update `.claude/agents/<agent>.md` |
| An advisor was invoked for a reason not listed in "when to invoke whom" | Add the trigger |
| A handoff section was useless or a needed section was absent | Update the handoff format |
| The same workaround / approach appeared in two or more features | Codify as a new skill or add to an existing one |
| A skill or agent was never invoked and has no plausible future use | Flag for deprecation (file a GitHub issue; don't delete unilaterally) |

### The bar for updating

**Don't update for a single data point.** A pattern needs at least two independent occurrences before it earns a rule — unless the incident was severe (e.g., a bug that shipped to users despite QA).

Severity exception: any defect that:
- Passed QA and reached production, OR
- Required a hotfix branch, OR
- Was called out explicitly by the user as "this keeps happening"

…earns an immediate update, even on first occurrence.

### How to update

1. Identify which artifact(s) need changing.
2. Consult `claude-code-author` if the change touches `.claude/agents/`, `.claude/skills/`, `.claude/commands/`, or `.claude/settings.json` — use the agent's judgment on file format and discovery rules.
3. Make the edit surgically. Don't rewrite whole files; add the new signal to the right section.
4. Open a PR targeting `main` with a conventional-commit title: `chore(sdlc): <what changed and why>`. If branch protections are disabled and the changes are trivial (e.g., a one-line addition to a skill), a direct commit to `main` is acceptable.
5. The learning updates are visible via the resulting commit(s) — no separate user-facing report is needed.

### What NOT to update

- Code conventions, architecture, file paths — those live in CLAUDE.md or are derivable from the code.
- Git history or who-changed-what — `git log` is authoritative.
- Transient task state — nothing from the current session that won't be true next session.
- Speculation ("this might be an issue someday") — only real signals from real runs.

### Skip only when

- The run produced zero new signal: every stage behaved exactly as expected, no new heuristics, no surprises, no edge cases. (Rare. State "no new signal" explicitly in the LEARNING line.)
- The user explicitly says "don't update skills."

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
