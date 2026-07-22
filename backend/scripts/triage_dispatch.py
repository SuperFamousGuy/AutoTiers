"""Decision core for the triage dispatcher (`.github/workflows/claude-triage-dispatch.yml`).

The improvement recommender files backlog issues labelled `triage-queued`, each
carrying a `<!-- autotiers:rec score=N -->` marker in its body. This module is
the PURE decision: given a snapshot of repo state (`world`) — the concurrency
cap, the count of in-flight `claude/issue-*` PRs, and the queued issues — it
returns which issues to dispatch to `claude-implement-issue.yml` to fill the
open slots, highest score first.

Keeping the slot math + score-sort here (not in shell) lets us unit-test the
boundaries an `if`-chain gets wrong (cap<=inflight, tie-breaks, malformed
markers). The workflow shell then, for each dispatched issue, removes the
`triage-queued` label and dispatches the implement workflow via PR_AUTHOR_PAT.

world (stdin/file JSON):
    {
      "cap": 2,
      "inflight": 1,
      "queued_label": "triage-queued",
      "issues": [
        {"number": 12, "body": "spec\\n<!-- autotiers:rec score=8.5 -->",
         "labels": ["recommendation", "triage-queued"]}
      ]
    }

plan (stdout JSON):
    {"dispatch": [{"number": 12, "score": 8.5}], "slots": 1}

`slots` is the number of free slots computed (cap - inflight, floored at 0);
`dispatch` is at most `slots` issues, best score first. A malformed world (bad
JSON, missing key) raises and exits non-zero so a broken input is loud.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

_SCORE_RE = re.compile(r"<!--\s*autotiers:rec\s+score=([-+]?\d*\.?\d+)\s*-->")


def parse_score(body: str) -> float:
    """Score from the body marker; 0.0 when absent or non-numeric."""
    if not body:
        return 0.0
    m = _SCORE_RE.search(body)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except ValueError:
        return 0.0


def plan_dispatch(world: dict) -> dict:
    cap = int(world["cap"])
    inflight = int(world["inflight"])
    queued_label = world["queued_label"]
    slots = max(cap - inflight, 0)

    # Only genuinely-queued issues are candidates (defensive: the shell already
    # queries by label, but a stale/edited label list must not slip through).
    queued = [
        i for i in world.get("issues", [])
        if queued_label in i.get("labels", [])
    ]
    # Highest score first; deterministic tiebreak on ascending issue number.
    ordered = sorted(
        queued,
        key=lambda i: (-parse_score(i.get("body", "")), int(i["number"])),
    )
    dispatch = [
        {"number": int(i["number"]), "score": parse_score(i.get("body", ""))}
        for i in ordered[:slots]
    ]
    return {"dispatch": dispatch, "slots": slots}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--world",
        default="-",
        help="Path to the world JSON, or '-' (default) to read stdin.",
    )
    args = parser.parse_args(argv)
    raw = sys.stdin.read() if args.world == "-" else open(args.world, encoding="utf-8").read()
    plan = plan_dispatch(json.loads(raw))
    json.dump(plan, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
