import pytest
import respx
from httpx import Response
from app.auth.yahoo import build_authorize_url, exchange_code, fetch_subject


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(state="random123")
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "state=random123" in url


@pytest.mark.asyncio
async def test_exchange_code_returns_access_token():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(return_value=Response(
            200, json={"access_token": "the-access-token", "token_type": "bearer", "expires_in": 3600}
        ))
        token = await exchange_code("the-code")
    assert token == "the-access-token"


@pytest.mark.asyncio
async def test_exchange_code_raises_on_error():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.post("/oauth2/get_token").mock(return_value=Response(400, json={"error": "invalid_grant"}))
        with pytest.raises(Exception):
            await exchange_code("bad-code")


@pytest.mark.asyncio
async def test_fetch_subject_returns_sub_claim():
    with respx.mock(base_url="https://api.login.yahoo.com") as router:
        router.get("/openid/v1/userinfo").mock(return_value=Response(
            200, json={"sub": "yahoo-user-abc"}
        ))
        sub = await fetch_subject("access-token")
    assert sub == "yahoo-user-abc"
