import pytest
import respx
from httpx import Response
from app.integrations.espn import fetch_league, EspnAuthRequired


def _espn_base(season: int, league_id: str) -> str:
    return (
        f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
        f"/segments/0/leagues/{league_id}"
    )


@pytest.mark.asyncio
async def test_fetch_public_league_returns_metadata_and_size():
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(
            return_value=Response(200, json={
                "id": 12345,
                "settings": {
                    "name": "Dynasty Champs",
                    "size": 12,
                    "scoringSettings": {"scoringItems": [
                        {"statId": 53, "points": 1.0},  # receptions
                    ]},
                },
                "teams": [
                    {"id": 1, "owners": ["O1"], "draftStrategy": {"keepers": [{"playerId": 4035687}]}},
                ],
                "players": [
                    {"id": 4035687, "fullName": "Justin Jefferson", "defaultPositionId": 4, "proTeamId": 16},
                ],
                "draftDetail": {"drafted": False, "picks": []},
            }),
        )
        league = await fetch_league("12345", 2026, swid=None, espn_s2=None)
    assert league.league_size == 12
    assert league.name == "Dynasty Champs"
    assert league.keepers and league.keepers[0]["player_name"] == "Justin Jefferson"
    assert league.adp_json is None


@pytest.mark.asyncio
async def test_fetch_private_league_sends_cookies():
    captured = {}
    def handler(request):
        captured["cookies"] = dict(request.headers).get("cookie", "")
        return Response(200, json={
            "id": 12345,
            "settings": {"name": "Private", "size": 10, "scoringSettings": {"scoringItems": []}},
            "teams": [], "players": [],
            "draftDetail": {"drafted": False, "picks": []},
        })
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(side_effect=handler)
        await fetch_league("12345", 2026, swid="{abc-123}", espn_s2="encrypted-blob")
    assert "swid={abc-123}" in captured["cookies"].lower() or "SWID=" in captured["cookies"]
    assert "espn_s2=encrypted-blob" in captured["cookies"]


@pytest.mark.asyncio
async def test_fetch_private_league_without_cookies_raises_auth_required():
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(return_value=Response(401, json={}))
        with pytest.raises(EspnAuthRequired):
            await fetch_league("12345", 2026, swid=None, espn_s2=None)


@pytest.mark.asyncio
async def test_fetch_redirect_treated_as_auth_required():
    """ESPN redirects to a login page (3xx) for private leagues. Treat that the
    same as 401/403 so the user gets the 'paste your cookies' hint."""
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(
            return_value=Response(302, headers={"location": "https://www.espn.com/login"}),
        )
        with pytest.raises(EspnAuthRequired):
            await fetch_league("12345", 2026, swid=None, espn_s2=None)


@pytest.mark.asyncio
async def test_fetch_league_returns_adp_when_draft_completed():
    with respx.mock() as router:
        router.get(_espn_base(2026, "12345")).mock(
            return_value=Response(200, json={
                "id": 12345,
                "settings": {"name": "Done", "size": 10, "scoringSettings": {"scoringItems": []}},
                "teams": [], "players": [
                    {"id": 1, "fullName": "Justin Jefferson", "defaultPositionId": 4, "proTeamId": 16},
                    {"id": 2, "fullName": "Christian McCaffrey", "defaultPositionId": 2, "proTeamId": 25},
                ],
                "draftDetail": {"drafted": True, "picks": [
                    {"overallPickNumber": 1, "playerId": 1},
                    {"overallPickNumber": 2, "playerId": 2},
                ]},
            }),
        )
        league = await fetch_league("12345", 2026, swid=None, espn_s2=None)
    assert league.adp_json == {"Justin Jefferson": 1.0, "Christian McCaffrey": 2.0}
