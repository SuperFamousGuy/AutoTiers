from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.data.fetcher import fetcher

router = APIRouter()


@router.get("/data/status")
async def data_status(db: AsyncSession = Depends(get_db)) -> dict:
    return await fetcher.last_updated(db)


@router.post("/data/refresh")
async def data_refresh(db: AsyncSession = Depends(get_db)) -> dict:
    status = await fetcher.refresh_all(db)
    return {"status": status}
