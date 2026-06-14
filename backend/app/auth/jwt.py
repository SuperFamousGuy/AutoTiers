"""JWT encode/decode + cookie helpers.

We embed the user's id and token_version in the token. Anything else
(email, profile id) is read from the DB so token leaks don't expose state.

The "v" claim carries token_version. Tokens without a "v" claim are treated
as v=0 (backward-compatible with pre-#241 cookies; existing users migrate to
token_version=0 so they stay logged in across the deploy).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Response
from app.config import settings


JWT_COOKIE_NAME = "autotiers_session"
_DEFAULT_TTL = timedelta(days=30)


class JWTInvalid(Exception):
    """Raised when a JWT is malformed, expired, or signature invalid."""


@dataclass(frozen=True)
class JWTClaims:
    user_id: uuid.UUID
    token_version: int


def encode_jwt(user_id: uuid.UUID, token_version: int = 0, ttl: timedelta = _DEFAULT_TTL) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "v": token_version, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_jwt(token: str) -> JWTClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise JWTInvalid(str(e)) from e
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise JWTInvalid("missing/invalid sub claim") from e
    # "v" claim is absent on pre-#241 tokens — treat as version 0.
    token_version = int(payload.get("v", 0))
    return JWTClaims(user_id=user_id, token_version=token_version)


def set_auth_cookie(response: Response, user: "User", *, secure: Optional[bool] = None) -> None:
    """Set the session cookie. In test/dev, secure=False so non-HTTPS works.

    Takes the full User object so it can embed both user.id and user.token_version.
    """
    if secure is None:
        secure = not settings.debug
    response.set_cookie(
        key=JWT_COOKIE_NAME,
        value=encode_jwt(user.id, user.token_version),
        max_age=int(_DEFAULT_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=JWT_COOKIE_NAME, path="/")
