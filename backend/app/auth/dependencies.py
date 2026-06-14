"""FastAPI auth dependencies.

  - `get_current_user` — Optional[User]; None if no/invalid cookie. Use this when
    a route should work both anonymously and authenticated.
  - `require_user` — User; raises HTTPException(401) if missing. Use this when
    a route must be authenticated.
"""
from typing import Optional
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User
from app.auth.jwt import decode_jwt, JWTInvalid, JWT_COOKIE_NAME


async def _resolve_user(
    cookie_value: Optional[str],
    db: AsyncSession,
) -> Optional[User]:
    if not cookie_value:
        return None
    try:
        claims = decode_jwt(cookie_value)
    except JWTInvalid:
        return None
    user = await db.get(User, claims.user_id)
    if user is None:
        return None
    # Reject any token whose version doesn't match the current user version.
    # This invalidates all sessions issued before a password reset/change.
    # No extra DB read required — we already loaded the user above.
    if claims.token_version != user.token_version:
        return None
    return user


async def _get_current_user_impl(
    autotiers_session: Optional[str] = Cookie(default=None, alias=JWT_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    return await _resolve_user(autotiers_session, db)


async def _require_user_impl(
    user: Optional[User] = Depends(_get_current_user_impl),
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


get_current_user = Depends(_get_current_user_impl)
require_user = Depends(_require_user_impl)
