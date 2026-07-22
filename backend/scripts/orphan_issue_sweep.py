"""Decision core for the orphan-issue sweeper (`claude-orphan-issue-sweeper.yml`).

`claude-implement-issue.yml` implements a trusted author's issue end-to-end and
opens a PR. It fires ONLY on `issues: opened/reopened` — a webhook, not a poll —
so nothing ever re-scans open issues. The flow has two no-PR outcomes:

  * DELIBERATE stop — the agent ran, its tests failed, it posted a blocker
    comment and stopped (job green). The implement workflow labels the issue
    `implement-blocked`. This is a correct terminal state; leave it alone.
  * SILENT death — the action step itself errored before the agent could post
    anything (dominant cause: the day's Claude subscription quota is exhausted;
    also timeouts / transient errors). The job concludes red, the push/PR steps
    skip on their `hashFiles('.pr-body.md')` gate, and the issue is left with no
    PR, no branch, no comment. It never re-triggers -> orphaned forever.

This module is the PURE decision: given a snapshot of repo state (`world`), it
returns the action plan the sweeper's shell then executes. Keeping the logic
here (not in shell) lets us unit-test the classification boundaries that shell
`if`-chains get wrong. The discriminator between the two cases above is the
`implement-blocked` label, NOT any historical Actions-run correlation
(`gh run list` exposes only a run's display title, i.e. the issue title, never
its number).

world (stdin JSON):
    {
      "max_attempts": 3,
      "attempt_label_prefix": "implement-attempt-",
      "blocked_label": "implement-blocked",
      "trusted_associations": ["OWNER", "MEMBER", "COLLABORATOR"],
      "issues": [
        {"number": 1, "title": "...", "author_association": "OWNER",
         "labels": ["implement-attempt-1"], "has_linked_pr": false,
         "has_branch": false, "in_progress": false}
      ]
    }

plan (stdout JSON):
    {
      "dispatch": [{"number", "attempt", "remove_labels", "add_label"}],
      "alarm":    [{"number", "attempts"}],
      "clear":    [{"number", "remove_labels"}],
      "skip":     [{"number", "reason"}]
    }

Exit code is 0 on success; a malformed world (bad JSON, missing key) raises and
exits non-zero so a broken input is loud rather than silently "nothing to do".
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def _attempt_labels(labels: list[str], prefix: str) -> tuple[int, list[str]]:
    """Return (highest attempt N, sorted attempt-label names present).

    A label whose suffix is not a base-10 integer is ignored for the count but
    still returned for removal, so a malformed `implement-attempt-oops` cannot
    wedge an issue: it contributes 0 to the count and gets swept away on the
    next dispatch.
    """
    names: list[str] = []
    best = 0
    for name in labels:
        if not name.startswith(prefix):
            continue
        names.append(name)
        suffix = name[len(prefix):]
        try:
            best = max(best, int(suffix))
        except ValueError:
            continue
    return best, sorted(names)


def plan_sweep(world: dict) -> dict:
    """Classify every open issue in `world` into an action plan (see module docstring)."""
    max_attempts = int(world["max_attempts"])
    prefix = world["attempt_label_prefix"]
    blocked = world["blocked_label"]
    queued_label = world.get("queued_label", "triage-queued")
    trusted = set(world["trusted_associations"])

    dispatch: list[dict] = []
    alarm: list[dict] = []
    clear: list[dict] = []
    skip: list[dict] = []

    for issue in world["issues"]:
        number = issue["number"]
        labels = issue.get("labels", [])
        count, attempt_labels = _attempt_labels(labels, prefix)

        # Trust FIRST, before anything that could mutate the issue. An untrusted
        # author's issue must always be a pure skip with zero label writes — even
        # the `clear` housekeeping below is a mutation, so the trust gate has to
        # precede it to honor "never touch a stranger's issue". (In practice an
        # untrusted issue never carries attempt labels, since the sweeper only
        # ever adds them to trusted issues — but ordering makes the safety
        # property hold by construction rather than by that incidental fact.)
        if issue.get("author_association") not in trusted:
            skip.append({"number": number, "reason": "untrusted_author"})
            continue

        # Undispatched triage backlog: intentionally waiting for the triage
        # dispatcher, NOT an orphan. Leave it entirely alone.
        if queued_label in labels:
            skip.append({"number": number, "reason": "triage_queued"})
            continue

        # A linked (open or merged) PR means the issue is in flight or done:
        # never an orphan. Housekeep any leftover attempt labels so a future
        # reopen starts from a fresh retry budget.
        if issue.get("has_linked_pr"):
            if attempt_labels:
                clear.append({"number": number, "remove_labels": attempt_labels})
            else:
                skip.append({"number": number, "reason": "has_linked_pr"})
            continue

        if issue.get("has_branch"):
            skip.append({"number": number, "reason": "has_branch"})
            continue
        if blocked in labels:
            skip.append({"number": number, "reason": "blocked"})
            continue
        if issue.get("in_progress"):
            skip.append({"number": number, "reason": "in_progress"})
            continue

        # Orphan: open, trusted, no PR, no branch, not blocked, not running.
        if count < max_attempts:
            dispatch.append({
                "number": number,
                "attempt": count + 1,
                "remove_labels": attempt_labels,
                "add_label": f"{prefix}{count + 1}",
            })
        else:
            alarm.append({"number": number, "attempts": count})

    return {"dispatch": dispatch, "alarm": alarm, "clear": clear, "skip": skip}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--world",
        default="-",
        help="Path to the world JSON, or '-' (default) to read stdin.",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.world == "-" else open(args.world, encoding="utf-8").read()
    world = json.loads(raw)
    plan = plan_sweep(world)
    json.dump(plan, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
