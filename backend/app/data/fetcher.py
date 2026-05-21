"""Top-level data refresh orchestrator. Wires the four source fetchers together."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.base import SourceResult
from app.data.sources.sleeper import SleeperFetcher
from app.data.sources.nfl_data import NflDataFetcher
from app.data.sources.espn import EspnFetcher
from app.data.sources.fantasypros import FantasyProsFetcher
from app.data.status import upsert_status, get_all_status


logger = logging.getLogger(__name__)


class DataFetcher:
    """Orchestrates all four sources. Sleeper runs first; downstream sources run in parallel."""

    def __init__(self, prior_season: int, current_season: int):
        self.prior_season = prior_season
        self.current_season = current_season

    async def refresh_all(self, db: AsyncSession) -> dict[str, dict]:
        # 1. Sleeper first — provides player table and cross-IDs.
        sleeper_result = await SleeperFetcher().fetch(db)
        await self._persist(db, sleeper_result)

        if not sleeper_result.success:
            skipped_at = datetime.utcnow()
            for name in ("nfl_data_py", "espn", "fantasypros"):
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
        downstream = [
            ("nfl_data_py", NflDataFetcher(self.prior_season)),
            ("espn", EspnFetcher(self.current_season)),
            ("fantasypros", FantasyProsFetcher()),
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
