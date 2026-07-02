"""Selection core for the daily improvement recommender
(`.github/workflows/claude-improvement-recommender.yml`).

Three specialist agents (researcher/designer/engineer) each emit candidate
improvement recommendations into `candidates.json`. This module is the PURE,
testable selection step: given all candidates plus the recommendations already
tracked as open/recently-closed GitHub issues, it drops duplicates, orders by
the agent-assigned value/effort `score`, and caps the result to `max_issues`.
The workflow's shell then files exactly these as issues.

Keeping selection here (not in the LLM prompt or shell) makes the
dedup/cap/ordering boundaries deterministic and unit-tested; the LLM still
*generates* and *scores* candidates, but cannot flood the tracker or refile a
standing recommendation.

world (input dict):
    {
      "max_issues": 5,
      "existing": [{"number": 12, "title": "...", "state": "open"}],
      "candidates": [
        {"title": "...", "area": "rankings", "body": "...", "score": 8.5}
      ]
    }

result (return value): the surviving candidates, ordered best-first, capped:
    [{"title": "...", "area": "...", "body": "..."}]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(title: str) -> set[str]:
    """Lowercased alphanumeric word tokens of a title, for fuzzy comparison."""
    return set(_WORD_RE.findall(title.lower()))


def _is_duplicate(cand_title: str, existing_titles: list[str], threshold: float = 0.7) -> bool:
    """True if cand_title's word tokens overlap any existing title's at
    >= threshold (Jaccard). Robust to reordering/punctuation but keeps two
    unrelated titles distinct. A title with no word tokens never matches.
    """
    ctoks = _tokens(cand_title)
    if not ctoks:
        return False
    for et in existing_titles:
        etoks = _tokens(et)
        if not etoks:
            continue
        if len(ctoks & etoks) / len(ctoks | etoks) >= threshold:
            return True
    return False


def select(world: dict) -> list[dict]:
    max_issues = int(world.get("max_issues", 5))
    existing = world.get("existing") or []
    candidates = world.get("candidates")
    if not isinstance(candidates, list):
        candidates = []

    seen_titles: list[str] = [e.get("title", "") for e in existing if isinstance(e, dict)]
    kept: list[dict] = []

    # Highest score first; stable tiebreak on title so output is deterministic.
    ordered = sorted(
        (c for c in candidates if isinstance(c, dict)),
        key=lambda c: (-float(c.get("score", 0) or 0), str(c.get("title", ""))),
    )
    for c in ordered:
        title = str(c.get("title", "")).strip()
        body = str(c.get("body", "")).strip()
        if not title or not body:
            continue  # malformed candidate — needs both a title and a spec body
        if _is_duplicate(title, seen_titles):
            continue  # duplicates an existing issue OR an already-kept candidate
        kept.append({"title": title, "area": str(c.get("area", "")), "body": body})
        seen_titles.append(title)
        if len(kept) >= max_issues:
            break
    return kept


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, help="Path to candidates JSON (a list).")
    parser.add_argument("--existing", default="", help="Path to existing-recs JSON (a list); optional.")
    parser.add_argument("--max", type=int, default=5, help="Max issues to keep.")
    args = parser.parse_args(argv)

    def _load(path: str) -> list:
        if not path:
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    world = {
        "max_issues": args.max,
        "candidates": _load(args.candidates),
        "existing": _load(args.existing),
    }
    json.dump(select(world), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
