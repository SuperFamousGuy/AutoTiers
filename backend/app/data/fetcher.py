"""Top-level data refresh orchestrator. Wires source fetchers together."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.data.sources.sleeper import SleeperFetcher
from app.data.sources.nfl_data import NflDataFetcher
from app.data.sources.fantasypros import FantasyProsFetcher
from app.data.sources.cbs import CBSFetcher
from app.data.status import upsert_status, get_all_status, purge_retired_status


logger = logging.getLogger(__name__)


class DataFetcher:
    """Orchestrates downstream sources. Sleeper runs first; others follow."""

    def __init__(self, prior_season: int, current_season: int):
        self.prior_season = prior_season
        self.current_season = current_season
        # Guards against concurrent refresh_all runs (issue #827). refresh_all
        # is not concurrency-idempotent: two runs double the outbound scraping
        # load and write-race the same DataSourceStatus/Player/Projection rows.
        # asyncio is single-threaded and cooperative, so the check-and-set in
        # try_begin_refresh() (no await between read and write) is atomic —
        # a plain flag is sufficient; no Lock is needed. Callers (the admin
        # endpoint and the scheduler) claim the slot before starting a run and
        # release it in a finally block so a failed run doesn't wedge it.
        self._refresh_in_progress = False

    @property
    def is_refreshing(self) -> bool:
        return self._refresh_in_progress

    def try_begin_refresh(self) -> bool:
        """Atomically claim the refresh slot.

        Returns True if the caller now owns the slot and must run the refresh
        (then call :meth:`end_refresh` in a finally block). Returns False if a
        refresh is already in progress and the caller should not start another.
        """
        if self._refresh_in_progress:
            return False
        self._refresh_in_progress = True
        return True

    def end_refresh(self) -> None:
        """Release the refresh slot. Safe to call even if not currently held."""
        self._refresh_in_progress = False

    async def refresh_all(self, db: AsyncSession) -> dict[str, dict]:
        # 0. Drop stale status rows for retired sources (e.g. spotrac, issue
        # #402) so they don't linger as perpetual errors in API/UI responses.
        # Committed alongside the fresh status rows by db.commit() below.
        await purge_retired_status(db)

        # 1. Sleeper first — provides player table and cross-IDs.
        sleeper_result = await SleeperFetcher().fetch(db)
        await self._persist(db, sleeper_result)

        if not sleeper_result.success:
            skipped_at = datetime.utcnow()
            for name in ("nfl_data_py", "fantasypros", "cbs"):
                skipped = SourceResult(
                    source=name, rows_upserted=0, last_attempted=skipped_at,
                    success=False, error="skipped — sleeper refresh failed",
                )
                await self._persist(db, skipped)
            # Flush DataSourceStatus rows staged by _persist().
            # Fetcher internals already committed their domain data.
            await db.commit()
            return await get_all_status(db)

        # 2. Downstream sources. AsyncSession is not safe for concurrent use,
        # so we serialize on a shared session but still isolate failures.
        # NOTE: EspnFetcher is intentionally not invoked. ESPN's public projection
        # endpoint requires authentication (S2/SWID cookies); we use FantasyPros
        # consensus as the projection source instead. EspnFetcher source is kept
        # in app/data/sources/espn.py for future re-enable if cookie auth is added.
        # NOTE: SpotracFetcher was retired (see issue #402). Spotrac's old positional
        # cap-hit pages (/nfl/positional/{POS}/cap_hit/) now 404; the replacement
        # rankings endpoint serves its table via a Cloudflare-Turnstile-protected
        # AJAX request that an httpx scraper cannot satisfy. The PlayerContract-backed
        # "Follow the Money" rule still works when contract data is present, but we no
        # longer have a free production feed for it.
        downstream = [
            ("nfl_data_py", NflDataFetcher(prior_seasons=3, latest_season=self.prior_season)),
            ("fantasypros", FantasyProsFetcher()),
            ("cbs", CBSFetcher()),
        ]
        for name, src in downstream:
            try:
                result = await src.fetch(db)
            except asyncio.CancelledError:
                # Cooperative cancellation — app shutdown, `--reload` restart, or
                # a request timeout wrapping this task. CancelledError is a
                # BaseException; catching it here (as the old `except BaseException`
                # did) would swallow the cancellation and keep the loop running,
                # defeating graceful shutdown (see issue #660). Record a
                # bookkeeping status, then re-raise so the task ends cancelled.
                logger.info("data refresh cancelled during %s fetch", name)
                try:
                    await self._persist(db, SourceResult(
                        source=name, rows_upserted=0, last_attempted=datetime.utcnow(),
                        success=False, error="skipped — shutdown",
                    ))
                except Exception:
                    # Best-effort bookkeeping; never mask the cancellation.
                    logger.debug(
                        "failed to record shutdown status for %s", name, exc_info=True
                    )
                raise
            except Exception as e:
                result = SourceResult(
                    source=name, rows_upserted=0, last_attempted=datetime.utcnow(),
                    success=False, error=str(e),
                )
            await self._persist(db, result)

        # Flush DataSourceStatus rows staged by _persist().
        # Fetcher internals already committed their domain data.
        await db.commit()
        return await get_all_status(db)

    @staticmethod
    async def _persist(db: AsyncSession, result: SourceResult) -> None:
        await upsert_status(
            db,
            source=result.source,
            last_attempted=result.last_attempted,
            success=result.success,
            rows_upserted=result.rows_upserted,
            error=result.error,
        )


# Singleton consumed by the API + scheduler.
class _DefaultFetcher(DataFetcher):
    def __init__(self):
        now = datetime.utcnow()
        super().__init__(prior_season=now.year - 1, current_season=now.year)

    async def last_updated(self, db: AsyncSession) -> dict:
        return await get_all_status(db)


fetcher = _DefaultFetcher()
