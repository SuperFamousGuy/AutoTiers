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


class PositionMatchIndex:
    """Per-fetcher-run cache of candidate players keyed by position.

    A single ``DataFetcher.refresh_all()`` calls :func:`fuzzy_match` once (CBS) or
    twice (FantasyPros projections + ADP) per scraped row, all against the same
    position buckets. Without a cache each call re-issues an identical
    ``SELECT ... WHERE position = ?`` query and re-runs :func:`normalize_name`
    over the same candidates — 1000+ redundant queries/normalizations per run,
    awaited sequentially on one non-concurrent AsyncSession.

    Construct one instance per ``fetch(db)`` call and pass it to every
    :func:`fuzzy_match`. Each position's ``(player, normalized_name)`` pairs are
    loaded and normalized exactly once, then reused across all subsequent calls.

    Only valid for the lifetime of a single fetcher run: it assumes the Player
    rows for a position do not change while the run is in flight (fetchers read
    players, they never create them).
    """

    def __init__(self) -> None:
        self._cache: dict[str, list[tuple[Player, str]]] = {}

    async def candidates(self, db: AsyncSession, position: str) -> list[tuple[Player, str]]:
        """Return cached ``(player, normalized_name)`` pairs for a position.

        The first call for a given position issues the DB query and normalizes;
        later calls return the cached list (including an empty list, which is
        cached to avoid re-querying positions with no players).
        """
        cached = self._cache.get(position)
        if cached is None:
            players = (await db.scalars(
                select(Player).where(Player.position == position)
            )).all()
            cached = [(p, normalize_name(p.name)) for p in players]
            self._cache[position] = cached
        return cached


async def fuzzy_match(
    db: AsyncSession,
    name: str,
    team: str,
    position: str,
    threshold: int = 90,
    index: Optional[PositionMatchIndex] = None,
) -> Optional[Player]:
    """
    Resolve a (name, team, position) triple to a Player row.

    Strategy (in order):
      1. Exact match on (normalized_name, team, position) — return immediately.
      2. Exact match on (normalized_name, position), ignoring team — handles traded players.
      3. rapidfuzz token_set_ratio on normalized_name within the position bucket — return if score >= threshold.
    Returns None if no candidate scores above threshold.

    Pass ``index`` (a :class:`PositionMatchIndex`) to share one DB query + one
    normalization pass per position across all calls in a fetcher run. When
    ``index`` is ``None`` (the default) the candidates are loaded and normalized
    per call, preserving the original standalone behavior for isolated callers.
    """
    target = normalize_name(name)

    # Candidates are (player, normalized_name) pairs for the position bucket,
    # either freshly loaded (index is None) or served from the per-run cache.
    if index is None:
        players = (await db.scalars(
            select(Player).where(Player.position == position)
        )).all()
        candidates = [(p, normalize_name(p.name)) for p in players]
    else:
        candidates = await index.candidates(db, position)

    # Strategy 1: exact match including team
    same_team = [p for p, norm in candidates if norm == target and p.team == team]
    if same_team:
        return same_team[0]

    # Strategy 2: exact name + position, any team
    any_team = [p for p, norm in candidates if norm == target]
    if any_team:
        return any_team[0]

    # Strategy 3: fuzzy
    best: Optional[Player] = None
    best_score = 0
    for p, norm in candidates:
        score = fuzz.token_set_ratio(target, norm)
        if score >= threshold and score > best_score:
            best = p
            best_score = score
    return best
