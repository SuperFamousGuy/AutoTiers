---
name: resolve-merge-conflicts
description: Resolve git merge conflicts end-to-end — detect all conflicted files, analyze both sides of each conflict, apply intelligent resolutions (making best-guess calls and flagging uncertain ones), commit the result, and report a summary. Handles all file types: source code, package.json, lockfiles, config files. Works in any git repo. Invoke when the user says "resolve the merge conflicts", "fix the conflicts", "we have conflicts", "merge is conflicted", "help me with these conflicts", "there are conflicts on this branch", or any similar phrase describing git merge or rebase conflict state.
---

# Resolve Merge Conflicts

## Before starting

```bash
# Confirm conflict state
git status
git diff --name-only --diff-filter=U  # list conflicted files
```

If there are no conflicted files, tell the user and stop. If a rebase is in progress (`git rebase --show-current-patch` exits 0), note that — the commit step differs.

---

## Step 1: Inventory all conflicts

```bash
git diff --name-only --diff-filter=U
```

Group files by type so you can apply the right resolution strategy to each:

| Group | Files |
|-------|-------|
| **lockfiles** | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Pipfile.lock`, `poetry.lock` |
| **package manifests** | `package.json`, `pyproject.toml`, `Pipfile`, `requirements.txt` |
| **config** | `.json`, `.yaml`, `.yml`, `.toml`, `.env.*`, `.rc` files |
| **source** | `.ts`, `.tsx`, `.js`, `.jsx`, `.py`, `.go`, etc. |

---

## Step 2: Resolve each file

Work through the groups. For each conflicted region (`<<<<<<< … ||||||| … =======  … >>>>>>>`), make a resolution decision and apply it.

### Lockfiles (`package-lock.json`, `yarn.lock`, etc.)

Never try to hand-resolve a lockfile — the merge markers corrupt the binary/structured format. Delete the lockfile and regenerate it:

```bash
# npm
rm package-lock.json && npm install
# If peer dep conflicts block the install:
# npm install --legacy-peer-deps

# yarn
rm yarn.lock && yarn install

# pnpm
rm pnpm-lock.yaml && pnpm install
```

If the lockfile is in a subdirectory (e.g., `web/package-lock.json`), run the install command from that directory.

### Package manifests (`package.json`)

Dependency version conflicts usually mean both sides added or updated a package. The right resolution is nearly always to keep both sets of changes and prefer the higher version when the same package appears on both sides.

Read both sides carefully. If one side removes a package the other side depends on, flag it as uncertain and keep both.

### Config files (JSON, YAML, etc.)

Read both sides in full. The goal is a merged result that satisfies both sides' intent:
- If both sides added different keys: keep all keys
- If both sides changed the same key differently: pick the value that looks more recent or intentional; flag as uncertain
- If one side deleted a key the other changed: flag as uncertain, keep the changed version by default

### Source code

Read both sides in full, plus surrounding context. Understand *what* each side was trying to accomplish, then write a merged version that satisfies both. Don't just pick one side — look for a real semantic merge.

Common patterns:
- Both sides added different imports: keep all imports, dedup
- Both sides modified the same function: merge the changes if possible; if they conflict semantically, pick the version that looks correct for the current branch's intent and flag
- One side deleted code the other modified: keep the modification, flag

---

## Step 3: Mark uncertain resolutions

After resolving, create a brief uncertainty log in memory (not a file). Track:
- Which file/line was uncertain
- What you chose and why
- What the alternative was

You'll use this for the final report.

---

## Step 4: Verify — no conflict markers remain

```bash
# This should return nothing
grep -rn "<<<<<<\|=======\|>>>>>>>" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.json" --include="*.py" --include="*.yaml" --include="*.yml" . | grep -v node_modules | grep -v ".git"
```

If any markers remain, go back and resolve them before continuing.

Also run a quick sanity check if there's a build or lint step that's fast:

```bash
# Example — adapt to what's in this repo
npm run typecheck 2>/dev/null || true
```

---

## Step 5: Stage and commit

```bash
git add -A
git status  # confirm only conflict-resolved files are staged
```

If this is a merge (not a rebase):

```bash
git commit -m "$(cat <<'EOF'
chore: resolve merge conflicts

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

If this is a rebase in progress:

```bash
git rebase --continue
```

---

## Step 6: Report

Print a summary table:

```
## Merge conflicts resolved

| File | Strategy | Confidence |
|------|----------|------------|
| web/package.json | Merged both dependency sets | High |
| web/package-lock.json | Regenerated via npm install | High |
| src/components/Foo.tsx | Merged both changes | High |
| src/utils/bar.ts | Picked HEAD version | ⚠️ Uncertain — see note |

### Uncertain resolutions
- `src/utils/bar.ts:42` — both sides changed the same default value (`5` vs `10`). Chose `10` (incoming). Verify this matches intent.

### Next steps
- [ ] Review uncertain resolutions above
- [ ] Run the full test suite: `npm test`
- [ ] Push when satisfied
```

Always list uncertain resolutions with enough context that the user can verify them quickly.
