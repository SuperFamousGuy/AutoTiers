import pytest
import respx
from httpx import Response
from app.integrations.sleeper import list_user_leagues, fetch_league


@pytest.mark.asyncio
async def test_list_user_leagues_resolves_username_to_leagues():
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/alice").mock(
            return_value=Response(200, json={"user_id": "u123", "username": "alice"}),
        )
        router.get("https://api.sleeper.app/v1/user/u123/leagues/nfl/2026").mock(
            return_value=Response(200, json=[
                {"league_id": "L1", "name": "PPR Champs", "season": "2026"},
                {"league_id": "L2", "name": "Standard 10", "season": "2026"},
            ]),
        )
        result = await list_user_leagues("alice", 2026)
    assert len(result) == 2
    assert result[0].id == "L1"
    assert result[0].name == "PPR Champs"
    assert result[0].season == 2026


@pytest.mark.asyncio
async def test_list_user_leagues_404_when_username_not_found():
    from app.integrations.sleeper import SleeperUserNotFound
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/ghost").mock(
            return_value=Response(404, json={}),
        )
        with pytest.raises(SleeperUserNotFound):
            await list_user_leagues("ghost", 2026)


@pytest.mark.asyncio
async def test_fetch_league_returns_settings_size_and_keepers():
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1",
                "name": "PPR Champs",
                "season": "2026",
                "total_rosters": 12,
                "scoring_settings": {"rec": 1.0, "pass_td": 4, "rush_yd": 0.1, "rec_yd": 0.1},
                "settings": {"draft_rounds": 15},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[
                {"owner_id": "u1", "keepers": ["12345", "67890"]},
                {"owner_id": "u2", "keepers": None},
            ]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={
                "12345": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
                "67890": {"full_name": "Christian McCaffrey", "position": "RB", "team": "SF"},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[]),
        )
        league = await fetch_league("L1")
    assert league.league_size == 12
    assert league.name == "PPR Champs"
    assert len(league.keepers) == 2
    assert {k["player_name"] for k in league.keepers} == {"Justin Jefferson", "Christian McCaffrey"}
    assert league.adp_json is None


@pytest.mark.asyncio
async def test_fetch_league_returns_adp_when_draft_data_exists():
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1", "name": "Champs", "season": "2026",
                "total_rosters": 10,
                "scoring_settings": {"rec": 0.5, "pass_td": 4},
                "settings": {"draft_rounds": 16},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={
                "p1": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
                "p2": {"full_name": "Christian McCaffrey", "position": "RB", "team": "SF"},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[{"draft_id": "D1", "status": "complete"}]),
        )
        router.get("https://api.sleeper.app/v1/draft/D1/picks").mock(
            return_value=Response(200, json=[
                {"pick_no": 1, "player_id": "p1"},
                {"pick_no": 2, "player_id": "p2"},
            ]),
        )
        league = await fetch_league("L1")
    assert league.adp_json == {"Justin Jefferson": 1.0, "Christian McCaffrey": 2.0}
