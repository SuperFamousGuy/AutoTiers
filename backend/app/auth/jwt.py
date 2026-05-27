"""JWT encode/decode + cookie helpers.

We embed only the user's id in the token. Anything else (email, profile id)
is read from the DB so token leaks don't expose state.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Response
from app.config import settings


JWT_COOKIE_NAME = "autotiers_session"
_DEFAULT_TTL = timedelta(days=30)


class JWTInvalid(Exception):
    """Raised when a JWT is malformed, expired, or signature invalid."""


def encode_jwt(user_id: uuid.UUID, ttl: timedelta = _DEFAULT_TTL) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_jwt(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise JWTInvalid(str(e)) from e
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise JWTInvalid("missing/invalid sub claim") from e


def set_auth_cookie(response: Response, user_id: uuid.UUID, *, secure: Optional[bool] = None) -> None:
    """Set the session cookie. In test/dev, secure=False so non-HTTPS works."""
    if secure is None:
        secure = not settings.debug if hasattr(settings, "debug") else True
    response.set_cookie(
        key=JWT_COOKIE_NAME,
        value=encode_jwt(user_id),
        max_age=int(_DEFAULT_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=JWT_COOKIE_NAME, path="/")
