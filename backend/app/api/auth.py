"""Email/password auth endpoints. Yahoo OAuth lives in this same router but is added in phase 3."""
import copy
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.defaults import DEFAULT_PROFILE_SETTINGS
from app.models import User, Profile
from app.models.auth_token import AuthToken
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt import set_auth_cookie, clear_auth_cookie
from app.auth.dependencies import require_user, _resolve_user
from app.auth.rate_limit import login_rate_limiter, reset_rate_limiter, verify_rate_limiter
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_identity
from app.auth.email_dep import get_email_sender
from app.email.sender import EmailSender
from app.email.templates import reset_password_email, verify_email_email
from app.security.fernet import encrypt
from app.auth.google import (
    build_authorize_url as build_google_authorize_url,
    exchange_code as exchange_google_code,
    fetch_identity as fetch_google_identity,
)
from app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    UserOut,
    MeResponse,
    ProfileOut,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    SetPasswordRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Token TTLs ---
_RESET_TOKEN_TTL = timedelta(hours=1)
_VERIFY_TOKEN_TTL = timedelta(hours=72)


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw token. Never stored raw."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _make_reset_url(raw_token: str) -> str:
    """Build the password-reset deep-link for the frontend."""
    return _frontend_url_with_param("reset_token", raw_token)


def _make_verify_url(raw_token: str) -> str:
    """Build the email-verification deep-link for the frontend."""
    return _frontend_url_with_param("verify_token", raw_token)


async def _issue_auth_token(
    db: AsyncSession,
    user_id,
    token_type: str,
    ttl: timedelta,
) -> str:
    """Create a new single-use auth token, deleting any prior unused tokens of
    the same type for this user (one-active-per-user-per-type policy).

    Returns the raw (unhashed) token — the caller must send this to the user
    and must NOT persist it.
    """
    # Delete any existing unused tokens of this type for this user.
    await db.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.token_type == token_type,
            AuthToken.used_at.is_(None),
        )
    )

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    auth_token = AuthToken(
        user_id=user_id,
        token_hash=token_hash,
        token_type=token_type,
        expires_at=now + ttl,
        created_at=now,
    )
    db.add(auth_token)
    await db.flush()
    return raw_token


async def _consume_auth_token(
    db: AsyncSession,
    raw_token: str,
    expected_type: str,
) -> AuthToken:
    """Atomically mark a token as used and return it.

    Uses a single conditional UPDATE ... RETURNING so that two concurrent
    calls for the same token can never both succeed — the DB guarantees
    exactly one UPDATE wins. If zero rows are affected, a follow-up SELECT
    identifies the specific error (not found, wrong type, already used,
    expired) and raises the appropriate 400.
    """
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    # Atomic: mark used only if the token exists, is the right type, is
    # unused, and has not yet expired. Concurrent calls race here; only one
    # will see rowcount > 0.
    result = await db.execute(
        update(AuthToken)
        .where(
            AuthToken.token_hash == token_hash,
            AuthToken.token_type == expected_type,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(AuthToken)
    )
    row = result.scalars().first()

    if row is not None:
        return row

    # Update touched zero rows — determine why for a useful error message.
    record = await db.scalar(
        select(AuthToken).where(AuthToken.token_hash == token_hash)
    )
    if record is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if record.token_type != expected_type:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if record.used_at is not None:
        raise HTTPException(status_code=400, detail="This link has already been used")
    # Must be expired (the only remaining case).
    raise HTTPException(status_code=400, detail="This link has expired")


@router.post("/signup", status_code=201, response_model=MeResponse)
async def signup(
    body: SignupRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
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

    # Issue a verification token and enqueue the email as a background task.
    raw_verify_token = await _issue_auth_token(db, user.id, "email_verify", _VERIFY_TOKEN_TTL)
    await db.commit()
    await db.refresh(user)

    set_auth_cookie(response, user)

    verify_url = _make_verify_url(raw_verify_token)
    background_tasks.add_task(
        _send_verification_email_task,
        email_sender=email_sender,
        to=body.email,
        verify_url=verify_url,
    )

    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).options(selectinload(Profile.linked_league))
    )).all()
    return MeResponse(user=UserOut.model_validate(user), profiles=[ProfileOut.model_validate(p) for p in profiles])


async def _send_verification_email_task(
    *,
    email_sender: EmailSender,
    to: str,
    verify_url: str,
) -> None:
    """Background task: send the verification email. Errors are logged but not raised."""
    try:
        html, text = verify_email_email(verify_url)
        await email_sender.send(
            to=to,
            subject="Verify your AutoTiers email",
            html=html,
            text=text,
        )
    except Exception:
        logger.exception("Failed to send verification email to %s", to)


@router.post("/login", response_model=MeResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    # Pydantic EmailStr already lowercases the domain (RFC 5321 domains are
    # case-insensitive); local parts are left as provided. Key the rate limiter
    # on the fully lowercased email so casing variants (Attacker@Example.com vs
    # attacker@example.com) share one attempt bucket and can't each be used to
    # reset the 5-attempt limit. Mirrors the normalisation in forgot_password.
    if not login_rate_limiter.check_and_record(body.email.strip().lower()):
        raise HTTPException(status_code=429, detail="Too many attempts; try again later")

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    set_auth_cookie(response, user)
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


# ---------------------------------------------------------------------------
# Forgot / Reset password (Slice 3)
# ---------------------------------------------------------------------------

@router.post("/password/forgot", status_code=202)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
) -> dict:
    """Always returns 202 regardless of whether the email exists.

    This endpoint is non-enumerating — the same response is returned whether
    the email is registered, unregistered, OAuth-only, or unverified.
    """
    # Pydantic EmailStr normalises the domain to lowercase (RFC 5321 domains
    # are case-insensitive); local parts are left as provided. Match what the
    # signup stored — do NOT add extra lowercasing that signup doesn't do.
    email = str(body.email)

    if not reset_rate_limiter.check_and_record(email.lower()):
        raise HTTPException(status_code=429, detail="Too many requests; please wait before trying again")

    # Look up the user silently — do NOT branch on existence in the response.
    user = await db.scalar(select(User).where(User.email == email))

    if user is not None:
        raw_token = await _issue_auth_token(db, user.id, "password_reset", _RESET_TOKEN_TTL)
        await db.commit()
        reset_url = _make_reset_url(raw_token)
        background_tasks.add_task(
            _send_reset_email_task,
            email_sender=email_sender,
            to=email,
            reset_url=reset_url,
        )

    return {"detail": "If that email is registered, a reset link is on its way."}


async def _send_reset_email_task(
    *,
    email_sender: EmailSender,
    to: str,
    reset_url: str,
) -> None:
    """Background task: send the password-reset email. Errors are logged but not raised."""
    try:
        html, text = reset_password_email(reset_url)
        await email_sender.send(
            to=to,
            subject="Reset your AutoTiers password",
            html=html,
            text=text,
        )
    except Exception:
        logger.exception("Failed to send password-reset email to %s", to)


@router.post("/password/reset", response_model=MeResponse)
async def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Consume a password-reset token and set a new password.

    On success, issues a session cookie (the user is logged in after reset).
    Password reset also sets email_verified=True (inbox control proven).

    Bumps token_version BEFORE issuing the new cookie so the acting session
    gets the new version while all prior sessions (with the old version) are
    invalidated. (#241)
    """
    token_record = await _consume_auth_token(db, body.token, "password_reset")

    user = await db.get(User, token_record.user_id)
    if user is None:
        # Should not happen (CASCADE delete would remove tokens with user), but be safe.
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.email_verified = True  # inbox control proven by reset link
    # Invalidate all prior sessions. Bump BEFORE set_auth_cookie so the
    # cookie we issue below carries the NEW version and survives.
    user.token_version += 1

    await db.commit()
    await db.refresh(user)

    set_auth_cookie(response, user)

    profiles = (await db.scalars(
        select(Profile).where(Profile.user_id == user.id).options(selectinload(Profile.linked_league))
    )).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        profiles=[ProfileOut.model_validate(p) for p in profiles],
    )


# ---------------------------------------------------------------------------
# Email verification (Slice 4)
# ---------------------------------------------------------------------------

@router.post("/email/resend-verification", status_code=202)
async def resend_verification(
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
) -> dict:
    """Resend the email-verification link to the authenticated user.

    The send is performed INLINE (awaited) rather than fire-and-forget in a
    BackgroundTask, so that a real send failure (e.g. SES MessageRejected)
    surfaces to the client as an error instead of a false 202. This is a
    deliberate sync-over-async tradeoff (#274): honesty requires knowing the
    send outcome before responding, and the latency cost is a single SES
    SendEmail call on a rate-limited, user-initiated action. The user is
    already waiting for the email, so the extra round-trip is acceptable.

    NOTE: signup's verification email and the password-reset email remain
    fire-and-forget BackgroundTasks on purpose — signup must succeed even if
    email is slow, and the reset path is non-enumerating (it must not leak
    account existence via a differential send-failure response).
    """
    if not verify_rate_limiter.check_and_record(str(user.id)):
        raise HTTPException(status_code=429, detail="Too many requests; please wait before trying again")

    if user.email is None:
        raise HTTPException(status_code=400, detail="No email address on this account")
    if user.email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")

    raw_token = await _issue_auth_token(db, user.id, "email_verify", _VERIFY_TOKEN_TTL)
    await db.commit()

    verify_url = _make_verify_url(raw_token)
    try:
        html, text = verify_email_email(verify_url)
        await email_sender.send(
            to=user.email,
            subject="Verify your AutoTiers email",
            html=html,
            text=text,
        )
    except Exception:
        # The user is authenticated and known, so there is no enumeration
        # surface here — it is safe to tell them the send failed. 502 (not
        # 5xx-generic) names the upstream email dependency as the cause; the
        # frontend banner reverts to its retryable "default" state on any
        # non-429 error.
        logger.exception("Failed to send verification email to %s", user.email)
        raise HTTPException(
            status_code=502,
            detail="Could not send the verification email. Please try again.",
        )

    return {"detail": "Verification email sent."}


@router.get("/email/verify", status_code=204)
async def verify_email(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Verify an email address using a verification token."""
    token_record = await _consume_auth_token(db, token, "email_verify")

    user = await db.get(User, token_record.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user.email_verified = True
    await db.commit()


# ---------------------------------------------------------------------------
# Change / Set password (Slice 5)
# ---------------------------------------------------------------------------

@router.post("/password/change", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change the password for an authenticated user who already has one.

    Bumps token_version to invalidate all OTHER sessions, then re-issues the
    session cookie with the new version so THIS device stays logged in. (#241)
    """
    if user.password_hash is None:
        raise HTTPException(
            status_code=400,
            detail="No password set on this account — use set-password instead",
        )

    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if verify_password(user.password_hash, body.new_password):
        raise HTTPException(
            status_code=400,
            detail="New password must differ from current password",
        )

    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    # Invalidate all OTHER sessions. Re-issue the cookie below so THIS device
    # stays logged in with the new version.
    user.token_version += 1
    await db.commit()
    await db.refresh(user)

    set_auth_cookie(response, user)


@router.post("/password/set", status_code=204)
async def set_password(
    body: SetPasswordRequest,
    user: User = require_user,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Set a password on an OAuth-only account that currently has none.

    NOTE: We deliberately do NOT bump token_version here. set_password is
    additive — an OAuth-only user is adding a first password. There are no
    prior password-based sessions to invalidate, and bumping would be
    surprising (it would log out any other OAuth sessions with no reason).
    """
    if user.password_hash is not None:
        raise HTTPException(
            status_code=400,
            detail="Account already has a password — use change-password instead",
        )

    if user.email is None:
        raise HTTPException(
            status_code=400,
            detail="An email address is required to set a password",
        )

    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# OAuth helpers (unchanged from original)
# ---------------------------------------------------------------------------

_OAUTH_STATE_COOKIE = "autotiers_oauth_state"


def _frontend_url_with_param(key: str, value: str) -> str:
    """Append (or merge) a single query param onto settings.frontend_url.

    Safe whether or not the configured frontend URL already carries a query string.
    """
    parts = urlsplit(settings.frontend_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(parts._replace(query=urlencode(query)))


async def _seed_default_profile(db: AsyncSession, user: User) -> Profile:
    """Create the default "My setup" profile for a freshly-created OAuth user
    and mark it active.

    OAuth first-login callbacks don't carry the frontend's live state (unlike
    email/password signup, which passes initial_settings/initial_rules), so we
    seed with the server-side mirror of the frontend DEFAULT_SETTINGS. Without
    this the user lands with last_active_profile_id=None and every Settings/
    Rules edit is silently discarded because autosave is gated on an active
    profile (#606).

    The caller must have already flushed `user` so that `user.id` is populated.
    """
    profile = Profile(
        user_id=user.id,
        name="My setup",
        settings_json=copy.deepcopy(DEFAULT_PROFILE_SETTINGS),
        rules_json={},
    )
    db.add(profile)
    await db.flush()
    user.last_active_profile_id = profile.id
    return profile


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
        await db.flush()
        # Seed a default profile so the new user has somewhere for autosave to
        # persist to — OAuth callbacks carry no frontend state, so mirror the
        # frontend defaults server-side (#606).
        await _seed_default_profile(db, user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
    set_auth_cookie(response, user)
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
        await db.flush()
        # Seed a default profile so the new user has somewhere for autosave to
        # persist to — OAuth callbacks carry no frontend state, so mirror the
        # frontend defaults server-side (#606).
        await _seed_default_profile(db, user)
        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.delete_cookie(_GOOGLE_OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(_OAUTH_INTENT_COOKIE, path="/")
    set_auth_cookie(response, user)
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
    has_subject = user.yahoo_subject is not None
    has_tokens = (
        user.yahoo_access_token is not None
        or user.yahoo_refresh_token is not None
    )
    if not has_subject and not has_tokens:
        return  # idempotent — nothing to unlink
    # A live sign-in subject may only be removed if another method remains.
    # Legacy null-subject rows (subject already None, tokens still populated
    # from the old subject-null bug) skip this guard and just get revoked.
    if has_subject and not _has_other_method(user, "yahoo_subject"):
        raise HTTPException(status_code=400, detail="Cannot unlink last sign-in method")
    user.yahoo_subject = None
    # Revoke the Fantasy OAuth grant too. The linked-league endpoints gate on
    # yahoo_access_token/yahoo_refresh_token (not yahoo_subject), so leaving these
    # live would let Fantasy sync survive a "Disconnect" (issue #500).
    user.yahoo_access_token = None
    user.yahoo_refresh_token = None
    await db.commit()
