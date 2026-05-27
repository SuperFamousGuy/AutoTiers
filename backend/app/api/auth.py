"""Email/password auth endpoints. Yahoo OAuth lives in this same router but is added in phase 3."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Profile
from app.auth.hashing import hash_password
from app.auth.jwt import set_auth_cookie
from app.schemas.auth import SignupRequest, UserOut, MeResponse, ProfileOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=201, response_model=MeResponse)
async def signup(
    body: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already in use")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()

    profile: Profile | None = None
    if body.initial_settings is not None and body.initial_rules is not None:
        profile = Profile(
            user_id=user.id,
            name="My setup",
            settings_json=body.initial_settings,
            rules_json=body.initial_rules,
        )
        db.add(profile)
        await db.flush()
        user.last_active_profile_id = profile.id

    await db.commit()
    await db.refresh(user)

    set_auth_cookie(response, user.id)

    profiles = [ProfileOut.model_validate(profile)] if profile else []
    return MeResponse(user=UserOut.model_validate(user), profiles=profiles)
