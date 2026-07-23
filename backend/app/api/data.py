import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.data.fetcher import fetcher
from app.data.freshness import evaluate_data_freshness
from app.data.status import get_all_status, RETIRED_SOURCES
from app.auth.admin import require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run_refresh() -> None:
    # The refresh slot is claimed synchronously by data_refresh() before this
    # task is scheduled (issue #827); release it here so a subsequent refresh
    # can run once this one finishes, whether it succeeded or failed.
    try:
        async with AsyncSessionLocal() as db:
            try:
                await fetcher.refresh_all(db)
            except Exception:
                logger.exception("Background data refresh failed")
    finally:
        fetcher.end_refresh()


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
    # Exclude retired sources (#402) from the freshness verdict. Their rows stop
    # advancing `last_attempted` after retirement and are only deleted by
    # `purge_retired_status()` on the next scheduler cycle; between a retirement
    # deploy and that purge, a lingering row would become the "oldest attempt"
    # and trip a false 503 stale alarm even while every live source refreshes
    # normally (#786). Same exclusion `_compute_data_as_of` already applies for
    # the freshness banner (#579). Filtered here rather than in `get_all_status`
    # so `/api/data/status`'s response shape is unchanged.
    live_statuses = {
        source: row for source, row in statuses.items() if source not in RETIRED_SOURCES
    }
    verdict = evaluate_data_freshness(
        live_statuses, threshold_hours=settings.data_freshness_threshold_hours
    )
    status_code = 503 if verdict.stale else 200
    return JSONResponse(status_code=status_code, content=verdict.to_dict())


@router.post("/data/refresh")
async def data_refresh(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin),
) -> dict:
    # Claim the refresh slot synchronously (issue #827). BackgroundTasks run
    # after the response is sent, so claiming inside _run_refresh would let two
    # rapid POSTs both pass the check before either task starts. If a refresh
    # (admin- or scheduler-triggered) is already in flight, return 409 and
    # schedule nothing rather than launching a duplicate scraper run.
    if not fetcher.try_begin_refresh():
        return JSONResponse(
            status_code=409,
            content={"detail": "A data refresh is already in progress."},
        )
    background_tasks.add_task(_run_refresh)
    # Plain dict on the 200 path so FastAPI infers the OpenAPI response schema
    # (the 409 branch keeps JSONResponse for its custom status code).
    return {"status": "refresh started"}
