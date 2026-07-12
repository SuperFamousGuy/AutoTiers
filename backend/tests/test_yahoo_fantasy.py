"""Tests for the Yahoo Fantasy API client."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from app.integrations.yahoo_fantasy import (
    list_user_leagues,
    fetch_league,
    _parse_leagues,
    YahooLeagueSummary,
    YahooLeagueData,
    YahooReauthRequired,
    YahooLeaguesParseError,
)

# Yahoo's OAuth token endpoint that refresh_access_token POSTs to.
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


LEAGUES_RESPONSE = {
    "fantasy_content": {
        "users": {
            "0": {
                "user": [
                    {"guid": "ABCDEF"},
                    {
                        "games": {
                            "0": {
                                "game": [
                                    {"game_key": "423", "season": "2024"},
                                    {
                                        "leagues": {
                                            "0": {
                                                "league": [
                                                    {
                                                        "league_key": "423.l.12345",
                                                        "name": "My FF League",
                                                        "num_teams": "12",
                                                        "season": "2024",
                                                    }
                                                ]
                                            },
                                            "count": 1,
                                        }
                                    },
                                ]
                            },
                            "count": 1,
                        }
                    },
                ]
            },
            "count": 1,
        }
    }
}

SETTINGS_RESPONSE = {
    "fantasy_content": {
        "league": [
            {
                "league_key": "423.l.12345",
                "name": "My FF League",
                "num_teams": "12",
                "season": "2024",
            },
            {
                "settings": {
                    "stat_modifiers": {
                        "stats": {
                            "stat": [
                                {"stat_id": "5", "value": "4"},
                                {"stat_id": "11", "value": "1"},
                            ]
                        }
                    }
                }
            },
        ]
    }
}


# A well-formed response for an account with no NFL leagues: Yahoo returns the
# games envelope with count == 0 (we requested the games sub-resource, so it is
# present even when empty). This MUST parse to [] without raising.
EMPTY_LEAGUES_RESPONSE = {
    "fantasy_content": {
        "users": {
            "0": {
                "user": [
                    {"guid": "ABCDEF"},
                    {"games": {"count": 0}},
                ]
            },
            "count": 1,
        }
    }
}


def _make_user(access_token="enc_access", refresh_token="enc_refresh"):
    user = MagicMock()
    user.yahoo_access_token = access_token
    user.yahoo_refresh_token = refresh_token
    return user


@pytest.mark.asyncio
async def test_list_user_leagues_returns_summaries(respx_mock):
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues"
    respx_mock.get(url).mock(return_value=httpx.Response(200, json=LEAGUES_RESPONSE))

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        leagues = await list_user_leagues(user, db)

    assert len(leagues) == 1
    assert leagues[0].league_key == "423.l.12345"
    assert leagues[0].name == "My FF League"
    assert leagues[0].season == 2024
    assert leagues[0].num_teams == 12


def test_parse_leagues_parses_well_formed_response():
    """Sanity: the happy path still returns the parsed summary."""
    leagues = _parse_leagues(LEAGUES_RESPONSE)
    assert [l.league_key for l in leagues] == ["423.l.12345"]


def test_parse_leagues_empty_account_returns_empty():
    """A genuinely empty account (games count == 0) returns [] WITHOUT raising —
    it must stay distinguishable from a schema-drift failure."""
    assert _parse_leagues(EMPTY_LEAGUES_RESPONSE) == []


def test_parse_leagues_raises_on_missing_key():
    """A response missing an expected key is schema drift: it must raise
    YahooLeaguesParseError, not silently return [] (issue #643)."""
    malformed = {"fantasy_content": {"users": {"0": {"user": [{"guid": "X"}]}}}}
    with pytest.raises(YahooLeaguesParseError):
        _parse_leagues(malformed)


def test_parse_leagues_raises_on_league_shape_drift():
    """A count that promises a league Yahoo then nests unexpectedly is drift —
    it must raise rather than swallow the KeyError into an empty list."""
    drifted = {
        "fantasy_content": {
            "users": {
                "0": {
                    "user": [
                        {"guid": "X"},
                        {
                            "games": {
                                "0": {
                                    "game": [
                                        {"season": "2024"},
                                        {
                                            "leagues": {
                                                # count says 1 league exists, but the
                                                # entry lacks the "league" key.
                                                "0": {"not_league": []},
                                                "count": 1,
                                            }
                                        },
                                    ]
                                },
                                "count": 1,
                            }
                        },
                    ]
                },
                "count": 1,
            }
        }
    }
    with pytest.raises(YahooLeaguesParseError):
        _parse_leagues(drifted)


def test_parse_leagues_logs_on_drift(caplog):
    """The swallowed exception is no longer silent: a warning with a traceback is
    logged before the parse error is raised."""
    import logging

    malformed = {"fantasy_content": {}}
    with caplog.at_level(logging.WARNING, logger="app.integrations.yahoo_fantasy"):
        with pytest.raises(YahooLeaguesParseError):
            _parse_leagues(malformed)
    assert any(
        "Yahoo leagues parse failed" in r.message and r.exc_info
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_list_user_leagues_raises_on_malformed_response(respx_mock):
    """End-to-end at the client boundary: a 200 with a malformed body raises
    YahooLeaguesParseError rather than returning []."""
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues"
    respx_mock.get(url).mock(
        return_value=httpx.Response(200, json={"fantasy_content": {"unexpected": True}})
    )

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        with pytest.raises(YahooLeaguesParseError):
            await list_user_leagues(user, db)


@pytest.mark.asyncio
async def test_list_user_leagues_follows_redirect(respx_mock):
    """The Yahoo client must follow redirects (httpx defaults follow_redirects
    to False); a 302 hop to a canonical URL must still resolve to league data
    rather than leaving a 3xx body for resp.json() to choke on."""
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues"
    canonical = "https://fantasysports.yahooapis.com/fantasy/v2/users/canonical/leagues"
    respx_mock.get(url).mock(return_value=httpx.Response(302, headers={"location": canonical}))
    respx_mock.get(canonical).mock(return_value=httpx.Response(200, json=LEAGUES_RESPONSE))

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        leagues = await list_user_leagues(user, db)

    assert len(leagues) == 1
    assert leagues[0].league_key == "423.l.12345"


@pytest.mark.asyncio
async def test_fetch_league_returns_data(respx_mock):
    league_key = "423.l.12345"
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(url).mock(return_value=httpx.Response(200, json=SETTINGS_RESPONSE))

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        data = await fetch_league(league_key, user, db)

    assert data.league_id == "423.l.12345"
    assert data.name == "My FF League"
    assert data.season == 2024
    assert data.league_size == 12
    assert data.raw_scoring is not None


@pytest.mark.asyncio
async def test_fetch_league_refreshes_token_on_401(respx_mock):
    league_key = "423.l.12345"
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(url).mock(
        side_effect=[
            httpx.Response(401, text="Unauthorized"),
            httpx.Response(200, json=SETTINGS_RESPONSE),
        ]
    )

    db = AsyncMock()
    user = _make_user()

    async def fake_refresh(token: str) -> str:
        return "new_access_token"

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.refresh_access_token", fake_refresh)
        data = await fetch_league(league_key, user, db)

    assert data.league_id == "423.l.12345"
    assert user.yahoo_access_token == "new_access_token"
    db.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh_status", [400, 401])
async def test_fetch_league_raises_reauth_when_refresh_token_revoked(respx_mock, refresh_status):
    """When the access token is stale (401) AND the refresh token is
    revoked/expired (Yahoo returns 400/401 on the refresh POST), the client
    surfaces YahooReauthRequired instead of leaking the raw HTTPStatusError."""
    league_key = "423.l.12345"
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(url).mock(return_value=httpx.Response(401, text="Unauthorized"))
    respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(refresh_status, text="invalid_grant")
    )

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        with pytest.raises(YahooReauthRequired):
            await fetch_league(league_key, user, db)

    # The stale access token must NOT be overwritten on a failed refresh.
    db.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh_status", [429, 500, 503])
async def test_fetch_league_reraises_transient_refresh_failure(respx_mock, refresh_status):
    """A transient failure on the refresh POST (429 rate-limit, 5xx outage) is
    NOT a revoked token — it must propagate as the raw HTTPStatusError (which the
    endpoint maps to a 502 upstream error) rather than a misleading
    YahooReauthRequired "reconnect Yahoo" prompt."""
    league_key = "423.l.12345"
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(url).mock(return_value=httpx.Response(401, text="Unauthorized"))
    respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(refresh_status, text="temporarily unavailable")
    )

    db = AsyncMock()
    user = _make_user()

    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.integrations.yahoo_fantasy.decrypt", lambda x: x)
        m.setattr("app.integrations.yahoo_fantasy.encrypt", lambda x: x)
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_league(league_key, user, db)

    # The stale access token must NOT be overwritten on a failed refresh.
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_get_yahoo_leagues_endpoint(async_client, test_db):
    from app.models import User, Profile
    from app.security.fernet import encrypt
    import uuid

    user = User(
        email="yf@example.com",
        yahoo_subject="ysub1",
        yahoo_access_token=encrypt("acc"),
        yahoo_refresh_token=encrypt("ref"),
    )
    test_db.add(user)
    await test_db.flush()

    profile = Profile(
        user_id=user.id,
        name="My Profile",
        settings_json={},
        rules_json=[],
    )
    test_db.add(profile)
    await test_db.commit()
    await test_db.refresh(profile)

    from app.auth.jwt import encode_jwt
    jwt = encode_jwt(str(user.id))

    from app.integrations.yahoo_fantasy import YahooLeagueSummary
    with pytest.MonkeyPatch().context() as m:
        async def fake_list(u, db):
            return [YahooLeagueSummary("423.l.99", "Test League", 2024, 12)]
        m.setattr("app.api.linked_league.list_yahoo_leagues", fake_list)

        resp = await async_client.get(
            f"/api/profiles/{profile.id}/link/yahoo/leagues",
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["league_key"] == "423.l.99"


@pytest.mark.asyncio
async def test_get_yahoo_leagues_malformed_returns_non_200(async_client, test_db, respx_mock):
    """A schema-drifted Yahoo response (HTTP 200 body we can't parse) must surface
    as a provider error, NOT a 200 with an empty list that reads as "no leagues"
    (issue #643)."""
    _LEAGUES_URL = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues"
    respx_mock.get(_LEAGUES_URL).mock(
        return_value=httpx.Response(200, json={"fantasy_content": {"unexpected": True}})
    )

    user, profile = await _make_yahoo_user_and_profile(test_db)
    from app.auth.jwt import encode_jwt
    jwt = encode_jwt(str(user.id))

    resp = await async_client.get(
        f"/api/profiles/{profile.id}/link/yahoo/leagues",
        cookies={"autotiers_session": jwt},
    )

    assert resp.status_code != 200
    assert resp.status_code == 502  # routed through _provider_http_error


@pytest.mark.asyncio
async def test_post_yahoo_link_endpoint(async_client, test_db):
    from app.models import User, Profile
    from app.security.fernet import encrypt
    from app.auth.jwt import encode_jwt
    from app.integrations.yahoo_fantasy import YahooLeagueData

    user = User(
        email="yf2@example.com",
        yahoo_subject="ysub2",
        yahoo_access_token=encrypt("acc"),
        yahoo_refresh_token=encrypt("ref"),
    )
    test_db.add(user)
    await test_db.flush()
    profile = Profile(user_id=user.id, name="P", settings_json={}, rules_json=[])
    test_db.add(profile)
    await test_db.commit()
    await test_db.refresh(profile)

    jwt = encode_jwt(str(user.id))

    fake_data = YahooLeagueData(
        league_id="423.l.99",
        name="Test League",
        season=2024,
        league_size=12,
        raw_scoring={"stat": [{"stat_id": "11", "value": "1"}]},
        keepers=[],
        adp_json=None,
    )

    with pytest.MonkeyPatch().context() as m:
        async def fake_fetch(league_key, u, db):
            return fake_data
        m.setattr("app.api.linked_league.fetch_yahoo_league", fake_fetch)

        resp = await async_client.post(
            f"/api/profiles/{profile.id}/link/yahoo",
            json={"league_key": "423.l.99", "season": 2024},
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["linked_league"]["provider"] == "yahoo"
    assert body["linked_league"]["league_id"] == "423.l.99"


async def _make_yahoo_connected_profile(test_db, email):
    """Create a Yahoo-connected user + profile, returning (jwt, profile)."""
    from app.models import User, Profile
    from app.security.fernet import encrypt
    from app.auth.jwt import encode_jwt

    user = User(
        email=email,
        yahoo_subject=f"ysub-{email}",
        yahoo_access_token=encrypt("acc"),
        yahoo_refresh_token=encrypt("ref"),
    )
    test_db.add(user)
    await test_db.flush()
    profile = Profile(user_id=user.id, name="P", settings_json={}, rules_json=[])
    test_db.add(profile)
    await test_db.commit()
    await test_db.refresh(profile)
    return encode_jwt(str(user.id)), profile


async def test_post_yahoo_rejects_blank_league_key(async_client, test_db):
    """A blank league_key must be rejected with a Yahoo-specific 400 before the
    provider is ever contacted — not a passthrough 502/400 provider error."""
    from app.integrations.yahoo_fantasy import YahooLeagueData

    jwt, profile = await _make_yahoo_connected_profile(test_db, "yf-blank@example.com")

    called = False

    with pytest.MonkeyPatch().context() as m:
        async def fake_fetch(league_key, u, db):
            nonlocal called
            called = True
            return YahooLeagueData(
                league_id="x", name="x", season=2026, league_size=12,
                raw_scoring={}, keepers=[], adp_json=None,
            )
        m.setattr("app.api.linked_league.fetch_yahoo_league", fake_fetch)

        resp = await async_client.post(
            f"/api/profiles/{profile.id}/link/yahoo",
            json={"league_key": "", "season": 2026},
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Yahoo league" in detail  # Yahoo-specific copy, not a generic provider error
    assert called is False  # guard fires before the provider is contacted


async def test_post_yahoo_rejects_whitespace_league_key(async_client, test_db):
    """Whitespace-only league_key is treated the same as blank (stripped)."""
    jwt, profile = await _make_yahoo_connected_profile(test_db, "yf-ws@example.com")

    resp = await async_client.post(
        f"/api/profiles/{profile.id}/link/yahoo",
        json={"league_key": "   ", "season": 2026},
        cookies={"autotiers_session": jwt},
    )

    assert resp.status_code == 400
    assert "Yahoo league" in resp.json()["detail"]


async def test_post_yahoo_rejects_season_mismatch(async_client, test_db):
    """body.season is consumed: it must match the fetched league's season, else
    a 400 is returned instead of silently persisting the fetched season."""
    from app.integrations.yahoo_fantasy import YahooLeagueData

    jwt, profile = await _make_yahoo_connected_profile(test_db, "yf-season@example.com")

    fake_data = YahooLeagueData(
        league_id="423.l.99", name="Test League", season=2024, league_size=12,
        raw_scoring={"stat": [{"stat_id": "11", "value": "1"}]},
        keepers=[], adp_json=None,
    )

    with pytest.MonkeyPatch().context() as m:
        async def fake_fetch(league_key, u, db):
            return fake_data
        m.setattr("app.api.linked_league.fetch_yahoo_league", fake_fetch)

        resp = await async_client.post(
            f"/api/profiles/{profile.id}/link/yahoo",
            json={"league_key": "423.l.99", "season": 2026},  # mismatches data.season=2024
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "2026" in detail and "2024" in detail


async def test_post_yahoo_accepts_matching_season(async_client, test_db):
    """A season that matches the fetched league links successfully."""
    from app.integrations.yahoo_fantasy import YahooLeagueData

    jwt, profile = await _make_yahoo_connected_profile(test_db, "yf-match@example.com")

    fake_data = YahooLeagueData(
        league_id="423.l.99", name="Test League", season=2024, league_size=12,
        raw_scoring={"stat": [{"stat_id": "11", "value": "1"}]},
        keepers=[], adp_json=None,
    )

    with pytest.MonkeyPatch().context() as m:
        async def fake_fetch(league_key, u, db):
            return fake_data
        m.setattr("app.api.linked_league.fetch_yahoo_league", fake_fetch)

        resp = await async_client.post(
            f"/api/profiles/{profile.id}/link/yahoo",
            json={"league_key": "423.l.99", "season": 2024},
            cookies={"autotiers_session": jwt},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["linked_league"]["league_id"] == "423.l.99"
    assert body["linked_league"]["league_metadata_json"]["season"] == 2024


# --- Refresh-token-revoked reconnect-prompt endpoint tests ---------------------
#
# These drive the real integration path (no monkeypatch of the client) with
# respx returning 401 on the Yahoo API call and 401 on the refresh POST, so a
# revoked refresh token propagates as YahooReauthRequired and each endpoint must
# translate it to a 400 "reconnect Yahoo" message — NOT a 502 "verify
# credentials". Deleting either the client's YahooReauthRequired raise or the
# endpoint's except-branch makes these fail.

_LEAGUES_URL = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues"
_REAUTH_SUBSTR = "reconnect Yahoo"


async def _make_yahoo_user_and_profile(test_db):
    from app.models import User, Profile
    from app.security.fernet import encrypt

    user = User(
        email="reauth@example.com",
        yahoo_subject="ysub-reauth",
        yahoo_access_token=encrypt("acc"),
        yahoo_refresh_token=encrypt("ref"),
    )
    test_db.add(user)
    await test_db.flush()
    profile = Profile(user_id=user.id, name="P", settings_json={}, rules_json=[])
    test_db.add(profile)
    await test_db.commit()
    await test_db.refresh(profile)
    return user, profile


@pytest.mark.asyncio
async def test_get_yahoo_leagues_reauth_returns_400(async_client, test_db, respx_mock):
    respx_mock.get(_LEAGUES_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
    respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(401, text="invalid_grant"))

    user, profile = await _make_yahoo_user_and_profile(test_db)
    from app.auth.jwt import encode_jwt
    jwt = encode_jwt(str(user.id))

    resp = await async_client.get(
        f"/api/profiles/{profile.id}/link/yahoo/leagues",
        cookies={"autotiers_session": jwt},
    )

    assert resp.status_code == 400
    assert _REAUTH_SUBSTR in resp.json()["detail"]


@pytest.mark.asyncio
async def test_post_yahoo_reauth_returns_400(async_client, test_db, respx_mock):
    league_key = "423.l.99"
    settings_url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(settings_url).mock(return_value=httpx.Response(401, text="Unauthorized"))
    respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(401, text="invalid_grant"))

    user, profile = await _make_yahoo_user_and_profile(test_db)
    from app.auth.jwt import encode_jwt
    jwt = encode_jwt(str(user.id))

    resp = await async_client.post(
        f"/api/profiles/{profile.id}/link/yahoo",
        json={"league_key": league_key, "season": 2024},
        cookies={"autotiers_session": jwt},
    )

    assert resp.status_code == 400
    assert _REAUTH_SUBSTR in resp.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_yahoo_reauth_returns_400(async_client, test_db, respx_mock):
    from app.models import LinkedLeague

    league_key = "423.l.99"
    settings_url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings"
    respx_mock.get(settings_url).mock(return_value=httpx.Response(401, text="Unauthorized"))
    respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(401, text="invalid_grant"))

    user, profile = await _make_yahoo_user_and_profile(test_db)
    ll = LinkedLeague(
        profile_id=profile.id,
        provider="yahoo",
        username_or_swid="",
        league_id=league_key,
        league_metadata_json={"name": "Test League", "season": 2024},
    )
    test_db.add(ll)
    await test_db.commit()

    from app.auth.jwt import encode_jwt
    jwt = encode_jwt(str(user.id))

    resp = await async_client.post(
        f"/api/profiles/{profile.id}/link/refresh",
        cookies={"autotiers_session": jwt},
    )

    assert resp.status_code == 400
    assert _REAUTH_SUBSTR in resp.json()["detail"]
