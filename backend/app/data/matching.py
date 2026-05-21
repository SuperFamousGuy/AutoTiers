"""Player name normalization and fuzzy matching for sources without stable IDs."""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player


_SUFFIX_PATTERN = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)
_PUNCT_PATTERN = re.compile(r"[^\w\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes (Jr/Sr/II/III/IV), remove punctuation, collapse whitespace."""
    s = name.lower()
    s = _SUFFIX_PATTERN.sub("", s)
    s = _PUNCT_PATTERN.sub("", s)
    s = _WHITESPACE_PATTERN.sub(" ", s).strip()
    return s


async def fuzzy_match(
    db: AsyncSession,
    name: str,
    team: str,
    position: str,
    threshold: int = 90,
) -> Optional[Player]:
    """
    Resolve a (name, team, position) triple to a Player row.

    Strategy (in order):
      1. Exact match on (normalized_name, team, position) — return immediately.
      2. Exact match on (normalized_name, position), ignoring team — handles traded players.
      3. rapidfuzz token_set_ratio on normalized_name within the position bucket — return if score >= threshold.
    Returns None if no candidate scores above threshold.
    """
    target = normalize_name(name)

    # Strategy 1: exact match including team
    candidates = (await db.scalars(
        select(Player).where(Player.position == position)
    )).all()

    same_team = [p for p in candidates if normalize_name(p.name) == target and p.team == team]
    if same_team:
        return same_team[0]

    # Strategy 2: exact name + position, any team
    any_team = [p for p in candidates if normalize_name(p.name) == target]
    if any_team:
        return any_team[0]

    # Strategy 3: fuzzy
    best: Optional[Player] = None
    best_score = 0
    for p in candidates:
        score = fuzz.token_set_ratio(target, normalize_name(p.name))
        if score >= threshold and score > best_score:
            best = p
            best_score = score
    return best
