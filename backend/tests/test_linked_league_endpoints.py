import json

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
    p = Profile(user_id=u.id, name="My", settings_json={}, rules_json={})
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
@pytest.mark.parametrize("username", ["", "   "])
async def test_post_sleeper_rejects_blank_username(async_client, test_db, username):
    """Blank/whitespace username → 400 and no LinkedLeague row is persisted."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    # No respx mock — a blank username must be rejected before any Sleeper call.
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/sleeper",
        json={"username": username},
    )
    assert r.status_code == 400, r.text
    assert "username" in r.json()["detail"].lower()
    # Verify at the DB level: the guard must run before the row is created/committed.
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["", "   "])
async def test_get_sleeper_leagues_rejects_blank_username(async_client, test_db, username):
    """Blank/whitespace username query param → 400 before hitting Sleeper."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    # No respx mock — a blank username must be rejected before any Sleeper call.
    r = await async_client.get(
        f"/api/profiles/{p.id}/link/sleeper/leagues",
        params={"username": username, "season": 2026},
    )
    assert r.status_code == 400, r.text
    assert "username" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pre_linked_sleeper_survives_profile_patch_and_me_refetch(async_client, test_db):
    """Regression: user reported pre-linking Sleeper, then closing the modal,
    refreshing, and seeing the link gone. Replays the exact sequence:
    link → autosave PATCH → fetch /me.
    """
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)

    # 1. Pre-link Sleeper (no league).
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/sleeper",
        json={"username": "alice"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["linked_league"]["provider"] == "sleeper"

    # Confirm the LinkedLeague row was actually persisted before any PATCH.
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(rows) == 1, "LinkedLeague row should exist after POST /sleeper"

    # 2. Autosave fires shortly after — the frontend PATCHes the profile with
    # its current settings + rules (no link-related fields, those are a
    # separate table).
    r = await async_client.patch(
        f"/api/profiles/{p.id}",
        json={"settings_json": {"scoring_format": "ppr"}, "rules_json": {}},
    )
    assert r.status_code == 200, r.text

    # 2a. The PATCH response goes straight into the frontend's profiles state
    # (via `setProfiles(profiles.map((p) => p.id === id ? updated : p))`).
    # If linked_league isn't on the response, the in-memory state loses it
    # until the next /me — exactly the symptom the user reported.
    patch_body = r.json()
    assert "linked_league" in patch_body, (
        "PATCH response missing linked_league key — the frontend will overwrite "
        "its in-memory profile and lose the link until the next /me."
    )
    assert patch_body["linked_league"] is not None, (
        "PATCH response has linked_league=null — the frontend overwrites the in-memory "
        "linked profile with this null and shows 'unlinked' until /me runs again."
    )
    assert patch_body["linked_league"]["provider"] == "sleeper"

    # 2b. Hard check at the DB level: the LinkedLeague row must still exist.
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(rows) == 1, "LinkedLeague row was deleted by the profile PATCH"

    # 3. Page refresh → user calls /me → linked_league must come back.
    me = (await async_client.get("/api/auth/me")).json()
    assert len(me["profiles"]) == 1
    ll = me["profiles"][0]["linked_league"]
    assert ll is not None, "/me should still return linked_league after PATCH"
    assert ll["provider"] == "sleeper"
    assert ll["league_id"] is None  # pre-link, no league selected


@pytest.mark.asyncio
async def test_post_espn_rejects_empty_body(async_client, test_db):
    """No league, no cookies → 400. We're not storing an empty row."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(f"/api/profiles/{p.id}/link/espn", json={})
    assert r.status_code == 400
    assert "league" in r.json()["detail"].lower() or "cookie" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_espn_rejects_swid_without_espn_s2(async_client, test_db):
    """Half-cookies alone aren't useful for authenticated requests."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/espn",
        json={"swid": "{abc-123}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_post_espn_rejects_half_cookies_even_with_league_id(async_client, test_db):
    """A league_id must not let a lone cookie past the guard: exactly one of
    swid/espn_s2 → 400, and no LinkedLeague row is created (no half-credential)."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/espn",
        json={"league_id": "12345", "season": 2026, "swid": "abc", "espn_s2": None},
    )
    assert r.status_code == 400
    assert "both" in r.json()["detail"].lower()
    from sqlalchemy import select as sql_select
    rows = (await test_db.scalars(sql_select(LinkedLeague))).all()
    assert rows == [], "no half-credential row should be persisted on the 400 path"


@pytest.mark.asyncio
async def test_post_espn_rejects_espn_s2_without_swid_with_league_id(async_client, test_db):
    """The mirror case: espn_s2 present, swid blank, league_id supplied → 400."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/espn",
        json={"league_id": "12345", "season": 2026, "swid": "   ", "espn_s2": "blob"},
    )
    assert r.status_code == 400
    assert "both" in r.json()["detail"].lower()
    from sqlalchemy import select as sql_select
    rows = (await test_db.scalars(sql_select(LinkedLeague))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_post_espn_rejects_league_id_without_season(async_client, test_db):
    """A league_id with no season can't be fetched. Rather than silently fall
    through to the pre-link branch and discard the selection, return 400 and
    persist nothing."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/espn",
        json={"league_id": "123"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "A season is required when linking an ESPN league."
    from sqlalchemy import select as sql_select
    rows = (await test_db.scalars(sql_select(LinkedLeague))).all()
    assert rows == [], "no row should be persisted on the season-required 400 path"


@pytest.mark.asyncio
async def test_post_espn_league_id_only_followup_does_not_null_existing_league(
    async_client, test_db
):
    """Regression: after a league is linked, a malformed league_id-only (no
    season) follow-up must be rejected before the existing row's league_id is
    nulled — the caller's prior selection survives."""
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
    assert r.json()["linked_league"]["league_id"] == "12345"

    # Malformed follow-up: league_id but no season.
    r2 = await async_client.post(
        f"/api/profiles/{p.id}/link/espn",
        json={"league_id": "99999"},
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] == "A season is required when linking an ESPN league."

    # The previously-linked league must be untouched.
    from sqlalchemy import select as sql_select
    rows = (await test_db.scalars(sql_select(LinkedLeague))).all()
    assert len(rows) == 1
    assert rows[0].league_id == "12345"


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
    """A non-httpx exception during connect still surfaces as a structured 502
    with user-safe copy — the raw exception type/text must NOT leak to the client."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        # respx will raise a non-httpx exception here. The secret marker text and
        # the exception class name must never appear in the client-facing body.
        router.get("https://api.sleeper.app/v1/league/L1").mock(
            side_effect=RuntimeError("super-secret-internal-detail-boom")
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/sleeper",
            json={"username": "alice", "league_id": "L1", "season": 2026},
        )
    assert r.status_code == 502
    detail = r.json()["detail"]
    # User-safe copy still names the provider so the user knows what failed.
    assert "sleeper" in detail.lower()
    # The generic branch must not echo the raw exception text or its type.
    assert "super-secret-internal-detail-boom" not in detail
    assert "RuntimeError" not in detail


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
async def test_refresh_espn_stale_ciphertext_returns_400_reconnect(async_client, test_db):
    """A stored ESPN ciphertext that no longer decrypts (e.g. after a
    SECRET_KEY rotation) must surface as a 400 reconnect prompt, not an
    uncaught 500 — the decrypt() call is guarded before any ESPN fetch, so
    no provider request is made (issue #768)."""
    from datetime import datetime, timezone
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    ll = LinkedLeague(
        profile_id=p.id, provider="espn", league_id="12345",
        username_or_swid="{swid-123}",
        credentials_encrypted="not-a-valid-fernet-token",
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "espn" in detail and "reconnect" in detail


@pytest.mark.asyncio
async def test_refresh_cbs_stale_ciphertext_returns_400_reconnect(async_client, test_db):
    """A stored CBS ciphertext that no longer decrypts must surface as a 400
    reconnect prompt, not an uncaught 500 — the decrypt() call is guarded
    before any CBS fetch (issue #768)."""
    from datetime import datetime, timezone
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    ll = LinkedLeague(
        profile_id=p.id, provider="cbs", league_id="999999",
        username_or_swid="fan@example.com",
        credentials_encrypted="not-a-valid-fernet-token",
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "cbs" in detail and "reconnect" in detail


@pytest.mark.asyncio
async def test_refresh_yahoo_stale_ciphertext_returns_400_reconnect(async_client, test_db):
    """A stored Yahoo access/refresh token that no longer decrypts must surface
    as a 400 reconnect prompt, not the generic 502 "try again later" the Yahoo
    branch would otherwise fall through to — no HTTP call is attempted and every
    retry fails identically until the user reconnects (issue #792). Parallels the
    ESPN/CBS stale-ciphertext tests above; the guard lives in
    yahoo_fantasy._with_refresh, translating InvalidCiphertext to the existing
    YahooReauthRequired reconnect branch."""
    from datetime import datetime, timezone
    u, p = await _make_user_and_profile(test_db)
    # The Yahoo refresh path reads the token off the User, so plant a
    # non-decryptable ciphertext there (not on the LinkedLeague credentials).
    u.yahoo_subject = "ysub-stale"
    u.yahoo_access_token = "not-a-valid-fernet-token"
    u.yahoo_refresh_token = "not-a-valid-fernet-token"
    await _login(async_client)
    ll = LinkedLeague(
        profile_id=p.id, provider="yahoo", league_id="423.l.99",
        username_or_swid="",
        league_metadata_json={"name": "Old", "season": 2024},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "yahoo" in detail and "reconnect" in detail


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


_CBS_AUTH_URL = "https://api.cbssports.com/general/oauth/mobile/login?response_format=json"


def _cbs_league_url(league_id: str, view: str) -> str:
    return (
        f"https://{league_id}.football.cbssports.com/api/league/{view}"
        f"?version=3.0&response_format=json&sport=football&league_id={league_id}"
    )


def _mock_cbs_league_success(router, league_id="999999", name="CBS Champs", num_teams=10):
    router.post(_CBS_AUTH_URL).mock(
        return_value=Response(200, json={"body": {"access_token": "cbs-access-token"}}),
    )
    router.get(_cbs_league_url(league_id, "details")).mock(
        return_value=Response(200, json={
            "body": {"league_details": {"name": name, "num_teams": num_teams}},
        }),
    )
    router.get(_cbs_league_url(league_id, "rules")).mock(
        return_value=Response(200, json={
            "body": {"rules": {"scoring": {"rec": {"value": "1.0"}, "passTD": {"value": "4"}}}},
        }),
    )
    router.get(_cbs_league_url(league_id, "teams")).mock(
        return_value=Response(200, json={"body": {"teams": []}}),
    )
    router.get(_cbs_league_url(league_id, "rosters")).mock(
        return_value=Response(200, json={"body": {"rosters": {"teams": []}}}),
    )
    router.get(_cbs_league_url(league_id, "transaction-list/log")).mock(
        return_value=Response(200, json={"body": {"transaction_log": []}}),
    )


@pytest.mark.asyncio
async def test_post_cbs_succeeds_and_persists_encrypted_token_not_password(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        _mock_cbs_league_success(router)
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "fan@example.com", "password": "hunter2", "league_id": "999999"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "cbs"
    assert body["linked_league"]["league_id"] == "999999"
    assert body["linked_league"]["league_metadata_json"]["name"] == "CBS Champs"
    # CBS scoring/keeper heuristics are unverified (issue #769) — every CBS link
    # carries a flag the frontend can use to prompt the user to verify scoring.
    assert body["linked_league"]["league_metadata_json"]["scoring_unconfirmed"] is True
    assert body["profile"]["settings_json"]["scoring_format"] == "ppr"
    assert body["profile"]["settings_json"]["league_size"] == 10

    # Neither the password nor the raw access token should ever appear on
    # the wire — LinkedLeagueOut omits credentials_encrypted entirely.
    assert "password" not in body["linked_league"]
    assert "credentials_encrypted" not in body["linked_league"]
    assert "access_token" not in body["linked_league"]
    assert "email" not in body["linked_league"]

    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.username_or_swid == "fan@example.com"
    # The persisted credential must be the encrypted access token, never the
    # plaintext password and never the plaintext token.
    assert row.credentials_encrypted is not None
    assert row.credentials_encrypted != "hunter2"
    assert row.credentials_encrypted != "cbs-access-token"
    from app.security.fernet import decrypt
    assert decrypt(row.credentials_encrypted) == "cbs-access-token"


@pytest.mark.asyncio
async def test_post_cbs_forwards_password_untrimmed(async_client, test_db):
    """A CBS password with leading/trailing whitespace must reach CBS auth
    exactly as typed — trimming it (issue #697) would submit a DIFFERENT
    secret than the one on file and get legitimately rejected, blaming the
    user's credentials for a bug in our own request construction."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        auth_route = router.post(_CBS_AUTH_URL).mock(
            return_value=Response(200, json={"body": {"access_token": "cbs-access-token"}}),
        )
        _mock_cbs_league_success(router)
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "  fan@example.com  ", "password": "hunter2 ", "league_id": "  999999  "},
        )
    assert r.status_code == 200, r.text

    # The password sent to CBS must be the raw value, including the trailing
    # space — not "hunter2".
    assert auth_route.called
    sent = json.loads(auth_route.calls.last.request.content)
    assert sent["password"] == "hunter2 "
    # email (the CBS user_id) is still trimmed — only the secret is preserved.
    assert sent["user_id"] == "fan@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_transaction_log,rosters_teams",
    [
        # `None` entries inside `moves` for voided/cancelled transactions.
        pytest.param([{"moves": [None]}], [], id="none-in-moves"),
        # Truthy-non-list `moves` (a JSON boolean) — `x.get(key) or []`
        # does NOT catch this since `True` is truthy, not falsy.
        pytest.param([{"moves": True}], [], id="moves-is-bool-true"),
        # Truthy-non-list `moves` (a JSON number) — same failure mode.
        pytest.param([{"moves": 5}], [], id="moves-is-int"),
        # The whole transaction_log body being a non-list.
        pytest.param(True, [], id="transaction-log-is-bool"),
        # A roster team's `players` being a truthy non-list (a JSON number).
        pytest.param([], [{"players": 7}], id="players-is-int"),
    ],
)
async def test_post_cbs_malformed_transaction_log_links_successfully_with_empty_keepers(
    async_client, test_db, malformed_transaction_log, rosters_teams,
):
    """CBS's transaction log (and roster payload) can contain malformed
    shapes — `None` entries inside `moves` for voided/cancelled
    transactions, or truthy-non-list values like a JSON boolean/number where
    a list was expected (`"moves": true`, `"players": 7`). Linking must
    succeed (200) with an empty keepers list, not 502 — a malformed entry
    must never block account linking entirely (the _extract_keepers crash
    this regresses: TypeError on iterating a non-list / AttributeError on
    None.get(), surfaced through fetch_league as a 502 via
    _provider_http_error)."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    league_id = "999999"
    with respx.mock() as router:
        router.post(_CBS_AUTH_URL).mock(
            return_value=Response(200, json={"body": {"access_token": "cbs-access-token"}}),
        )
        router.get(_cbs_league_url(league_id, "details")).mock(
            return_value=Response(200, json={
                "body": {"league_details": {"name": "CBS Champs", "num_teams": 10}},
            }),
        )
        router.get(_cbs_league_url(league_id, "rules")).mock(
            return_value=Response(200, json={"body": {"rules": {"scoring": {"rec": {"value": "1.0"}}}}}),
        )
        router.get(_cbs_league_url(league_id, "teams")).mock(
            return_value=Response(200, json={"body": {"teams": []}}),
        )
        router.get(_cbs_league_url(league_id, "rosters")).mock(
            return_value=Response(200, json={"body": {"rosters": {"teams": rosters_teams}}}),
        )
        router.get(_cbs_league_url(league_id, "transaction-list/log")).mock(
            return_value=Response(200, json={"body": {"transaction_log": malformed_transaction_log}}),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "fan@example.com", "password": "hunter2", "league_id": league_id},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "cbs"
    assert body["linked_league"]["keepers_json"] == []

    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(rows) == 1
    assert rows[0].keepers_json == []


@pytest.mark.asyncio
async def test_post_cbs_bad_credentials_returns_400_via_embedded_error_body(async_client, test_db):
    """CBS's auth quirk: bad credentials return HTTP 200 with an embedded
    errors array. AutoTiers must still surface this as a 400 with a clear
    'check both and try again' message, not a 200 success or a generic 502."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.post(_CBS_AUTH_URL).mock(
            return_value=Response(200, json={
                "body": {"errors": ["The member ID or password entered is incorrect."]},
                "statusCode": 200,
            }),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "fan@example.com", "password": "wrong", "league_id": "999999"},
        )
    assert r.status_code == 400
    assert "rejected" in r.json()["detail"].lower()

    # No row should have been created on a failed auth.
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_post_cbs_rejects_empty_body(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(f"/api/profiles/{p.id}/link/cbs", json={})
    assert r.status_code == 422  # pydantic: email/password/league_id are required


@pytest.mark.asyncio
async def test_post_cbs_rejects_whitespace_only_fields(async_client, test_db):
    """Whitespace-only input must fail the same as empty input (bug-class #2)."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/cbs",
        json={"email": "  ", "password": "  ", "league_id": "  "},
    )
    assert r.status_code == 400
    assert "email" in r.json()["detail"].lower()
    assert "password" in r.json()["detail"].lower()
    assert "league" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_cbs_invalid_league_fetch_token_returns_reconnect_message(async_client, test_db):
    """Defensive case: token rejected immediately after exchange (unlikely
    but the design calls it out explicitly) — must map to the reconnect
    message, not a generic 502."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.post(_CBS_AUTH_URL).mock(
            return_value=Response(200, json={"body": {"access_token": "tok"}}),
        )
        router.get(_cbs_league_url("999999", "details")).mock(
            return_value=Response(400, text="Failed Authentication: error - invalid access token"),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "fan@example.com", "password": "hunter2", "league_id": "999999"},
        )
    assert r.status_code == 400
    assert "reconnect" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_cbs_returns_504_on_auth_timeout(async_client, test_db):
    import httpx as httpx_module
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.post(_CBS_AUTH_URL).mock(side_effect=httpx_module.ReadTimeout("slow"))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "fan@example.com", "password": "hunter2", "league_id": "999999"},
        )
    assert r.status_code == 504
    assert "cbs" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_cbs_wrong_league_id_returns_502(async_client, test_db):
    """A league id that doesn't exist (CBS returns a generic 5xx/4xx that
    isn't the 'invalid access token' string) maps to the spec's 502 'verify
    the league id and your credentials' message, not a raw 500."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        router.post(_CBS_AUTH_URL).mock(
            return_value=Response(200, json={"body": {"access_token": "tok"}}),
        )
        router.get(_cbs_league_url("000000", "details")).mock(
            return_value=Response(404, json={"error": "league not found"}),
        )
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/cbs",
            json={"email": "fan@example.com", "password": "hunter2", "league_id": "000000"},
        )
    assert r.status_code == 502
    detail = r.json()["detail"].lower()
    assert "cbs" in detail and "404" in detail


@pytest.mark.asyncio
async def test_refresh_cbs_reuses_stored_token_without_reprompting_credentials(async_client, test_db):
    """/link/refresh must reuse the persisted encrypted token — it never asks
    for email/password again (the 'store token-only' design decision)."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    from app.security.fernet import encrypt
    ll = LinkedLeague(
        profile_id=p.id, provider="cbs", league_id="999999",
        username_or_swid="fan@example.com",
        credentials_encrypted=encrypt("stored-access-token"),
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    with respx.mock() as router:
        # No respx mock registered for the auth endpoint — if refresh tries
        # to re-authenticate, this test fails with a respx "no route" error.
        router.get(_cbs_league_url("999999", "details")).mock(
            return_value=Response(200, json={"body": {"league_details": {"name": "Refreshed", "num_teams": 12}}}),
        )
        router.get(_cbs_league_url("999999", "rules")).mock(
            return_value=Response(200, json={"body": {"rules": {"scoring": {"rec": {"value": "0.5"}, "passTD": {"value": "4"}}}}}),
        )
        router.get(_cbs_league_url("999999", "teams")).mock(return_value=Response(200, json={"body": {"teams": []}}))
        router.get(_cbs_league_url("999999", "rosters")).mock(return_value=Response(200, json={"body": {"rosters": {"teams": []}}}))
        router.get(_cbs_league_url("999999", "transaction-list/log")).mock(
            return_value=Response(200, json={"body": {"transaction_log": []}}),
        )
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")

    assert r.status_code == 200, r.text
    assert r.json()["linked_league"]["league_metadata_json"]["name"] == "Refreshed"
    # The unconfirmed-scoring flag (issue #769) must survive a refresh, so the
    # frontend hint doesn't vanish when a CBS league is re-synced.
    assert r.json()["linked_league"]["league_metadata_json"]["scoring_unconfirmed"] is True
    assert r.json()["profile"]["settings_json"]["scoring_format"] == "half_ppr"


@pytest.mark.asyncio
async def test_refresh_cbs_expired_token_returns_reconnect_message(async_client, test_db):
    """An expired/invalid stored token surfaces as the 'reconnect' message,
    not a silent failure or a generic 502 — this is the safe degradation
    path the design names for the unverified token-expiry open question."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    from app.security.fernet import encrypt
    ll = LinkedLeague(
        profile_id=p.id, provider="cbs", league_id="999999",
        username_or_swid="fan@example.com",
        credentials_encrypted=encrypt("stale-token"),
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    with respx.mock() as router:
        router.get(_cbs_league_url("999999", "details")).mock(
            return_value=Response(400, text="Failed Authentication: error - invalid access token"),
        )
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")

    assert r.status_code == 400
    assert "reconnect" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_cbs_missing_token_returns_400(async_client, test_db):
    """A CBS row with no stored credential (shouldn't normally happen, but
    defensive) must not crash trying to decrypt None."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    from datetime import datetime, timezone
    ll = LinkedLeague(
        profile_id=p.id, provider="cbs", league_id="999999",
        username_or_swid="fan@example.com",
        credentials_encrypted=None,
        league_metadata_json={"name": "Old", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()
    r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 400
    assert "reconnect" in r.json()["detail"].lower()


_NFL_STANDINGS = "https://api.fantasy.nfl.com/v2/league/standings"


def _nfl_body(name="NFL Champs", num_teams=12, league_id="55555"):
    return {
        "games": {
            "102025": {
                "leagues": {
                    league_id: {
                        "leagueId": league_id,
                        "name": name,
                        "leagueType": "private",
                        "numTeams": num_teams,
                    }
                }
            }
        }
    }


def _mock_nfl_league_success(router, **kw):
    router.get(_NFL_STANDINGS).mock(return_value=Response(200, json=_nfl_body(**kw)))


@pytest.mark.asyncio
async def test_post_nfl_links_and_persists_no_credentials(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    with respx.mock() as router:
        _mock_nfl_league_success(router, num_teams=12)
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/nfl",
            json={"league_id": "55555", "season": 2025},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked_league"]["provider"] == "nfl"
    assert body["linked_league"]["league_id"] == "55555"
    assert body["linked_league"]["league_metadata_json"] == {"name": "NFL Champs", "season": 2025}
    # league_size imported; scoring keys are NOT emitted by NFL (appKey-gated),
    # so a profile that started with empty settings has only league_size set.
    assert body["profile"]["settings_json"]["league_size"] == 12
    assert "scoring_format" not in body["profile"]["settings_json"]
    assert "qb_td_points" not in body["profile"]["settings_json"]

    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(rows) == 1
    row = rows[0]
    # NFL collects no credentials — both fields must be empty/None, like Sleeper.
    assert row.username_or_swid == ""
    assert row.credentials_encrypted is None
    assert row.keepers_json == []
    assert row.adp_json is None


@pytest.mark.asyncio
async def test_post_nfl_preserves_existing_user_scoring(async_client, test_db):
    """Because NFL contributes no scoring, _apply_settings must leave a user's
    pre-existing scoring untouched (only league_size changes)."""
    u = User(email="pre@example.com", password_hash=hash_password("password-long-enough"))
    test_db.add(u); await test_db.commit(); await test_db.refresh(u)
    p = Profile(user_id=u.id, name="My",
                settings_json={"scoring_format": "ppr", "qb_td_points": 6.0}, rules_json={})
    test_db.add(p); await test_db.commit(); await test_db.refresh(p)
    await _login(async_client, email="pre@example.com")
    with respx.mock() as router:
        _mock_nfl_league_success(router, num_teams=10)
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/nfl", json={"league_id": "55555", "season": 2025},
        )
    assert r.status_code == 200, r.text
    settings = r.json()["profile"]["settings_json"]
    # NFL contributes ONLY league_size; the user's pre-existing PPR / 6pt-TD
    # scoring must survive linking untouched (QA blocker fix — would FAIL if
    # nfl_to_settings re-emitted placeholder defaults).
    assert settings["league_size"] == 10
    assert settings["scoring_format"] == "ppr"
    assert settings["qb_td_points"] == 6.0


@pytest.mark.asyncio
async def test_post_nfl_missing_league_returns_404_from_200_errors_body(async_client, test_db):
    """NFL returns HTTP 200 with an errors array for a missing league; the
    endpoint must surface a 404 with actionable copy, not a 200 'linked'."""
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    err = {"errors": [{"messageStringId": "LEAGUE_INVALID", "message": "League does not exist."}]}
    with respx.mock() as router:
        router.get(_NFL_STANDINGS).mock(return_value=Response(200, json=err))
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/nfl", json={"league_id": "999999999", "season": 2025},
        )
    assert r.status_code == 404, r.text
    assert "couldn't find" in r.json()["detail"].lower()
    # Nothing should have been persisted.
    rows = (await test_db.scalars(select(LinkedLeague))).all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_post_nfl_rejects_blank_league_id(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/nfl", json={"league_id": "   ", "season": 2025},
    )
    assert r.status_code == 400
    assert (await test_db.scalars(select(LinkedLeague))).all() == []


@pytest.mark.asyncio
async def test_post_nfl_rejects_implausible_season(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    r = await async_client.post(
        f"/api/profiles/{p.id}/link/nfl", json={"league_id": "55555", "season": 20245},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_refresh_nfl_refetches_by_stored_season(async_client, test_db):
    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    # First link.
    with respx.mock() as router:
        _mock_nfl_league_success(router, num_teams=12)
        r = await async_client.post(
            f"/api/profiles/{p.id}/link/nfl", json={"league_id": "55555", "season": 2025},
        )
    assert r.status_code == 200, r.text
    # Now refresh — league grew to 14 teams.
    with respx.mock() as router:
        _mock_nfl_league_success(router, num_teams=14)
        r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["settings_json"]["league_size"] == 14


@pytest.mark.asyncio
async def test_refresh_cbs_pins_stored_season_across_wall_clock_rollover(async_client, test_db):
    """Acceptance criteria for issue #775: a CBS league linked with
    season=2026 keeps league_metadata_json.season == 2026 across a refresh
    made after the March wall-clock rollover, until the user relinks. CBS's
    API never returns a season, so before the fix the refresh path re-derived
    it from wall-clock and could silently flip it to 2027."""
    import app.integrations.cbs as cbs_module
    from datetime import date, datetime, timezone
    from app.security.fernet import encrypt

    u, p = await _make_user_and_profile(test_db)
    await _login(async_client)
    ll = LinkedLeague(
        profile_id=p.id, provider="cbs", league_id="999999",
        username_or_swid="fan@example.com",
        credentials_encrypted=encrypt("cbs-access-token"),
        league_metadata_json={"name": "CBS Champs", "season": 2026},
        keepers_json=[], adp_json=None,
        last_synced_at=datetime.now(timezone.utc),
    )
    test_db.add(ll)
    await test_db.commit()

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return date(2027, 9, 1)  # wall-clock would infer season 2027

    cbs_module.date = _FakeDate
    try:
        # Refresh reuses the stored access token, so the auth login endpoint
        # is never hit — don't assert it was called.
        with respx.mock(assert_all_called=False) as router:
            _mock_cbs_league_success(router)
            r = await async_client.post(f"/api/profiles/{p.id}/link/refresh")
    finally:
        cbs_module.date = date

    assert r.status_code == 200, r.text
    assert r.json()["linked_league"]["league_metadata_json"]["season"] == 2026

    await test_db.refresh(ll)
    assert ll.league_metadata_json["season"] == 2026
