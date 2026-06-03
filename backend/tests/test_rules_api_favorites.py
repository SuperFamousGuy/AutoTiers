"""Tests for the auth-aware GET /rules behavior introduced for Favorites.

Anonymous users must NOT see the Favorites rule. Authenticated users must.
"""
import pytest


@pytest.mark.asyncio
async def test_get_rules_anon_hides_favorites(async_client, test_db):
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    names = [rule["name"] for rule in r.json()]
    assert "Favorites" not in names, (
        "Anonymous users must not see the Favorites rule — it has no meaning without an account."
    )


@pytest.mark.asyncio
async def test_get_rules_authed_shows_favorites(async_client, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "ruletest@example.com", "password": "password-long-enough",
    })
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    names = [rule["name"] for rule in r.json()]
    assert "Favorites" in names


@pytest.mark.asyncio
async def test_get_rules_favorites_categorized_personal(async_client, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "categorize@example.com", "password": "password-long-enough",
    })
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    fav = next(rule for rule in r.json() if rule["name"] == "Favorites")
    assert fav["category"] == "Personal"
