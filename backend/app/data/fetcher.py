"""Top-level data refresh orchestrator. Wires source fetchers together."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.data.sources.sleeper import SleeperFetcher
from app.data.sources.nfl_data import NflDataFetcher
from app.data.sources.fantasypros import FantasyProsFetcher
from app.data.sources.spotrac import SpotracFetcher
from app.data.status import upsert_status, get_all_status, purge_statuses


logger = logging.getLogger(__name__)

# Sources that were once orchestrated but are no longer fetched. Their status
# rows are purged on every refresh so a permanently-dead source can't linger in
# the status table and mask overall freshness (the banner reports the oldest
# source). See app/data/sources/cbs.py for why CBS was retired.
RETIRED_SOURCES = ("cbs",)


class DataFetcher:
    """Orchestrates downstream sources. Sleeper runs first; others follow."""

    def __init__(self, prior_season: int, current_season: int):
        self.prior_season = prior_season
        self.current_season = current_season

    async def refresh_all(self, db: AsyncSession) -> dict[str, dict]:
        # 0. Evict retired sources so they don't pollute status/freshness.
        await purge_statuses(db, RETIRED_SOURCES)

        # 1. Sleeper first — provides player table and cross-IDs.
        sleeper_result = await SleeperFetcher().fetch(db)
        await self._persist(db, sleeper_result)

        if not sleeper_result.success:
            skipped_at = datetime.utcnow()
            for name in ("nfl_data_py", "fantasypros", "spotrac"):
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
        # NOTE: CBSFetcher is intentionally not invoked. CBS's projection page is
        # client-side rendered, so the static fetch+parse returned 0 rows on every
        # run (issue #404). Source is kept in app/data/sources/cbs.py for future
        # re-enable if a JSON endpoint or headless-render path is found.
        downstream = [
            ("nfl_data_py", NflDataFetcher(prior_seasons=3, latest_season=self.prior_season)),
            ("fantasypros", FantasyProsFetcher()),
            ("spotrac", SpotracFetcher()),
        ]
        for name, src in downstream:
            try:
                result = await src.fetch(db)
            except BaseException as e:
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
