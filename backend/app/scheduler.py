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
    async with AsyncSessionLocal() as db:
        status = await fetcher.refresh_all(db)
        logger.info("Data refresh complete: %s", status)


def setup_scheduler() -> None:
    if not scheduler.get_job("hourly_refresh"):
        # next_run_time=now → fire once immediately on boot, then hourly. The
        # scheduler task is force-redeployed on each deploy, so this guarantees
        # a refresh right after deploy instead of waiting up to an hour with
        # stale data on the live site.
        scheduler.add_job(
            _refresh_job,
            IntervalTrigger(hours=1),
            id="hourly_refresh",
            next_run_time=datetime.now(ZoneInfo("UTC")),
        )
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
