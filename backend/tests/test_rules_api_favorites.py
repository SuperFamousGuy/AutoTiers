"""Tests for GET /api/rules and the "Favorites" rule.

Accounts were removed (v1 teardown): /generate never populates is_favorite
server-side anymore, so the "Favorites" built-in rule can never fire. It is
always excluded from the exposed rule list — there is no authenticated state
in which it would appear.
"""
import pytest


@pytest.mark.asyncio
async def test_get_rules_hides_favorites(async_client, test_db):
    r = await async_client.get("/api/rules")
    assert r.status_code == 200
    names = [rule["name"] for rule in r.json()]
    assert "Favorites" not in names, (
        "Favorites has no meaning without server-side accounts — it must never "
        "be exposed for toggling."
    )
