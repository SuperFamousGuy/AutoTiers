from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.data.fetcher import fetcher
from app.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _refresh_job() -> None:
    async with AsyncSessionLocal() as db:
        status = await fetcher.refresh_all(db)
        logger.info("Data refresh complete: %s", status)


def setup_scheduler() -> None:
    if not scheduler.get_job("weekly_refresh"):
        scheduler.add_job(_refresh_job, CronTrigger(day_of_week="sun", hour=0, month="6,7"), id="weekly_refresh")
    if not scheduler.get_job("daily_refresh"):
        scheduler.add_job(_refresh_job, CronTrigger(hour=0, month="8,9"), id="daily_refresh")
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started")
