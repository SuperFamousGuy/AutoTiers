"""Tests for the auto-enable side effect inside PUT /favorites.

When a user transitions from 0 favorites to 1+, the Favorites rule must
flip to enabled in their currently-active profile's rules_json — in the
same transaction.
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
        "initial_rules": [],
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


def _rule_state(profile: Profile, name: str) -> tuple[bool, float] | None:
    """Look up (enabled, weight) for a rule name in the profile's rules_json. None if absent."""
    for entry in profile.rules_json:
        if entry.get("name") == name:
            return entry.get("enabled", True), entry.get("weight", 1.0)
    return None


@pytest.mark.asyncio
async def test_first_favorite_add_enables_rule(async_client, test_db):
    user, profile = await _signup_and_make_active_profile(async_client, test_db)
    pre = _rule_state(profile, "Favorites")
    assert pre is None or pre[0] is False, "expected Favorites to start off"

    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    assert r.status_code == 200, r.text

    await test_db.refresh(profile)
    post = _rule_state(profile, "Favorites")
    assert post is not None, "Favorites rule should be present in rules_json after first add"
    assert post[0] is True, "Favorites rule should be enabled after first add"


@pytest.mark.asyncio
async def test_subsequent_add_does_not_re_enable_disabled_rule(async_client, test_db):
    """User may have intentionally disabled the rule after first add.
    A SUBSEQUENT add (still > 0) must not re-enable it."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    await test_db.refresh(profile)
    # User disables the rule manually.
    profile.rules_json = [
        ({"name": "Favorites", "enabled": False, "weight": 1.0}
         if entry.get("name") == "Favorites" else entry)
        for entry in profile.rules_json
    ]
    await test_db.commit()
    await test_db.refresh(profile)

    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046", "7564"], "favorite_teams": [],
    })
    await test_db.refresh(profile)
    post = _rule_state(profile, "Favorites")
    assert post is not None and post[0] is False, (
        "Favorites rule must stay disabled when user has explicitly disabled it, "
        "even if count goes 1 → 2."
    )


@pytest.mark.asyncio
async def test_transition_to_empty_does_not_disable_rule(async_client, test_db):
    """Removing the last favorite should NOT disable the rule. The rule
    silently no-ops when there are no favorites (is_favorite never True);
    leaving it enabled means a re-add Just Works without surprising the user."""
    user, profile = await _signup_and_make_active_profile(async_client, test_db)

    await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["4046"], "favorite_teams": [],
    })
    await test_db.refresh(profile)

    await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": [],
    })
    await test_db.refresh(profile)
    post = _rule_state(profile, "Favorites")
    assert post is not None, "Favorites rule should still be in rules_json"
    assert post[0] is True, "Favorites rule should remain enabled after going to empty"
