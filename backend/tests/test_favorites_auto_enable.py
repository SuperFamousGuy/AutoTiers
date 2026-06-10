"""Tests verifying that PUT /favorites does NOT corrupt rules_json.

The old auto-enable side effect (injecting a Favorites entry into a flat list)
has been removed. rules_json is now a dict keyed by position. These tests
confirm the put_favorites endpoint leaves rules_json intact regardless of
how many favorites the user adds or removes.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Profile


async def _signup_and_make_active_profile(async_client, test_db: AsyncSession) -> tuple[User, Profile]:
    """Signs up via the public API + activates a profile. Returns (user, profile)."""
    await async_client.post("/api/auth/signup", json={
        "email": "auto@example.com",
        "password": "password-long-enough",
        "initial_settings": {"scoring": "half_ppr"},
        "initial_rules": {},
    })
    user = (await test_db.scalars(
        select(User).where(User.email == "auto@example.com")
    )).one()
    profile = (await test_db.scalars(
        select(Profile).where(Profile.user_id == user.id)
    )).first()
    assert profile is not None, "signup should have created a default profile"
    user.last_active_profile_id = profile.id
    await test_db.commit()
    return user, profile


@pytest.mark.asyncio
async def test_first_favorite_does_not_corrupt_rules_json(async_client, test_db):
    """Adding a first favorite must leave rules_json as a valid dict (not a list)."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    # Capture dict shape before the favorite is added.
    initial_rules = dict(profile.rules_json)

    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text

    await test_db.refresh(profile)
    # rules_json must still be a dict — not a list, not a mangled format.
    assert isinstance(profile.rules_json, dict), (
        f"rules_json should remain a dict after first favorite add; got {type(profile.rules_json)}"
    )
    # Dict content must be unchanged.
    assert profile.rules_json == initial_rules, (
        "rules_json should not be mutated by adding a favorite"
    )


@pytest.mark.asyncio
async def test_multiple_favorites_do_not_corrupt_rules_json(async_client, test_db):
    """rules_json remains a valid dict after multiple favorites are added."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    initial_rules = dict(profile.rules_json)

    # Add first favorite.
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    # Add a second favorite (still > 0, transitions from 1 → 2).
    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "7564"], "favorite_teams": [],
    })

    await test_db.refresh(profile)
    assert isinstance(profile.rules_json, dict), (
        f"rules_json should remain a dict after multiple favorite adds; got {type(profile.rules_json)}"
    )
    assert profile.rules_json == initial_rules, (
        "rules_json should not be mutated by adding multiple favorites"
    )


@pytest.mark.asyncio
async def test_no_duplicate_favorites_entries_after_add(async_client, test_db):
    """No duplicate Favorites entries appear anywhere in rules_json after adding a favorite."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })

    await test_db.refresh(profile)
    assert isinstance(profile.rules_json, dict), (
        f"rules_json should remain a dict; got {type(profile.rules_json)}"
    )
    for position, rule_list in profile.rules_json.items():
        names = [r.get("name") for r in rule_list if isinstance(r, dict)]
        assert names.count("Favorites") <= 1, (
            f"Duplicate 'Favorites' entry found under position '{position}' in rules_json"
        )


@pytest.mark.asyncio
async def test_add_favorite_preserves_existing_position_overrides(async_client, test_db):
    """Adding a first favorite with a non-empty rules_json dict leaves the dict unchanged."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    # Pre-set a specific override to confirm it survives the favorite add.
    existing_rules = {"RB": [{"name": "RB Committee Penalty", "enabled": False, "weight": 1.0}]}
    profile.rules_json = existing_rules
    await test_db.commit()
    await test_db.refresh(profile)

    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text

    await test_db.refresh(profile)
    assert profile.rules_json == existing_rules, (
        f"rules_json should be unchanged after adding a favorite; got {profile.rules_json!r}"
    )
