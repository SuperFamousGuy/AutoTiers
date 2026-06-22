from datetime import date

import pytest
import respx
from httpx import Response
from app.integrations.cbs import get_access_token, fetch_league, CbsAuthRequired, _current_season, _extract_keepers


_AUTH_URL = "https://api.cbssports.com/general/oauth/mobile/login?response_format=json"


def _league_url(league_id: str, view: str) -> str:
    return (
        f"https://{league_id}.football.cbssports.com/api/league/{view}"
        f"?version=3.0&response_format=json&sport=football&league_id={league_id}"
    )


@pytest.mark.asyncio
async def test_get_access_token_returns_token_on_success():
    with respx.mock() as router:
        router.post(_AUTH_URL).mock(
            return_value=Response(200, json={"body": {"access_token": "abc123"}}),
        )
        token = await get_access_token("user@example.com", "correct-password")
    assert token == "abc123"


@pytest.mark.asyncio
async def test_get_access_token_sends_expected_body():
    """client_id/client_secret are CBS's public mobile-app constants, not a
    secret AutoTiers configures — confirm they travel verbatim, and that the
    plaintext password is the request body, never logged or transformed."""
    captured = {}

    def handler(request):
        import json
        captured["body"] = json.loads(request.content)
        return Response(200, json={"body": {"access_token": "tok"}})

    with respx.mock() as router:
        router.post(_AUTH_URL).mock(side_effect=handler)
        await get_access_token("user@example.com", "hunter2")

    assert captured["body"] == {
        "client_id": "cbssports",
        "client_secret": "sportsallthetime",
        "user_id": "user@example.com",
        "password": "hunter2",
    }


@pytest.mark.asyncio
async def test_get_access_token_sends_mobile_user_agent():
    """CBS's API is the backend for its mobile app, not a public web API —
    like ESPN, it may reject the default httpx UA as script-like traffic.
    Confirm we send the same mobile UA the FFMWR reference client uses,
    not the httpx default ('python-httpx/x.y.z')."""
    captured = {}

    def handler(request):
        captured["ua"] = request.headers.get("user-agent")
        return Response(200, json={"body": {"access_token": "tok"}})

    with respx.mock() as router:
        router.post(_AUTH_URL).mock(side_effect=handler)
        await get_access_token("user@example.com", "hunter2")

    assert captured["ua"] == "Fantasy FB/5 CFNetwork/1410.0.3 Darwin/22.6.0"


@pytest.mark.asyncio
async def test_get_access_token_raises_on_embedded_error_with_200_status():
    """CBS's auth quirk: bad credentials return HTTP 200 with an errors array
    embedded in the body, NOT a 4xx — httpx.raise_for_status() would not catch
    this. get_access_token must inspect the body itself."""
    with respx.mock() as router:
        router.post(_AUTH_URL).mock(
            return_value=Response(
                200,
                json={
                    "body": {"errors": ["The member ID or password entered is incorrect."]},
                    "statusCode": 200,
                },
            ),
        )
        with pytest.raises(CbsAuthRequired):
            await get_access_token("user@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_get_access_token_raises_when_no_token_and_no_errors():
    """Defensive: a 200 body with neither access_token nor errors is itself
    unusable — must not silently return None as a token."""
    with respx.mock() as router:
        router.post(_AUTH_URL).mock(return_value=Response(200, json={"body": {}}))
        with pytest.raises(CbsAuthRequired):
            await get_access_token("user@example.com", "password")


@pytest.mark.asyncio
async def test_fetch_league_returns_metadata_scoring_and_size():
    league_id = "12345"
    with respx.mock() as router:
        router.get(_league_url(league_id, "details")).mock(
            return_value=Response(200, json={
                "body": {"league_details": {"name": "Dynasty Champs", "num_teams": 10}},
            }),
        )
        router.get(_league_url(league_id, "rules")).mock(
            return_value=Response(200, json={"body": {"rules": {"scoring": {"rec": {"value": "1"}}}}}),
        )
        router.get(_league_url(league_id, "teams")).mock(
            return_value=Response(200, json={"body": {"teams": []}}),
        )
        router.get(_league_url(league_id, "rosters")).mock(
            return_value=Response(200, json={"body": {"rosters": {"teams": []}}}),
        )
        router.get(_league_url(league_id, "transaction-list/log")).mock(
            return_value=Response(200, json={"body": {"transaction_log": []}}),
        )
        league = await fetch_league(league_id, "valid-token")

    assert league.name == "Dynasty Champs"
    assert league.league_size == 10
    assert league.raw_scoring == {"scoring": {"rec": {"value": "1"}}}
    assert league.keepers == []
    assert league.adp_json is None
    # CBS exposes no season field on /league/details — must fall back to the
    # wall-clock heuristic rather than persisting season=0 (the pre-fix bug;
    # season=0 made /link/refresh's "missing season metadata" guard fire on
    # every CBS profile, forever).
    assert league.season == _current_season()
    assert league.season != 0


@pytest.mark.asyncio
async def test_fetch_league_sends_authorization_header_with_raw_token():
    league_id = "12345"
    captured = {}

    def handler(request):
        captured["auth"] = request.headers.get("authorization")
        captured["ua"] = request.headers.get("user-agent")
        return Response(200, json={"body": {"league_details": {"name": "L", "num_teams": 8}}})

    with respx.mock() as router:
        router.get(_league_url(league_id, "details")).mock(side_effect=handler)
        router.get(_league_url(league_id, "rules")).mock(return_value=Response(200, json={"body": {}}))
        router.get(_league_url(league_id, "teams")).mock(return_value=Response(200, json={"body": {}}))
        router.get(_league_url(league_id, "rosters")).mock(return_value=Response(200, json={"body": {}}))
        router.get(_league_url(league_id, "transaction-list/log")).mock(
            return_value=Response(200, json={"body": {}}),
        )
        await fetch_league(league_id, "raw-access-token")

    # CBS wants the bare token, not "Bearer <token>" (matches FFMWR reference).
    assert captured["auth"] == "raw-access-token"
    # Same mobile UA as get_access_token — CBS's API may reject the httpx default.
    assert captured["ua"] == "Fantasy FB/5 CFNetwork/1410.0.3 Darwin/22.6.0"


@pytest.mark.asyncio
async def test_fetch_league_raises_on_invalid_token_400():
    league_id = "12345"
    with respx.mock() as router:
        router.get(_league_url(league_id, "details")).mock(
            return_value=Response(400, text="Failed Authentication: error - invalid access token"),
        )
        with pytest.raises(CbsAuthRequired):
            await fetch_league(league_id, "stale-token")


@pytest.mark.asyncio
async def test_fetch_league_extracts_keepers_from_transaction_log():
    league_id = "12345"
    with respx.mock() as router:
        router.get(_league_url(league_id, "details")).mock(
            return_value=Response(200, json={"body": {"league_details": {"name": "L", "num_teams": 12}}}),
        )
        router.get(_league_url(league_id, "rules")).mock(return_value=Response(200, json={"body": {"rules": {}}}))
        router.get(_league_url(league_id, "teams")).mock(return_value=Response(200, json={"body": {"teams": []}}))
        router.get(_league_url(league_id, "rosters")).mock(
            return_value=Response(200, json={
                "body": {"rosters": {"teams": [
                    {"players": [{"fullname": "Justin Jefferson", "position": "WR", "pro_team": "MIN"}]},
                ]}},
            }),
        )
        router.get(_league_url(league_id, "transaction-list/log")).mock(
            return_value=Response(200, json={
                "body": {"transaction_log": [
                    {"moves": [{"type": "keeper", "player": {"fullname": "Justin Jefferson"}}]},
                    {"moves": [{"type": "trade", "player": {"fullname": "Someone Else"}}]},
                ]},
            }),
        )
        league = await fetch_league(league_id, "valid-token")

    assert league.keepers == [{"player_name": "Justin Jefferson", "position": "WR", "team": "MIN"}]


@pytest.mark.asyncio
async def test_fetch_league_keepers_skips_moves_and_roster_entries_without_a_player_name():
    """Defensive branches: a roster player with no fullname/full_name is
    skipped when building the lookup, and a keeper move with no player name
    is skipped entirely rather than producing a keeper entry with an empty
    name."""
    league_id = "12345"
    with respx.mock() as router:
        router.get(_league_url(league_id, "details")).mock(
            return_value=Response(200, json={"body": {"league_details": {"name": "L", "num_teams": 12}}}),
        )
        router.get(_league_url(league_id, "rules")).mock(return_value=Response(200, json={"body": {"rules": {}}}))
        router.get(_league_url(league_id, "teams")).mock(return_value=Response(200, json={"body": {"teams": []}}))
        router.get(_league_url(league_id, "rosters")).mock(
            return_value=Response(200, json={
                "body": {"rosters": {"teams": [
                    # No fullname/full_name on this roster entry — must not
                    # be added to the lookup (and must not raise).
                    {"players": [{"position": "RB", "pro_team": "SF"}]},
                ]}},
            }),
        )
        router.get(_league_url(league_id, "transaction-list/log")).mock(
            return_value=Response(200, json={
                "body": {"transaction_log": [
                    # Keeper-typed move but no player name at all — must be
                    # skipped, not appended as a keeper with an empty name.
                    {"moves": [{"type": "keeper", "player": {}}]},
                ]},
            }),
        )
        league = await fetch_league(league_id, "valid-token")

    assert league.keepers == []


@pytest.mark.asyncio
async def test_fetch_league_keepers_empty_when_no_keeper_moves_present():
    """Non-keeper transactions (trade/drop/won — the only move types FFMWR's
    reference implementation actually observes) must not be misclassified."""
    league_id = "12345"
    with respx.mock() as router:
        router.get(_league_url(league_id, "details")).mock(
            return_value=Response(200, json={"body": {"league_details": {"name": "L", "num_teams": 12}}}),
        )
        router.get(_league_url(league_id, "rules")).mock(return_value=Response(200, json={"body": {"rules": {}}}))
        router.get(_league_url(league_id, "teams")).mock(return_value=Response(200, json={"body": {"teams": []}}))
        router.get(_league_url(league_id, "rosters")).mock(return_value=Response(200, json={"body": {"rosters": {"teams": []}}}))
        router.get(_league_url(league_id, "transaction-list/log")).mock(
            return_value=Response(200, json={
                "body": {"transaction_log": [
                    {"moves": [{"type": "trade", "player": {"fullname": "Someone"}}]},
                    {"moves": [{"type": "won", "player": {"fullname": "Someone Else"}}]},
                ]},
            }),
        )
        league = await fetch_league(league_id, "valid-token")

    assert league.keepers == []


def test_extract_keepers_none_in_moves_does_not_raise():
    """A voided/cancelled CBS transaction is realistically represented as
    `None` inside the moves list, not omitted — must be skipped, not crash."""
    assert _extract_keepers([{"moves": [None]}], []) == []


def test_extract_keepers_non_dict_transaction_does_not_raise():
    """A transaction-log entry that isn't itself a dict must be skipped."""
    assert _extract_keepers([None, "garbage", 42, []], []) == []


def test_extract_keepers_non_dict_move_does_not_raise():
    """A move inside a (valid) transaction's moves list that isn't a dict
    must be skipped, not passed to .get()."""
    assert _extract_keepers([{"moves": [None, "garbage", 123]}], []) == []


def test_extract_keepers_non_dict_player_does_not_raise():
    """A keeper-typed move whose 'player' value isn't a dict (e.g. a bare
    string or null) must be skipped rather than raising on player.get()."""
    assert _extract_keepers(
        [{"moves": [{"type": "keeper", "player": "not-a-dict"}]}], []
    ) == []
    assert _extract_keepers(
        [{"moves": [{"type": "keeper", "player": None}]}], []
    ) == []


def test_extract_keepers_non_dict_roster_team_does_not_raise():
    """A roster entry in rosters_raw that isn't a dict must be skipped when
    building the player lookup, not raise on team.get('players')."""
    assert _extract_keepers([], [None, "garbage", 7]) == []


def test_extract_keepers_non_dict_roster_player_does_not_raise():
    """A player inside a (valid) roster team's players list that isn't a
    dict must be skipped, not passed to .get()."""
    assert _extract_keepers([], [{"players": [None, "garbage"]}]) == []


def test_extract_keepers_skips_malformed_entries_but_keeps_valid_ones():
    """Malformed entries are skipped individually — a real keeper elsewhere
    in the same payload must still be extracted, not lost to the first bad
    entry encountered."""
    transaction_log = [
        None,
        "garbage",
        {"moves": None},
        {"moves": [None, "garbage", {"type": "keeper", "player": "oops"}]},
        {"moves": [{"type": "keeper", "player": {"fullname": "Bob Smith"}}]},
    ]
    rosters_raw = [
        None,
        {"players": [None, {"fullname": "Bob Smith", "position": "RB", "pro_team": "KC"}]},
    ]
    assert _extract_keepers(transaction_log, rosters_raw) == [
        {"player_name": "Bob Smith", "position": "RB", "team": "KC"},
    ]


def test_current_season_rolls_over_in_march():
    """Jan/Feb belong to the previous season; March onward is the current one
    — mirrors web/src/lib/season.ts's currentSeason() exactly."""
    import app.integrations.cbs as cbs_module

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return date(2027, 1, 15)

    cbs_module.date = _FakeDate
    try:
        assert cbs_module._current_season() == 2026
    finally:
        cbs_module.date = date

    class _FakeDateMarch(date):
        @classmethod
        def today(cls):
            return date(2027, 3, 1)

    cbs_module.date = _FakeDateMarch
    try:
        assert cbs_module._current_season() == 2027
    finally:
        cbs_module.date = date
