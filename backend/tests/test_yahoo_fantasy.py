"""Tests for the Yahoo Fantasy API client."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from app.integrations.yahoo_fantasy import (
    list_user_leagues,
    fetch_league,
    YahooLeagueSummary,
    YahooLeagueData,
)


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
