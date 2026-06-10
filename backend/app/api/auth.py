"""Email/password auth endpoints. Yahoo OAuth lives in this same router but is added in phase 3."""
import secrets
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import User, Profile
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt import set_auth_cookie, clear_auth_cookie
from app.auth.dependencies import require_user, _resolve_user
from app.auth.rate_limit import login_rate_limiter
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_identity
from app.security.fernet import encrypt
from app.auth.google import (
    build_authorize_url as build_google_authorize_url,
    exchange_code as exchange_google_code,
    fetch_identity as fetch_google_identity,
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

    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).options(selectinload(Profile.linked_league))
    )).all()
    return MeResponse(user=UserOut.model_validate(user), profiles=[ProfileOut.model_validate(p) for p in profiles])


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
    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).options(selectinload(Profile.linked_league))
    )).all()
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
    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).options(selectinload(Profile.linked_league))
    )).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        profiles=[ProfileOut.model_validate(p) for p in profiles],
    )


_OAUTH_STATE_COOKIE = "autotiers_oauth_state"


def _frontend_url_with_param(key: str, value: str) -> str:
    """Append (or merge) a single query param onto settings.frontend_url.

    Safe whether or not the configured frontend URL already carries a query string.
    """
    parts = urlsplit(settings.frontend_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(parts._replace(query=urlencode(query)))


async def _handle_oauth_link(
    db: AsyncSession,
    current_user: User,
    subject_attr: str,
    subject: str,
    email: str | None,
    email_verified: bool,
    state_cookie_name: str,
) -> RedirectResponse:
    """Run the linking branch of an OAuth callback.

    Attaches `subject` to `current_user.<subject_attr>` unless that subject is
    already on a different user (returns linking_error redirect). Backfills
    current_user.email if absent and the provider returned a verified email.
    Returns a RedirectResponse (with the state cookie deleted) that does NOT
    re-issue the session cookie — the caller is already authenticated.
    """
    existing_owner = await db.scalar(
        select(User).where(getattr(User, subject_attr) == subject)
    )
    if existing_owner is not None and existing_owner.id != current_user.id:
        url = _frontend_url_with_param("linking_error", "already_linked_elsewhere")
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(state_cookie_name, path="/")
        return response

    mutated = False
    if existing_owner is None:
        setattr(current_user, subject_attr, subject)
        mutated = True
    if current_user.email is None and email_verified and email:
        current_user.email = email
        mutated = True
    if mutated:
        await db.commit()

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(state_cookie_name, path="/")
    return response


# Set alongside the state cookie when the user clicks 'Connect' from inside
# the app (signalling 'link to my current account', NOT 'sign in / sign up').
# We use this in the callback to avoid silently creating a new account when
# the session cookie failed to travel — we'd rather error out and ask the
# user to retry than orphan their existing data on a phantom user.
_OAUTH_INTENT_COOKIE = "autotiers_oauth_intent"


def _set_oauth_state_cookies(response, state_cookie_name: str, state: str, intent: str | None) -> None:
    response.set_cookie(
        key=state_cookie_name,
        value=state,
        max_age=600,  # 10 min
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
    )
    if intent in ("link", "yahoo_fantasy"):
        response.set_cookie(
            key=_OAUTH_INTENT_COOKIE,
            value="yahoo_fantasy" if intent == "yahoo_fantasy" else "link",
            max_age=600,
            httponly=True,
            secure=not settings.debug,
            samesite="lax",
            path="/",
        )


@router.get("/yahoo/authorize")
async def yahoo_authorize(intent: str | None = None) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    fantasy = intent == "yahoo_fantasy"
    response = RedirectResponse(url=build_authorize_url(state, fantasy=fantasy), status_code=307)
    _set_oauth_state_cookies(response, _OAUTH_STATE_COOKIE, state, intent)
    return response


@router.get("/yahoo/callback")
async def yahoo_callback(
    code: str,
    state: str,
    autotiers_oauth_state: str | None = Cookie(default=None),
    autotiers_session: str | None = Cookie(default=None),
    autotiers_oauth_intent: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_oauth_state or autotiers_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token, refresh_token = await exchange_code(code)
    yahoo_subject, yahoo_email, yahoo_email_verified = await fetch_identity(access_token)

    current_user = await _resolve_user(autotiers_session, db)

    if current_user is not None:
        # Store tokens when this is a fantasy connect intent.
        if autotiers_oauth_intent == "yahoo_fantasy" and refresh_token:
            current_user.yahoo_access_token = encrypt(access_token)
            current_user.yahoo_refresh_token = encrypt(refresh_token)
            await db.commit()

        return await _handle_oauth_link(
            db,
            current_user,
            subject_attr="yahoo_subject",
            subject=yahoo_subject,
            email=yahoo_email,
            email_verified=yahoo_email_verified,
            state_cookie_name=_OAUTH_STATE_COOKIE,
        )

    # The user clicked "Connect" from inside the app intending to link, but
    # we couldn't resolve their session. Bail out instead of silently signing
    # them in as a different account and orphaning their existing profile.
    if autotiers_oauth_intent in ("link", "yahoo_fantasy"):
        url = _frontend_url_with_param("linking_error", "session_lost")
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
        response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
        return response

    # Sign-in flow only — linking flow handled above.
    user = await db.scalar(select(User).where(User.yahoo_subject == yahoo_subject))
    if user is None and yahoo_email_verified and yahoo_email:
        user = await db.scalar(select(User).where(User.email == yahoo_email))
        if user is not None:
            user.yahoo_subject = yahoo_subject
            await db.commit()
            await db.refresh(user)
    if user is None:
        user = User(yahoo_subject=yahoo_subject)
        if yahoo_email_verified and yahoo_email:
            user.email = yahoo_email
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response


_GOOGLE_OAUTH_STATE_COOKIE = "autotiers_google_oauth_state"


@router.get("/google/authorize")
async def google_authorize(intent: str | None = None) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(url=build_google_authorize_url(state), status_code=307)
    _set_oauth_state_cookies(response, _GOOGLE_OAUTH_STATE_COOKIE, state, intent)
    return response


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    autotiers_google_oauth_state: str | None = Cookie(default=None),
    autotiers_session: str | None = Cookie(default=None),
    autotiers_oauth_intent: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not autotiers_google_oauth_state or autotiers_google_oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token = await exchange_google_code(code)
    google_subject, google_email, google_email_verified = await fetch_google_identity(access_token)

    current_user = await _resolve_user(autotiers_session, db)

    if current_user is not None:
        return await _handle_oauth_link(
            db,
            current_user,
            subject_attr="google_subject",
            subject=google_subject,
            email=google_email,
            email_verified=google_email_verified,
            state_cookie_name=_GOOGLE_OAUTH_STATE_COOKIE,
        )

    if autotiers_oauth_intent == "link":
        url = _frontend_url_with_param("linking_error", "session_lost")
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
        response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
        return response

    # Sign-in flow only — linking flow handled above.
    user = await db.scalar(select(User).where(User.google_subject == google_subject))
    if user is None and google_email_verified and google_email:
        user = await db.scalar(select(User).where(User.email == google_email))
        if user is not None:
            user.google_subject = google_subject  # auto-link
            await db.commit()
            await db.refresh(user)
    if user is None:
        user = User(google_subject=google_subject)
        if google_email_verified and google_email:
            user.email = google_email
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
    set_auth_cookie(response, user.id)
    return response


def _has_other_method(user: User, removing: str) -> bool:
    """True if the user has at least one sign-in method besides `removing`.

    `removing` is one of: "password", "yahoo_subject", "google_subject".
    """
    methods = {
        "password": user.password_hash is not None,
        "yahoo_subject": user.yahoo_subject is not None,
        "google_subject": user.google_subject is not None,
    }
    methods[removing] = False
    return any(methods.values())


@router.delete("/google/link", status_code=204)
async def unlink_google(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.google_subject is None:
        return  # idempotent
    if not _has_other_method(user, "google_subject"):
        raise HTTPException(status_code=400, detail="Cannot unlink last sign-in method")
    user.google_subject = None
    await db.commit()


@router.delete("/yahoo/link", status_code=204)
async def unlink_yahoo(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.yahoo_subject is None:
        return
    if not _has_other_method(user, "yahoo_subject"):
        raise HTTPException(status_code=400, detail="Cannot unlink last sign-in method")
    user.yahoo_subject = None
    await db.commit()
