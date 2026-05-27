"""Profile CRUD endpoints. All require auth."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Profile
from app.auth.dependencies import require_user
from app.schemas.profile import (
    ProfileOut, ProfileCreate, ProfileUpdate, ProfilesListResponse,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])

_PROFILE_CAP = 5


@router.get("", response_model=ProfilesListResponse)
async def list_profiles(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> ProfilesListResponse:
    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).order_by(Profile.updated_at.desc())
    )).all()
    return ProfilesListResponse(
        profiles=[ProfileOut.model_validate(p) for p in profiles],
        active_profile_id=user.last_active_profile_id,
    )
