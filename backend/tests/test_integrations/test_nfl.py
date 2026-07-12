import pytest
import respx
from httpx import Response
from app.integrations.nfl import (
    fetch_league,
    NflLeagueNotFound,
    NflApiError,
    _first_league,
    _has_league_error,
)


_STANDINGS_URL = "https://api.fantasy.nfl.com/v2/league/standings"


def _standings_body(league_id="1", name="My NFL League", num_teams=12, game_key="102025"):
    return {
        "games": {
            game_key: {
                "gameId": game_key,
                "season": "2025",
                "leagues": {
                    league_id: {
                        "leagueId": league_id,
                        "name": name,
                        "leagueType": "private",
                        "numTeams": num_teams,
                        "maxTeams": str(num_teams),
                        "teamIds": [str(i) for i in range(1, num_teams + 1)],
                    }
                },
            }
        }
    }


@pytest.mark.asyncio
async def test_fetch_league_returns_league_data():
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(200, json=_standings_body()))
        data = await fetch_league("1", 2025)
    assert data.league_id == "1"
    assert data.name == "My NFL League"
    assert data.season == 2025
    assert data.league_size == 12
    assert data.raw_scoring == {}
    assert data.keepers == []
    assert data.adp_json is None


@pytest.mark.asyncio
async def test_fetch_league_reads_private_league_anonymously():
    """Confirmed live: NFL returns full metadata for leagueType=private with
    no auth. Assert we don't gate on leagueType."""
    body = _standings_body(name="Private League")
    body["games"]["102025"]["leagues"]["1"]["leagueType"] = "private"
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(200, json=body))
        data = await fetch_league("1", 2025)
    assert data.name == "Private League"


@pytest.mark.asyncio
async def test_fetch_league_raises_on_embedded_errors_array_in_200():
    """NFL returns HTTP 200 with an errors array for a missing league — NOT a
    4xx. fetch_league must inspect the body, not the status code (bug-class #4)."""
    err = {"errors": [{"id": "leagueInvalid", "message": "League does not exist.",
                       "messageStringId": "LEAGUE_INVALID"}]}
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(200, json=err))
        with pytest.raises(NflLeagueNotFound):
            await fetch_league("999999999", 2025)


@pytest.mark.asyncio
async def test_fetch_league_propagates_unknown_embedded_error_as_provider_error():
    """A 200-body errors array whose id is NOT the not-found signal (e.g. a
    rate limit) must surface as NflApiError, not be misclassified as a missing
    league (which would become a misleading 404)."""
    err = {"errors": [{"id": "rateLimited", "messageStringId": "RATE_LIMITED",
                       "message": "Too many requests."}]}
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(200, json=err))
        with pytest.raises(NflApiError):
            await fetch_league("1", 2025)


@pytest.mark.asyncio
async def test_fetch_league_raises_when_no_league_in_body():
    """A 200 with neither an errors array nor a league dict is treated as
    not-found, not a fabricated empty row."""
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(200, json={"games": {}}))
        with pytest.raises(NflLeagueNotFound):
            await fetch_league("1", 2025)


@pytest.mark.asyncio
async def test_fetch_league_propagates_http_error():
    """A real 5xx (not the 200-with-errors quirk) propagates so the API layer
    maps it via _provider_http_error."""
    import httpx
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_league("1", 2025)


@pytest.mark.asyncio
async def test_fetch_league_sends_browser_user_agent():
    """NFL's edge may reject the default httpx UA; confirm we pin a browser UA
    (bug-class #4), not 'python-httpx/x.y.z'."""
    captured = {}

    def handler(request):
        captured["ua"] = request.headers.get("user-agent", "")
        return Response(200, json=_standings_body())

    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(side_effect=handler)
        await fetch_league("1", 2025)

    assert "Mozilla" in captured["ua"]
    assert "python-httpx" not in captured["ua"]


@pytest.mark.asyncio
async def test_fetch_league_falls_back_to_maxteams_then_default():
    body = _standings_body()
    del body["games"]["102025"]["leagues"]["1"]["numTeams"]
    body["games"]["102025"]["leagues"]["1"]["maxTeams"] = "10"
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(return_value=Response(200, json=body))
        data = await fetch_league("1", 2025)
    assert data.league_size == 10


def test_first_league_iterates_synthetic_gamekey():
    """The gameKey is synthetic/unknown a priori; _first_league must not
    hardcode it."""
    body = _standings_body(game_key="990999")
    assert _first_league(body)["name"] == "My NFL League"


def test_first_league_returns_empty_on_malformed_shapes():
    assert _first_league({}) == {}
    assert _first_league({"games": "nope"}) == {}
    assert _first_league({"games": {"k": {"leagues": 7}}}) == {}
    assert _first_league({"games": {"k": {"leagues": {"1": "notadict"}}}}) == {}


def test_has_league_error():
    assert _has_league_error({"errors": [{"messageStringId": "LEAGUE_INVALID"}]}) is True
    # matched case-insensitively / underscore-insensitively
    assert _has_league_error({"errors": [{"id": "leagueInvalid"}]}) is True
    assert _has_league_error({"errors": []}) is False
    assert _has_league_error({}) is False
    assert _has_league_error({"errors": "nope"}) is False
    # an unknown error id is NOT a not-found signal
    assert _has_league_error({"errors": [{"messageStringId": "RATE_LIMITED"}]}) is False


@pytest.mark.asyncio
async def test_fetch_league_follows_redirect():
    """The NFL client must follow redirects (httpx defaults follow_redirects to
    False); a 302 to a canonical standings URL must still resolve to league
    data rather than choking resp.json() on the 3xx body."""
    canonical = "https://api.fantasy.nfl.com/v2/league/standings/canonical"
    with respx.mock() as router:
        router.get(_STANDINGS_URL).mock(
            return_value=Response(302, headers={"location": canonical}),
        )
        router.get(canonical).mock(return_value=Response(200, json=_standings_body()))
        data = await fetch_league("1", 2025)
    assert data.league_id == "1"
    assert data.name == "My NFL League"
