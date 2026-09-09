"""Sleeper API fetcher — the master player list."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.models import Player


logger = logging.getLogger(__name__)

_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST", "DEF"}
_POSITION_NORMALIZE = {"DEF": "DST"}

# --- Orphan-delete sanity floor (#1203) ---
#
# ``fetch`` hard-deletes every existing Player whose id is absent from the
# current Sleeper response, cascading via FK to PlayerStat/Projection/ADPData.
# The only pre-existing guard is ``resp.raise_for_status()``, which catches
# non-2xx and JSON-parse failures only. A valid HTTP 200 that nonetheless
# carries a degraded payload — transient Sleeper degradation, a field rename
# that filters every row out, an empty ``{}`` body, a truncated/paginated
# response, or a CDN serving a stale cached error page as JSON — would leave
# ``seen_ids`` near-empty and delete essentially the whole player table (plus
# all dependent stat/projection/ADP rows) while still returning ``success=True``.
# Because Sleeper runs first in ``DataFetcher.refresh_all``, that also poisons
# the subsequent nfl_data/fantasypros/cbs matches for the cycle.
#
# Guard: once we already hold a substantial table (>= ``_ABSOLUTE_FLOOR`` rows),
# refuse to run the delete when the number of players we would *retain* is
# anomalously low relative to what we have — i.e. when
# ``len(seen_ids) < max(_ABSOLUTE_FLOOR, existing_count * _RETAIN_FRACTION)``.
# A healthy Sleeper feed yields many hundreds of active fantasy-relevant players,
# so a retained set below 500 (or below half the current table) is treated as a
# failed refresh: we discard the pending upserts, keep every existing row, log a
# warning, and return ``success=False`` so the cycle is retried rather than
# silently accepted as good.
#
# The floor deliberately does NOT engage while the table is small
# (< ``_ABSOLUTE_FLOOR``): a fresh/bootstrapping DB legitimately holds few rows
# and has no large table to protect, so the normal orphan-delete runs. The
# trade-off is that a real table sized right at the floor that legitimately loses
# a player or two registers a (retryable, non-destructive) soft failure — an
# acceptable price given the severity of wiping the entire table.
_ABSOLUTE_FLOOR = 500
_RETAIN_FRACTION = 0.5


class _SanityFloorTripped(Exception):
    """Internal signal that the orphan-delete sanity floor refused the delete.

    Raised inside the ``db.begin_nested()`` SAVEPOINT so that unwinding the block
    rolls back only *this* source's staged upserts, leaving unrelated pending
    work on the shared session (e.g. ``refresh_all``'s ``purge_retired_status``)
    intact for its end-of-run commit. Never escapes ``fetch``.
    """


class SleeperFetcher:
    name: ClassVar[str] = "sleeper"
    base_url: ClassVar[str] = "https://api.sleeper.app"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"},
            ) as client:
                resp = await client.get("/v1/players/nfl")
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        existing_rows = (await db.scalars(select(Player))).all()
        existing_by_id = {p.id: p for p in existing_rows}
        seen_ids: set[str] = set()

        upserted = 0
        try:
            # SAVEPOINT (nested transaction) around all of this source's writes —
            # the upserts *and* the orphan delete. When the sanity floor trips we
            # must discard our own staged rows without touching pending work that
            # DataFetcher.refresh_all already staged on the shared session before
            # calling us (e.g. purge_retired_status). A blanket db.rollback() would
            # undo that unrelated bookkeeping too; rolling the savepoint back scopes
            # the cleanup to us alone. Mirrors the begin_nested() pattern in
            # fantasypros.py.
            async with db.begin_nested():
                for sleeper_id, raw in payload.items():
                    position = raw.get("position")
                    if position not in _FANTASY_POSITIONS:
                        continue
                    # Gate on Sleeper's own ``active`` flag, NOT on ``team`` (#791).
                    # A just-released *free agent* is still ``active=True`` but has
                    # ``team=None``; treating team-null as deletion-worthy hard-deleted
                    # him (and cascaded away his PlayerStat/Projection/ADPData history)
                    # the instant he showed up unrostered, even though every public ADP
                    # board still ranks him as a discounted-but-draftable option. Only
                    # genuinely retired/inactive players carry ``active=False`` — those
                    # we still skip (and thus prune) as before.
                    if not raw.get("active", True):
                        continue

                    team = raw.get("team")  # None for free agents — persisted as-is.
                    seen_ids.add(sleeper_id)
                    existing = existing_by_id.get(sleeper_id)
                    if existing is None:
                        existing = Player(id=sleeper_id)
                        db.add(existing)

                    existing.name = raw.get("full_name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip()
                    existing.position = _POSITION_NORMALIZE.get(position, position)
                    existing.team = team
                    existing.age = raw.get("age")
                    existing.years_exp = raw.get("years_exp")
                    # Only overwrite cross-IDs when Sleeper explicitly produced a value this
                    # run. Sleeper transiently omits gsis_id/espn_id even for players it has
                    # populated on prior pulls; an unconditional assignment would wipe a
                    # previously-correct id to None and silently drop the player from every
                    # downstream nfl_data_py join (which keys on Player.gsis_id.is_not(None)).
                    # Mirrors the "only overwrite when the source produced a value" pattern in
                    # nfl_data.py. See issue #837.
                    if raw.get("gsis_id") is not None:
                        existing.gsis_id = raw["gsis_id"]
                    if raw.get("espn_id") is not None:
                        existing.espn_id = str(raw["espn_id"])
                    existing.active = True
                    upserted += 1

                # Sanity floor before the destructive delete loop (#1203). Skip the
                # delete entirely — and fail the refresh — when a populated table would
                # be gutted by an anomalously small retained set (a degraded-but-200
                # payload). See the module-level constants for the threshold rationale.
                existing_count = len(existing_by_id)
                if existing_count >= _ABSOLUTE_FLOOR:
                    sanity_floor = max(_ABSOLUTE_FLOOR, int(existing_count * _RETAIN_FRACTION))
                    if len(seen_ids) < sanity_floor:
                        # Bail out of the SAVEPOINT: raising unwinds begin_nested(),
                        # which rolls back our staged upserts (discarding the partial
                        # write) and runs no delete, while refresh_all's pending
                        # purge_retired_status survives for its final commit. A
                        # degraded payload must be a no-op failed refresh.
                        raise _SanityFloorTripped(
                            f"sanity floor tripped: payload would retain only "
                            f"{len(seen_ids)} of {existing_count} existing players "
                            f"(floor={sanity_floor}); skipping orphan delete and failing "
                            f"the refresh to avoid wiping the player table"
                        )

                # Hard-delete players Sleeper has dropped from its player list *entirely*
                # (id absent from the response), plus any it now marks inactive. A player
                # who is merely unrostered (team=None but still active) stays in
                # ``seen_ids`` above and is preserved — see #791.
                # Cascade FKs on Player.stats/projections/adp_entries clean up dependent
                # rows for the players we do delete.
                for pid, p in existing_by_id.items():
                    if pid not in seen_ids:
                        await db.delete(p)
        except _SanityFloorTripped as e:
            # SAVEPOINT already rolled back as the exception unwound: our upserts
            # are gone, no delete ran, and the shared session's other pending work
            # is untouched. Fail the refresh so the cycle is retried.
            msg = str(e)
            logger.warning("sleeper: %s", msg)
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=msg)

        await db.commit()
        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)
