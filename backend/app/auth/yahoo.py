"""Yahoo OAuth2 client.

Used solely for identity: we exchange the auth code for a token, fetch the
subject claim, and discard the token. We deliberately do not request email
scope or store any Yahoo tokens — see the design doc's "Email-collision
avoidance" section.
"""
from urllib.parse import urlencode
import httpx
from app.config import settings


AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
USERINFO_URL = "https://api.login.yahoo.com/openid/v1/userinfo"


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.yahoo_redirect_uri,
        "response_type": "code",
        "scope": "openid",
        "state": state,
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
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": settings.yahoo_redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def fetch_subject(access_token: str) -> str:
    """Fetch the openid `sub` claim from Yahoo's userinfo endpoint."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()["sub"]
