"""Profile CRUD endpoints. All require auth."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
        select(Profile)
        .where(Profile.user_id == user.id)
        .options(selectinload(Profile.linked_league))
        .order_by(Profile.updated_at.desc())
    )).all()
    return ProfilesListResponse(
        profiles=[ProfileOut.model_validate(p) for p in profiles],
        active_profile_id=user.last_active_profile_id,
    )


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    count = await db.scalar(
        select(func.count(Profile.id)).where(Profile.user_id == user.id)
    ) or 0
    if count >= _PROFILE_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Profile limit reached ({_PROFILE_CAP}). Delete one to add another.",
        )
    profile = Profile(
        user_id=user.id,
        name=body.name,
        settings_json=body.settings_json,
        rules_json=body.rules_json,
    )
    db.add(profile)
    await db.commit()
    # Eager-load linked_league before serializing — a freshly-created profile
    # has none, but ProfileOut still needs the attribute populated (vs. an
    # async lazy-load) for Pydantic's from_attributes to read it cleanly.
    await db.refresh(profile, attribute_names=["linked_league"])
    return ProfileOut.model_validate(profile)


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdate,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    # selectinload here matters: ProfileOut now includes linked_league, and the
    # frontend stores PATCH responses straight back into in-memory state. If we
    # don't eager-load, Pydantic's from_attributes hits an async lazy-load
    # (MissingGreenlet) at best, or silently emits null at worst — the latter
    # is the bug users reported as "link disappears after autosave."
    profile = await db.scalar(
        select(Profile)
        .where(Profile.id == profile_id)
        .options(selectinload(Profile.linked_league))
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your profile")

    if body.name is not None:
        profile.name = body.name
    if body.settings_json is not None:
        profile.settings_json = body.settings_json
    if body.rules_json is not None:
        profile.rules_json = body.rules_json

    await db.commit()
    await db.refresh(profile, attribute_names=["linked_league"])
    return ProfileOut.model_validate(profile)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your profile")

    if user.last_active_profile_id == profile.id:
        user.last_active_profile_id = None

    await db.delete(profile)
    await db.commit()


@router.post("/{profile_id}/activate", status_code=204)
async def activate_profile(
    profile_id: uuid.UUID,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your profile")
    user.last_active_profile_id = profile.id
    # Bump updated_at so the list endpoint (ordered by updated_at desc)
    # surfaces the active profile at the top after activation.
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
