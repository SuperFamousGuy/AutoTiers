import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.data.fetcher import fetcher
from app.data.freshness import evaluate_data_freshness
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


@router.get("/data/health")
async def data_health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Machine-pollable data-freshness check for monitoring (issue #401).

    Returns the freshness verdict and an HTTP status code an uptime check /
    Route 53 health check can alarm on: 200 when data is fresh (or nothing is
    tracked yet), 503 when the oldest source's last refresh attempt is past the
    configured threshold — the signature of a crash-looped or frozen scheduler.
    Wire this to the ops SNS topic so a silent scheduler outage pages the team
    instead of waiting for a user to report the stale banner.
    """
    statuses = await get_all_status(db)
    verdict = evaluate_data_freshness(
        statuses, threshold_hours=settings.data_freshness_threshold_hours
    )
    status_code = 503 if verdict.stale else 200
    return JSONResponse(status_code=status_code, content=verdict.to_dict())


@router.post("/data/refresh")
async def data_refresh(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin),
) -> dict:
    background_tasks.add_task(_run_refresh)
    return {"status": "refresh started"}
