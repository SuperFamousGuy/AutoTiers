#!/usr/bin/env bash
# Install the repo's hooks into .git/hooks/ so they survive branch switches.
#
# Run once per clone (and again after the canonical hook source in
# .githooks/ changes):
#   ./.githooks/setup.sh
#
# Why a copy install and not core.hooksPath:
# core.hooksPath points at a tree-checked directory, so the hook is only
# present when the current branch contains it. Branches that diverged
# before the hook landed get no protection. Copying into .git/hooks/
# (which is per-clone, not per-branch) gives the protection on every
# branch in this clone, including pre-existing ones.

set -e
cd "$(git rev-parse --show-toplevel)"

# Clear any previous core.hooksPath setting from older versions of this
# script (the .githooks/ approach was the first cut).
if [ "$(git config --get core.hooksPath || true)" = ".githooks" ]; then
  git config --unset core.hooksPath
fi

HOOKS_DIR="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS_DIR"

for hook_source in .githooks/*; do
  hook_name="$(basename "$hook_source")"
  case "$hook_name" in
    setup.sh|README.md) continue ;;
  esac
  cp "$hook_source" "$HOOKS_DIR/$hook_name"
  chmod +x "$HOOKS_DIR/$hook_name"
  echo "[githooks] installed $hook_name → $HOOKS_DIR/$hook_name"
done

echo "[githooks] done. Re-run this script after updating .githooks/ sources."
