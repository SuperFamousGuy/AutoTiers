"""Email/password auth endpoints. Yahoo OAuth lives in this same router but is added in phase 3."""
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User, Profile
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt import set_auth_cookie, clear_auth_cookie
from app.auth.dependencies import require_user
from app.auth.rate_limit import login_rate_limiter
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_subject
from app.auth.google import (
    build_authorize_url as build_google_authorize_url,
    exchange_code as exchange_google_code,
    fetch_subject as fetch_google_subject,
)
from app.schemas.auth import SignupRequest, LoginRequest, UserOut, MeResponse, ProfileOut

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


@router.post("/login", response_model=MeResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    if not login_rate_limiter.check_and_record(body.email):
        raise HTTPException(status_code=429, detail="Too many attempts; try again later")

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    set_auth_cookie(response, user.id)
    profiles = (await db.scalars(select(Profile).where(Profile.user_id == user.id))).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        profiles=[ProfileOut.model_validate(p) for p in profiles],
    )


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_auth_cookie(response)


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    profiles = (await db.scalars(select(Profile).where(Profile.user_id == user.id))).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        profiles=[ProfileOut.model_validate(p) for p in profiles],
    )


_OAUTH_STATE_COOKIE = "autotiers_oauth_state"


@router.get("/yahoo/authorize")
async def yahoo_authorize() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(url=build_authorize_url(state), status_code=307)
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,  # 10 min
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/yahoo/callback")
async def yahoo_callback(
    code: str,
    state: str,
    autotiers_oauth_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_oauth_state or autotiers_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token = await exchange_code(code)
    yahoo_subject = await fetch_subject(access_token)

    user = await db.scalar(select(User).where(User.yahoo_subject == yahoo_subject))
    if user is None:
        user = User(yahoo_subject=yahoo_subject)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response


_GOOGLE_OAUTH_STATE_COOKIE = "autotiers_google_oauth_state"


@router.get("/google/authorize")
async def google_authorize() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(url=build_google_authorize_url(state), status_code=307)
    response.set_cookie(
        key=_GOOGLE_OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    autotiers_google_oauth_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_google_oauth_state or autotiers_google_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token = await exchange_google_code(code)
    google_subject = await fetch_google_subject(access_token)

    user = await db.scalar(select(User).where(User.google_subject == google_subject))
    if user is None:
        user = User(google_subject=google_subject)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response
