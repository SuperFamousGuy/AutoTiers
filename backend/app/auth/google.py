"""Google OAuth2 client.

Used for identity: we exchange the auth code for a token, fetch the
subject + email + email_verified claims, and discard the token. We trust
`email_verified` for auto-linking on first sign-in — see the design doc's
"Email-collision policy" section.
"""
from urllib.parse import urlencode
import httpx
from app.config import settings


AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "access_type": "online",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange an auth code for an access token. Returns the access_token string.

    Raises httpx.HTTPStatusError on non-2xx.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def fetch_identity(access_token: str) -> tuple[str, str | None, bool]:
    """Fetch the openid `sub`, `email`, and `email_verified` claims from Google's userinfo endpoint.

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
