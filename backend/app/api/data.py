import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, AsyncSessionLocal
from app.data.fetcher import fetcher
from app.data.status import get_all_status
from app.auth.admin import require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run_refresh() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await fetcher.refresh_all(db)
        except Exception:
            logger.exception("Background data refresh failed")


@router.get("/data/status")
async def data_status(db: AsyncSession = Depends(get_db)) -> dict:
    return await get_all_status(db)


@router.post("/data/refresh")
async def data_refresh(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin),
) -> dict:
    background_tasks.add_task(_run_refresh)
    return {"status": "refresh started"}
