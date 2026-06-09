from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.data.fetcher import fetcher
from app.database import AsyncSessionLocal
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
        scheduler.add_job(_refresh_job, IntervalTrigger(hours=1), id="hourly_refresh")
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
