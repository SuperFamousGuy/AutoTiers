"""Profile CRUD endpoints. All require auth."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
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


def _validate_and_normalize_name(name: str) -> str:
    """Trim and reject blank/whitespace-only profile names.

    Mirrors favorites_api._validate_and_normalize: a name like " " passes
    Pydantic's min_length=1 (a single space has len 1) but produces an
    invisibly-blank profile, indistinguishable from others in the switcher.
    Reject with 422 and persist the trimmed value.
    """
    trimmed = name.strip()
    if not trimmed:
        raise HTTPException(status_code=422, detail="Profile name cannot be blank.")
    return trimmed


def _is_duplicate_name_violation(exc: IntegrityError) -> bool:
    """True only when the IntegrityError is the (user_id, name) uniqueness
    violation — not some unrelated constraint.

    Matches both dialects: Postgres surfaces the constraint name
    (``uq_profiles_user_name``) in the error text; SQLite reports the offending
    column list (``profiles.user_id, profiles.name``). Any other integrity
    failure must not be masked behind a misleading duplicate-name 409.
    """
    message = str(getattr(exc, "orig", None) or exc)
    return (
        "uq_profiles_user_name" in message
        or "profiles.user_id, profiles.name" in message
    )


def _duplicate_name_error(name: str) -> HTTPException:
    """The 409 raised when a user already has a profile with this name.

    Enforced two ways: a fast pre-check for the happy path, and a catch on the
    DB IntegrityError (uq_profiles_user_name) as the authoritative guard against
    the TOCTOU race between the pre-check and the commit.
    """
    return HTTPException(
        status_code=409,
        detail=f"You already have a profile named '{name}'. Choose a different name.",
    )


async def _name_taken(
    db: AsyncSession, user_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> bool:
    """True if `user_id` already has a profile named `name` (excluding exclude_id)."""
    stmt = select(func.count(Profile.id)).where(
        Profile.user_id == user_id, Profile.name == name
    )
    if exclude_id is not None:
        stmt = stmt.where(Profile.id != exclude_id)
    return bool(await db.scalar(stmt))


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
    name = _validate_and_normalize_name(body.name)
    count = await db.scalar(
        select(func.count(Profile.id)).where(Profile.user_id == user.id)
    ) or 0
    if count >= _PROFILE_CAP:
        raise HTTPException(
            status_code=409,
            detail=f"Profile limit reached ({_PROFILE_CAP}). Delete one to add another.",
        )
    if await _name_taken(db, user.id, name):
        raise _duplicate_name_error(name)
    profile = Profile(
        user_id=user.id,
        name=name,
        settings_json=body.settings_json,
        rules_json=body.rules_json,
    )
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Lost the race against a concurrent create with the same name.
        await db.rollback()
        if not _is_duplicate_name_violation(exc):
            # A different constraint failed — surface the real error as a 500
            # rather than a misleading duplicate-name 409.
            raise
        raise _duplicate_name_error(name)
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

    attempted_name = profile.name
    if body.name is not None:
        attempted_name = _validate_and_normalize_name(body.name)
        # Excludes this profile so renaming to its own current name is a no-op,
        # not a self-collision.
        if attempted_name != profile.name and await _name_taken(
            db, user.id, attempted_name, exclude_id=profile.id
        ):
            raise _duplicate_name_error(attempted_name)
        profile.name = attempted_name
    if body.settings_json is not None:
        profile.settings_json = body.settings_json
    if body.rules_json is not None:
        profile.rules_json = body.rules_json

    try:
        await db.commit()
    except IntegrityError as exc:
        # Lost the race against a concurrent rename to the same name.
        await db.rollback()
        if not _is_duplicate_name_violation(exc):
            # A different constraint failed — surface the real error as a 500
            # rather than a misleading duplicate-name 409.
            raise
        raise _duplicate_name_error(attempted_name)
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
