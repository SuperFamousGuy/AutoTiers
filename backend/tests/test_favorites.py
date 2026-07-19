"""Endpoint tests for GET /favorites and PUT /favorites — CRUD layer only.

Auto-enable-rule-on-first-add behavior is covered separately in
test_favorites_auto_enable.py.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player
from app.models.user_favorites import UserFavorites
from app.schemas.favorites import (
    _MAX_PLAYER_IDS,
    _MAX_PLAYER_ID_LEN,
    _MAX_TEAMS,
    _MAX_TEAM_LEN,
)


async def _signup_and_login(async_client: AsyncClient, email: str = "fav@example.com") -> None:
    """Helper: signup + login via cookie. async_client persists the auth
    cookie via its cookie jar."""
    await async_client.post("/api/auth/signup", json={
        "email": email, "password": "password-long-enough",
    })


async def _seed_players(test_db: AsyncSession, *player_ids: str) -> None:
    """Seed real Player rows so favorite_player_ids referencing them validate.

    PUT /favorites now rejects (422) any favorite player ID absent from the
    Player table, so CRUD tests must seed the IDs they expect to persist.
    """
    for pid in player_ids:
        test_db.add(Player(id=pid, name=f"Player {pid}", position="WR", team="KC"))
    await test_db.commit()


@pytest.mark.asyncio
async def test_get_favorites_returns_empty_for_new_user(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.get("/api/favorites")
    assert r.status_code == 200
    body = r.json()
    assert body == {"favorite_player_ids": [], "favorite_teams": []}


@pytest.mark.asyncio
async def test_get_favorites_requires_auth(async_client: AsyncClient):
    r = await async_client.get("/api/favorites")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_put_favorites_persists(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    await _seed_players(test_db, "4046", "7564")
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    }
    r = await async_client.get("/api/favorites")
    assert r.json() == {
        "favorite_player_ids": ["4046", "7564"],
        "favorite_teams": ["KC", "BUF"],
    }


@pytest.mark.asyncio
async def test_put_favorites_replaces_existing(async_client: AsyncClient, test_db):
    """Subsequent PUT fully replaces — not a merge."""
    await _signup_and_login(async_client)
    await _seed_players(test_db, "4046", "9999")
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": ["KC"],
    })
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["9999"], "favorite_teams": ["BUF"],
    })
    assert r.status_code == 200
    assert r.json() == {"favorite_player_ids": ["9999"], "favorite_teams": ["BUF"]}


@pytest.mark.asyncio
async def test_put_favorites_rejects_over_player_cap(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    too_many = [str(i) for i in range(21)]
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": too_many, "favorite_teams": [],
    })
    assert r.status_code == 409
    assert "20" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_over_team_cap(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    too_many = ["KC", "BUF", "NYJ", "PHI", "DAL"]  # 5 teams
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": too_many,
    })
    assert r.status_code == 409
    assert "4" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_unknown_team(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["XYZ"],
    })
    assert r.status_code == 422
    assert "XYZ" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_unknown_player_id(async_client: AsyncClient, test_db):
    """An ID absent from the Player table is rejected (422) naming the bad ID,
    mirroring the unknown-team guard — not persisted as an arbitrary string."""
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["nope-not-a-player"], "favorite_teams": [],
    })
    assert r.status_code == 422, r.text
    assert "nope-not-a-player" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_rejects_partially_unknown_player_ids(async_client: AsyncClient, test_db):
    """A mix of valid and invalid IDs is rejected wholesale (422), naming only
    the unknown one; the valid ID is not silently persisted."""
    await _signup_and_login(async_client)
    await _seed_players(test_db, "4046")
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "bogus"], "favorite_teams": [],
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "bogus" in detail
    assert "4046" not in detail
    # Nothing persisted: the row must not have been created.
    r = await async_client.get("/api/favorites")
    assert r.json() == {"favorite_player_ids": [], "favorite_teams": []}
    # Assert at the DB layer directly — the GET response above is identical
    # whether the row is absent or present-but-empty, so prove no row exists.
    rows = (await test_db.execute(select(UserFavorites))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_put_favorites_allows_edit_when_a_stored_id_went_stale(
    async_client: AsyncClient, test_db
):
    """Regression for #809: a full-replace PUT re-sends the whole stored list on
    every edit. Once a previously-favorited player's Player row disappears (e.g.
    Sleeper hard-deletes a free agent), re-validating the entire list would 422
    and brick every future add/toggle. An already-stored stale ID must degrade
    gracefully — kept, not rejected — so an unrelated add still succeeds."""
    await _signup_and_login(async_client)
    await _seed_players(test_db, "stale-1", "4046")
    # Persist the soon-to-be-stale id while its Player row still exists.
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["stale-1"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text
    # The player is hard-deleted out from under the stored favorite.
    await test_db.execute(delete(Player).where(Player.id == "stale-1"))
    await test_db.commit()
    # Adding a DIFFERENT, valid player must still succeed and keep the stale id.
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["stale-1", "4046"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text
    assert r.json()["favorite_player_ids"] == ["stale-1", "4046"]


@pytest.mark.asyncio
async def test_put_favorites_still_rejects_newly_added_unknown_id_with_stale_stored(
    async_client: AsyncClient, test_db
):
    """The stale-ID grace applies ONLY to already-stored IDs. A brand-new
    unknown ID in the same request is still rejected (422), naming only the new
    one — so typos are caught even when the stored list already has a stale id."""
    await _signup_and_login(async_client)
    await _seed_players(test_db, "stale-1")
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["stale-1"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text
    await test_db.execute(delete(Player).where(Player.id == "stale-1"))
    await test_db.commit()
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["stale-1", "brand-new-bogus"], "favorite_teams": [],
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "brand-new-bogus" in detail
    assert "stale-1" not in detail


@pytest.mark.asyncio
async def test_put_favorites_rejects_whitespace_player_id(async_client: AsyncClient, test_db):
    """Class 2 guard: whitespace-only strings pass min_length but mean nothing."""
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["   "], "favorite_teams": [],
    })
    assert r.status_code == 422
    assert "blank" in r.json()["detail"].lower() or "empty" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_player_list(async_client: AsyncClient, test_db):
    """A list far above the cap is rejected at the schema boundary (422),
    before the dedup/blank-scan loop runs — not the domain-specific 409."""
    await _signup_and_login(async_client)
    # One entry over the schema bound hits the same len(...) > _MAX_PLAYER_IDS
    # branch without allocating a giant list.
    huge = [str(i) for i in range(_MAX_PLAYER_IDS + 1)]
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": huge, "favorite_teams": [],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_team_list(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    huge = ["KC"] * (_MAX_TEAMS + 1)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": huge,
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_player_id_string(async_client: AsyncClient, test_db):
    """A single over-length player-id string is rejected at validation (422), not 200."""
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["A" * (_MAX_PLAYER_ID_LEN + 1)], "favorite_teams": [],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_rejects_oversized_team_string(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["A" * (_MAX_TEAM_LEN + 1)],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_put_favorites_modestly_over_cap_still_returns_domain_409(async_client: AsyncClient, test_db):
    """A request only modestly over _PLAYER_CAP passes the schema bound and
    still reaches the domain-specific 409 with its 'too many' copy."""
    await _signup_and_login(async_client)
    modestly_over = [str(i) for i in range(25)]  # over the 20 cap, under the 200 schema bound
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": modestly_over, "favorite_teams": [],
    })
    assert r.status_code == 409, r.text
    assert "20" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_favorites_deduplicates(async_client: AsyncClient, test_db):
    await _signup_and_login(async_client)
    await _seed_players(test_db, "4046", "7564")
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "4046", "7564"],
        "favorite_teams": ["KC", "KC"],
    })
    assert r.status_code == 200
    assert r.json() == {"favorite_player_ids": ["4046", "7564"], "favorite_teams": ["KC"]}


@pytest.mark.asyncio
async def test_put_favorites_requires_auth(async_client: AsyncClient):
    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 401
