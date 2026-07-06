"""Version core for the weekly auto-release workflow
(`.github/workflows/weekly-release.yml`).

The weekly job cuts a GitHub release every Monday. This module is the PURE,
testable decision step: given the repo's existing release tags and the commits
since the latest one, it decides (a) whether a release should be cut at all
(the empty-week guard) and (b) what the next version string is.

Versioning is deliberately TWO-component `vX.Y` (2026-07-06 locked decision).
The weekly cut only ever bumps the MINOR component:
    v3.15 -> v3.16
A MAJOR bump (v4.0) is a human-only act and is never produced here. There is
NO semver migration; do not add a patch component.

The "current version" is derived from the highest existing `vX.Y` tag, NOT from
pyproject.toml / package.json (both are a stale 0.1.0 and are not the source of
truth for releases).

Two guards, both deliberate:
  * No base tag at all -> FAIL LOUDLY (exit non-zero). Never invent a baseline
    like v0.1 or v1.0; a missing tag means human setup is incomplete and a
    silent guess would ship a wrong first release straight to a prod deploy.
  * No commits since the latest tag -> SKIP cleanly (exit 0). An empty week
    must not cut an identical release (which would re-trigger a prod deploy).

Keeping this here (not in the workflow's shell) makes the parse / numeric-sort /
increment / guard boundaries deterministic and unit-tested. The workflow's shell
consumes the emitted `next=vX.Y` line and the exit code; it re-derives nothing.

CLI contract (consumed by the workflow):
    python3 backend/scripts/weekly_release_version.py \
        --tags-file tags.txt --commit-count <N>

  --tags-file    file with one git tag per line (from `git tag -l 'v*'`). May
                 contain non-matching tags; they are ignored.
  --commit-count integer count of commits in `<latest_tag>..HEAD`.

Exit codes:
    0  and prints `next=vX.Y`   -> cut this release
    0  and prints `skip=empty`  -> empty week, do nothing (not an error)
    3  and prints an error      -> no base tag; fail loudly, cut nothing
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Optional

# A release tag is EXACTLY two numeric components: v<major>.<minor>.
# Anything else (v1, v1.2.3, v1.2-rc1, "latest", release-1.2) is not a release
# tag we manage and must be ignored, not coerced.
_TAG_RE = re.compile(r"^v(\d+)\.(\d+)$")


def parse_tag(tag: str) -> Optional[tuple[int, int]]:
    """Return (major, minor) for a well-formed `vX.Y` tag, else None.

    None is the signal "not one of our release tags" -- the caller filters on
    it. We never partially parse (e.g. take the v1 out of v1.2.3); a tag either
    matches the two-component contract exactly or it is ignored entirely.
    """
    m = _TAG_RE.match(tag.strip())
    if m is None:
        return None
    return (int(m.group(1)), int(m.group(2)))


def highest_version(tags: list[str]) -> Optional[tuple[int, int]]:
    """Highest ``(major, minor)`` among well-formed tags, by NUMERIC order.

    Returns None when no tag matches -- the "no base tag" condition. Numeric
    order matters: v3.15 > v3.9 numerically but v3.15 < v3.9 lexically, so a
    naive string sort would regress the version. We sort the parsed integer
    tuples, never the raw strings.
    """
    versions = [v for v in (parse_tag(t) for t in tags) if v is not None]
    if not versions:
        return None
    return max(versions)


def next_version(current: tuple[int, int]) -> tuple[int, int]:
    """Bump the MINOR component only. (3, 15) -> (3, 16). Major untouched."""
    major, minor = current
    return (major, minor + 1)


def format_version(version: tuple[int, int]) -> str:
    major, minor = version
    return f"v{major}.{minor}"


def decide(tags: list[str], commit_count: int) -> tuple[int, str]:
    """Pure decision. Returns (exit_code, message) for the workflow to act on.

    (0, "next=vX.Y")   -> cut it.
    (0, "skip=empty")  -> empty week, skip.
    (3, "error: ...")  -> no base tag, fail loudly.
    """
    current = highest_version(tags)
    if current is None:
        return (
            3,
            "error: no base release tag matching vX.Y found; refusing to "
            "invent a baseline. Create the first release tag manually "
            "(e.g. `git tag v1.0 && git push --tags`) before arming the "
            "weekly cut.",
        )
    if commit_count <= 0:
        return (
            0,
            f"skip=empty (no new commits since {format_version(current)}, "
            "nothing to release)",
        )
    return (0, f"next={format_version(next_version(current))}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tags-file",
        required=True,
        help="file with one git tag per line (from `git tag -l 'v*'`)",
    )
    parser.add_argument(
        "--commit-count",
        required=True,
        type=int,
        help="count of commits in <latest_tag>..HEAD",
    )
    args = parser.parse_args(argv)

    with open(args.tags_file, encoding="utf-8") as fh:
        tags = fh.read().splitlines()

    code, message = decide(tags, args.commit_count)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
