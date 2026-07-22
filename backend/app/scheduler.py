from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.data.fetcher import fetcher
from app.database import AsyncSessionLocal
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))


async def _refresh_job() -> None:
    # Share the refresh slot with the admin endpoint (issue #827) so a
    # scheduler tick that lands while an admin-triggered refresh is still in
    # flight (or vice versa) is skipped instead of launching a duplicate,
    # concurrency-unsafe refresh_all run. Release it in finally so a failed
    # run doesn't wedge future refreshes.
    if not fetcher.try_begin_refresh():
        logger.info("Skipping scheduled data refresh; one is already in progress")
        return
    try:
        async with AsyncSessionLocal() as db:
            status = await fetcher.refresh_all(db)
            logger.info("Data refresh complete: %s", status)
    finally:
        fetcher.end_refresh()


def setup_scheduler() -> None:
    if not scheduler.get_job("hourly_refresh"):
        # next_run_time=now → fire once immediately on boot, then hourly. The
        # scheduler task is force-redeployed on each deploy, so this guarantees
        # a refresh right after deploy instead of waiting up to an hour with
        # stale data on the live site.
        #
        # misfire_grace_time=None disables APScheduler's default 1s misfire
        # window: the boot fire runs even if start() lands more than a second
        # after add_job() (e.g. cold-start GC, future I/O between the two
        # calls). Without it, a slow boot would *silently* skip the refresh —
        # the same silent-failure class this whole change exists to fix.
        scheduler.add_job(
            _refresh_job,
            IntervalTrigger(hours=1),
            id="hourly_refresh",
            next_run_time=datetime.now(ZoneInfo("UTC")),
            misfire_grace_time=None,
        )
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
