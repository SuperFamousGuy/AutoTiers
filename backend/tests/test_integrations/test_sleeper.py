import pytest
import respx
from httpx import Response
from app.config import settings
from app.integrations.sleeper import list_user_leagues, fetch_league


def _mock_league(router, *, players=None, drafts=None):
    """Wire the four core fetch_league endpoints for league 'L1'.

    Returns the /v1/players/nfl route so tests can assert on its call count
    and per-request timeout.
    """
    router.get("https://api.sleeper.app/v1/league/L1").mock(
        return_value=Response(200, json={
            "league_id": "L1", "name": "PPR Champs", "season": "2026",
            "total_rosters": 12,
            "scoring_settings": {"rec": 1.0, "pass_td": 4},
            "settings": {"draft_rounds": 15},
        }),
    )
    router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
        return_value=Response(200, json=[{"owner_id": "u1", "keepers": ["12345"]}]),
    )
    players_route = router.get("https://api.sleeper.app/v1/players/nfl").mock(
        return_value=Response(200, json=players if players is not None else {
            "12345": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
        }),
    )
    router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
        return_value=Response(200, json=drafts if drafts is not None else []),
    )
    return players_route


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


@pytest.mark.asyncio
async def test_fetch_league_caches_players_dict_within_ttl():
    """A second link within the TTL must not re-download the multi-MB dict (issue #560)."""
    with respx.mock() as router:
        players_route = _mock_league(router)
        first = await fetch_league("L1")
        second = await fetch_league("L1")

    assert players_route.call_count == 1
    # The cached dict still resolves keeper names on the second call.
    assert {k["player_name"] for k in first.keepers} == {"Justin Jefferson"}
    assert {k["player_name"] for k in second.keepers} == {"Justin Jefferson"}


@pytest.mark.asyncio
async def test_fetch_league_refetches_players_when_cache_disabled(monkeypatch):
    """With the TTL set to 0, caching is off and each link re-hits the endpoint."""
    monkeypatch.setattr(settings, "sleeper_players_cache_ttl_seconds", 0)
    with respx.mock() as router:
        players_route = _mock_league(router)
        await fetch_league("L1")
        await fetch_league("L1")

    assert players_route.call_count == 2


@pytest.mark.asyncio
async def test_fetch_league_gives_players_dict_its_own_larger_timeout(monkeypatch):
    """The players request uses the independent, larger timeout — not the blanket 10s."""
    monkeypatch.setattr(settings, "sleeper_players_timeout_seconds", 42.0)
    with respx.mock() as router:
        players_route = _mock_league(router)
        await fetch_league("L1")

        players_timeout = players_route.calls.last.request.extensions["timeout"]
        assert players_timeout["read"] == 42.0
        # The small league call keeps the blanket client-level 10s timeout.
        league_calls = [c for c in router.calls if c.request.url.path == "/v1/league/L1"]
        assert league_calls
        assert league_calls[0].request.extensions["timeout"]["read"] == 10.0


@pytest.mark.asyncio
async def test_list_user_leagues_follows_redirect():
    """The Sleeper client must follow redirects (httpx defaults follow_redirects
    to False); a 302 hop must be followed transparently, not left as a 3xx body
    that resp.json() can't parse."""
    canonical = "https://api.sleeper.app/v1/user/alice/canonical"
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/alice").mock(
            return_value=Response(302, headers={"location": canonical}),
        )
        router.get(canonical).mock(
            return_value=Response(200, json={"user_id": "u123", "username": "alice"}),
        )
        router.get("https://api.sleeper.app/v1/user/u123/leagues/nfl/2026").mock(
            return_value=Response(200, json=[
                {"league_id": "L1", "name": "PPR Champs", "season": "2026"},
            ]),
        )
        result = await list_user_leagues("alice", 2026)
    assert len(result) == 1
    assert result[0].id == "L1"
