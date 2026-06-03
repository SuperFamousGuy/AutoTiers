---
name: resolve-pr-comments
description: Walk through all open GitHub PR review threads end-to-end: fetch unresolved threads via GraphQL, triage each one (Act / Decline / Defer), apply code fixes, post replies, resolve threads, commit, push, and report a summary table. General-purpose — works in any repo with `gh` auth configured.
when_to_use: Invoke when the user says "address the PR comments", "fix the review feedback", "resolve the review threads", "work through the PR comments", "respond to reviewers", or any similar phrase asking to act on open GitHub review threads.
---

# Resolving open PR review threads

## Before starting

```bash
# Verify clean state and correct branch
git status
git branch --show-current
gh pr view --json number,title,headRefName,url
```

If there are uncommitted changes unrelated to this task, stash them first (`git stash`). Confirm the current branch matches the PR's head branch before touching anything.

---

## Step 1: Fetch open review threads

Use GraphQL to get all unresolved inline threads. Replace `$OWNER`, `$REPO`, and `$PR_NUMBER` with real values (derive them from `gh repo view --json owner,name` and `gh pr view --json number`):

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 5) {
            nodes {
              databaseId
              body
              author { login }
              createdAt
            }
          }
        }
      }
    }
  }
}
' -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER"
```

Filter to `isResolved: false` nodes. Each node gives you:
- `id` — the thread node ID needed for the `resolveReviewThread` mutation
- `path` — file path the comment is on
- `line` — line number
- `comments.nodes[0].databaseId` — the comment ID for posting a reply
- `comments.nodes[0].body` — the comment text to triage

Also fetch any top-level (non-inline) review comments that may not appear as threads:

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" --paginate \
  | python3 -c "import json,sys; [print(c['id'], c['path'], c['body'][:80]) for c in json.load(sys.stdin)]"
```

---

## Step 2: Triage each thread

For every open thread, decide one of three actions before writing a single line of code:

| Decision | When to use | What happens next |
|----------|-------------|-------------------|
| **Act** | The comment identifies a real problem or improvement worth making | Fix the code/docs, then reply + resolve |
| **Decline** | The comment is factually wrong, based on incomplete context, or deliberately not adopted | Reply explaining why, then resolve without code change |
| **Defer** | The comment is valid but out of scope for this PR (separate feature, cleanup, etc.) | Reply noting it's tracked separately, then resolve |

Triage criteria:
- Does acting on it change observable behaviour? If yes and the change is safe, Act.
- Does it conflict with an existing architectural decision in this repo? Decline with explanation.
- Is it a good idea but clearly a separate concern (new feature, big refactor)? Defer — but only if you'd actually file a follow-up issue or note it somewhere concrete. Don't Defer as a way to avoid work.
- When uncertain between Act and Decline, prefer Act for small changes and ask the user for large ones.

Write down the triage decision for every thread before starting any code edits.

---

## Step 3: Apply fixes (Act threads only)

For each Act thread:

1. Read the file at the path in the thread comment.
2. Make the targeted change — no opportunistic cleanup beyond what the comment asks for.
3. Verify: run the relevant test or type-check if the change touches typed code. Use whatever test runner the project uses (the project may have a skill for this).
4. Stage the change but do not commit yet — batch all Act fixes into one commit at the end.

---

## Step 4: Reply and resolve every thread

### Post a reply on an inline comment thread

```bash
gh api "repos/$OWNER/$REPO/pulls/comments/$COMMENT_ID/replies" \
  -X POST \
  -f body="$REPLY_TEXT"
```

`$COMMENT_ID` is `comments.nodes[0].databaseId` from the GraphQL response.

For a top-level PR review comment (not inline), reply via the issues comments endpoint:

```bash
gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" \
  -X POST \
  -f body="$REPLY_TEXT"
```

Reply tone:
- **Act**: one line naming what changed, e.g. "Done — moved validation to `_validate_input` and added a test."
- **Decline**: one or two sentences of technical reasoning, no apology, no padding.
- **Defer**: one sentence naming where it's tracked or why it's out of scope for this PR.

### Resolve the thread

After posting the reply, resolve via GraphQL mutation:

```bash
gh api graphql -f query='
mutation($threadId: ID!) {
  resolveReviewThread(input: { threadId: $threadId }) {
    thread {
      id
      isResolved
    }
  }
}
' -f threadId="$THREAD_NODE_ID"
```

`$THREAD_NODE_ID` is the `id` field from the thread in Step 1 (the opaque node ID, not the numeric database ID).

Do this for every thread — Act, Decline, and Defer alike. Leaving threads open after responding is noise for the reviewer.

---

## Step 5: Commit, push, and report

If any code changed:

```bash
git add -p   # review the diff; stage only the review-driven changes
git commit -m "address PR review feedback"
git push
```

Commit message convention: imperative, lowercase, concise. Prefix with the scope if the project uses one (e.g., `fix(auth): address review feedback`). Match the style of recent commits in this repo (`git log --oneline -10`).

Finally, output a summary table:

```
Thread                          | File                | Decision | What changed
--------------------------------|---------------------|----------|----------------------------------
"Use const instead of let"      | src/utils.ts:14     | Act      | Changed let → const
"Why not use X library?"        | src/api.ts:42       | Decline  | Explained we already use Y for this
"Add logging throughout"        | —                   | Defer    | Valid but out of scope; noted in #123
```

If no threads were open, say so and stop.

---

## Common failure modes

- **Thread node ID vs comment database ID**: the GraphQL thread `id` (opaque, looks like `PRRT_...`) is what `resolveReviewThread` needs. The `databaseId` integer is what the REST replies endpoint needs. Do not mix them up.
- **Resolving before replying**: post the reply first; resolving immediately closes the visual thread and the reply may not be clearly associated.
- **Batch-committing unrelated changes**: only stage changes that map to an Act decision. Unrelated edits confuse reviewers and can stall re-review.
- **Leaving Defer threads open**: resolve them even though you're not acting — an open thread implies it still needs attention.
- **PR number vs issue number**: for top-level comments, the GitHub REST API uses `/issues/$PR_NUMBER/comments` (PRs are issues in GitHub's model). This is not the same as the GraphQL `databaseId` of the pull request object.
