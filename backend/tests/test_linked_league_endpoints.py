import pytest
import respx
from httpx import Response
from sqlalchemy import select
from app.models import User, Profile, LinkedLeague
from app.auth.hashing import hash_password


async def _make_user_and_profile(test_db, email="u@example.com"):
    u = User(email=email, password_hash=hash_password("password-long-enough"))
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    p = Profile(user_id=u.id, name="My", settings_json={}, rules_json=[])
    test_db.add(p)
    await test_db.commit()
    await test_db.refresh(p)
    return u, p


async def _login(async_client, email="u@example.com"):
    r = await async_client.post(
        "/api/auth/login", json={"email": email, "password": "password-long-enough"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_sleeper_leagues_returns_list(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/alice").mock(
            return_value=Response(200, json={"user_id": "u1", "username": "alice"}),
        )
        router.get("https://api.sleeper.app/v1/user/u1/leagues/nfl/2026").mock(
            return_value=Response(200, json=[
                {"league_id": "L1", "name": "PPR Champs", "season": "2026"},
            ]),
        )
        r = await async_client.get(
            f"/api/profiles/{p.id}/link/sleeper/leagues?username=alice&season=2026"
        )
    assert r.status_code == 200
    body = r.json()
    assert body == [{"id": "L1", "name": "PPR Champs", "season": 2026}]


@pytest.mark.asyncio
async def test_get_sleeper_leagues_username_not_found(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/ghost").mock(
            return_value=Response(404, json={}),
        )
        r = await async_client.get(
            f"/api/profiles/{p.id}/link/sleeper/leagues?username=ghost&season=2026"
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_sleeper_writes_linked_league_and_updates_settings(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1", "name": "Champs", "season": "2026",
                "total_rosters": 12,
                "scoring_settings": {"rec": 1.0, "pass_td": 4},
                "settings": {},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={}),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[]),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/sleeper",
            json={"username": "alice", "league_id": "L1", "season": 2026},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "sleeper"
    assert body["linked_league"]["league_id"] == "L1"
    assert body["profile"]["settings_json"]["scoring_format"] == "ppr"
    assert body["profile"]["settings_json"]["league_size"] == 12

    ll = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(ll) == 1


@pytest.mark.asyncio
async def test_post_espn_public_league_succeeds(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/12345"
        )
        router.get(url__startswith=url).mock(
            return_value=Response(200, json={
                "id": 12345,
                "settings": {
                    "name": "Public", "size": 10,
                    "scoringSettings": {"scoringItems": [{"statId": 53, "points": 1.0}]},
                },
                "teams": [], "players": [],
                "draftDetail": {"drafted": False, "picks": []},
            }),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/espn",
            json={"league_id": "12345", "season": 2026},
        )
    assert r.status_code == 200, r.text
    assert r.json()["linked_league"]["provider"] == "espn"
    assert r.json()["profile"]["settings_json"]["scoring_format"] == "ppr"


@pytest.mark.asyncio
async def test_post_sleeper_pre_link_stores_username_with_no_league(async_client, test_db):
    """No league_id in the body → just store the account; don't fetch from Sleeper."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    # No respx mock — if the endpoint tries to hit Sleeper, the test will fail.
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/sleeper",
        json={"username": "alice"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "sleeper"
    assert body["linked_league"]["league_id"] is None
    assert body["linked_league"]["league_metadata_json"] is None
    assert body["linked_league"]["keepers_json"] is None
    # settings_json should NOT have been overwritten with mapped scoring.
    assert "scoring_format" not in body["profile"]["settings_json"]


@pytest.mark.asyncio
async def test_post_espn_pre_link_stores_cookies_with_no_league(async_client, test_db):
    """ESPN body with cookies but no league_id → store cookies, skip league fetch."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/espn",
        json={"swid": "{abc-123}", "espn_s2": "blob"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "espn"
    assert body["linked_league"]["league_id"] is None
    # The encrypted credential should be persisted but never echoed back.
    from sqlalchemy import select as sql_select
    rows = (await test_db.scalars(sql_select(LinkedLeague))).all()
    assert len(rows) == 1
    assert rows[0].credentials_encrypted is not None
    assert rows[0].credentials_encrypted != "blob"  # encrypted at rest


@pytest.mark.asyncio
async def test_refresh_400_when_no_league_selected(async_client, test_db):
    """Pre-linked account (no league_id) → refresh returns a clear 400."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="sleeper",
        league_id=None,
        username_or_swid="alice",
        credentials_encrypted=None,
        league_metadata_json=None,
        keepers_json=None,
        adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 400
    assert "no league" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_sleeper_leagues_502_on_network_error(async_client, test_db):
    """RequestError from Sleeper (e.g. connection refused) → 502 with provider name."""
    import httpx as httpx_module
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/user/alice").mock(
            side_effect=httpx_module.ConnectError("no route"),
        )
        r = await async_client.get(
            f"/api/profiles/{p.id}/link/sleeper/leagues?username=alice&season=2026"
        )
    assert r.status_code == 502
    assert "sleeper" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_sleeper_502_on_generic_exception(async_client, test_db):
    """A non-httpx exception during connect still surfaces as a structured 502."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        # respx will raise a non-httpx exception here.
        router.get("https://api.sleeper.app/v1/league/L1").mock(side_effect=RuntimeError("boom"))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/sleeper",
            json={"username": "alice", "league_id": "L1", "season": 2026},
        )
    assert r.status_code == 502
    assert "unexpected" in r.json()["detail"].lower() or "sleeper" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_502_on_sleeper_error(async_client, test_db):
    """Refreshing a Sleeper-linked profile when Sleeper is down → 502."""
    import httpx as httpx_module
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="sleeper", league_id="L1",
        username_or_swid="alice",
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            side_effect=httpx_module.ConnectError("down"),
        )
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_refresh_502_on_espn_error(async_client, test_db):
    """Refreshing an ESPN-linked profile when ESPN is down → 502."""
    import httpx as httpx_module
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="espn", league_id="12345",
        username_or_swid="",
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/12345"
        )
        router.get(url__startswith=url).mock(side_effect=httpx_module.ConnectError("down"))
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_post_espn_returns_502_when_espn_responds_5xx(async_client, test_db):
    """ESPN returning a 5xx should surface as 502 with a useful message (not a raw 500)."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/12345"
        )
        router.get(url__startswith=url).mock(return_value=Response(503, json={}))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/espn",
            json={"league_id": "12345", "season": 2026},
        )
    assert r.status_code == 502
    detail = r.json()["detail"].lower()
    assert "espn" in detail and "503" in detail


@pytest.mark.asyncio
async def test_post_espn_returns_504_on_timeout(async_client, test_db):
    """An httpx timeout from ESPN should map to 504, not an uncaught 500."""
    import httpx as httpx_module
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/12345"
        )
        router.get(url__startswith=url).mock(side_effect=httpx_module.ReadTimeout("slow"))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/espn",
            json={"league_id": "12345", "season": 2026},
        )
    assert r.status_code == 504
    assert "espn" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_espn_private_without_cookies_returns_400(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        url = (
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2026"
            "/segments/0/leagues/99999"
        )
        router.get(url__startswith=url).mock(return_value=Response(401, json={}))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/espn",
            json={"league_id": "99999", "season": 2026},
        )
    assert r.status_code == 400
    assert "private" in r.json()["detail"].lower() or "cookie" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_re_fetches_and_updates(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="sleeper", league_id="L1",
        username_or_swid="alice",
        league_metadata_json={"name": "Old", "season": 2025},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    with respx.mock() as router:
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            return_value=Response(200, json={
                "league_id": "L1", "name": "New", "season": "2026",
                "total_rosters": 14,
                "scoring_settings": {"rec": 0.5, "pass_td": 6},
                "settings": {},
            }),
        )
        router.get("https://api.sleeper.app/v1/league/L1/rosters").mock(
            return_value=Response(200, json=[]),
        )
        router.get("https://api.sleeper.app/v1/players/nfl").mock(
            return_value=Response(200, json={}),
        )
        router.get("https://api.sleeper.app/v1/league/L1/drafts").mock(
            return_value=Response(200, json=[]),
        )
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 200
    assert r.json()["linked_league"]["league_metadata_json"]["name"] == "New"
    assert r.json()["profile"]["settings_json"]["scoring_format"] == "half_ppr"


@pytest.mark.asyncio
async def test_delete_clears_link_keeps_profile_settings(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    p.settings_json = {"scoring_format": "ppr", "league_size": 12}
    await test_db.commit()
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="sleeper", league_id="L1",
        username_or_swid="alice",
        league_metadata_json={"name": "X", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    r = await async_client.delete(f"/api/profiles/{p.id}/link")
    assert r.status_code == 204
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert rows == []
    await test_db.refresh(p)
    assert p.settings_json["scoring_format"] == "ppr"


@pytest.mark.asyncio
async def test_cross_user_access_returns_404(async_client, test_db):
    """A user cannot link a profile that belongs to someone else."""
    u1, p1 = await _make_user_and_profile(test_db, email="alice@example.com")
    u2, p2 = await _make_user_and_profile(test_db, email="bob@example.com")
    await _login(async_client, email="alice@example.com")
    r = await async_client.delete(f"/api/profiles/{p2.id}/link")
    assert r.status_code == 404
