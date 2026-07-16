"""Yahoo OAuth2 client.

Used for identity: we exchange the auth code for a token, fetch the
subject + email + email_verified claims, and discard the token. We trust
`email_verified` for auto-linking on first sign-in — see the design doc's
"Email-collision policy" section.

When fantasy=True is passed to build_authorize_url, the fspt-r scope is
added and exchange_code will return a refresh_token for offline access.
"""
from urllib.parse import urlencode
import httpx
from app.config import settings


AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
USERINFO_URL = "https://api.login.yahoo.com/openid/v1/userinfo"


def build_authorize_url(state: str, fantasy: bool = False) -> str:
    scope = "openid email fspt-r" if fantasy else "openid email"
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.yahoo_redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> tuple[str, str | None]:
    """Exchange an auth code for tokens.

    Returns (access_token, refresh_token). refresh_token is None when Yahoo
    did not return one (identity-only scope flows).
    Raises httpx.HTTPStatusError on non-2xx.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": settings.yahoo_redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data.get("refresh_token")


async def refresh_access_token(refresh_token: str) -> tuple[str, str | None]:
    """Exchange a refresh token for a new access token.

    Returns (access_token, refresh_token). refresh_token is None when Yahoo
    did not rotate it; when it is non-None Yahoo has issued a new refresh token
    and the caller MUST persist it, or the next refresh will use a stale token
    and force an avoidable reconnect. Mirrors exchange_code's tuple shape.

    Raises httpx.HTTPStatusError on non-2xx (including 401 when the refresh
    token has been revoked — callers should surface this as a reconnect prompt).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": settings.yahoo_redirect_uri,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data.get("refresh_token")


async def fetch_identity(access_token: str) -> tuple[str, str | None, bool]:
    """Fetch the openid `sub`, `email`, and `email_verified` claims from Yahoo's userinfo endpoint.

    Returns (subject, email, email_verified). email is None and email_verified is False
    if the provider declines to return them.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["sub"], data.get("email"), data.get("email_verified") is True
