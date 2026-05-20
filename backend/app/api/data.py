from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.data.fetcher import fetcher
from app.config import settings

router = APIRouter()


async def require_admin(x_api_key: str = Header(default="")) -> None:
    if settings.admin_api_key and x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/data/status")
async def data_status(db: AsyncSession = Depends(get_db)) -> dict:
    return await fetcher.last_updated(db)


@router.post("/data/refresh")
async def data_refresh(db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)) -> dict:
    status = await fetcher.refresh_all(db)
    return {"status": status}
