"""Tests for POST /api/feedback (in-app feedback, anonymous persist-only).

Accounts and SES email were removed (v1 teardown): feedback is always
anonymous, rate-limited by client IP only, and the only side effect is a
persisted row. Admins read it via the existing X-Api-Key-gated GET route.
"""
import pytest
from starlette.requests import Request as _StarletteRequest

from app.api.feedback import _client_ip
from app.auth.rate_limit import feedback_rate_limiter
from app.config import settings


@pytest.mark.asyncio
async def test_feedback_persists_row_on_submit(async_client, test_db):
    from sqlalchemy import select
    from app.models import Feedback

    r = await async_client.post(
        "/api/feedback", json={"message": "persist me", "category": "bug"}
    )
    assert r.status_code == 202
    assert r.json() == {"detail": "Thanks for the feedback!"}

    rows = (await test_db.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.message == "persist me"
    assert row.category == "bug"
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_empty_message_rejected(async_client, test_db):
    r = await async_client.post("/api/feedback", json={"message": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_whitespace_only_message_rejected(async_client, test_db):
    r = await async_client.post("/api/feedback", json={"message": "   \n\t  "})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_oversize_message_rejected(async_client, test_db):
    r = await async_client.post("/api/feedback", json={"message": "x" * 4001})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_message_is_trimmed_before_persist(async_client, test_db):
    from sqlalchemy import select
    from app.models import Feedback

    r = await async_client.post("/api/feedback", json={"message": "  padded  "})
    assert r.status_code == 202
    row = (await test_db.execute(select(Feedback))).scalars().one()
    assert row.message == "padded"


@pytest.mark.asyncio
async def test_rate_limited_after_burst(async_client, test_db):
    feedback_rate_limiter._attempts.clear()
    # Limit is 5 per window; the 6th from the same key is blocked.
    for _ in range(5):
        ok = await async_client.post("/api/feedback", json={"message": "spam"})
        assert ok.status_code == 202
    blocked = await async_client.post("/api/feedback", json={"message": "spam"})
    assert blocked.status_code == 429
    feedback_rate_limiter._attempts.clear()


# --- #285: category selector ---------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["bug", "idea", "other"])
async def test_category_persists(async_client, test_db, category):
    from sqlalchemy import select
    from app.models import Feedback

    r = await async_client.post(
        "/api/feedback", json={"message": "categorized", "category": category}
    )
    assert r.status_code == 202
    row = (await test_db.execute(select(Feedback))).scalars().one()
    assert row.category == category


@pytest.mark.asyncio
async def test_category_defaults_to_idea_when_omitted(async_client, test_db):
    # Backward compatibility: an old client sending no category still works and
    # is treated as "idea".
    from sqlalchemy import select
    from app.models import Feedback

    r = await async_client.post("/api/feedback", json={"message": "no category field"})
    assert r.status_code == 202
    row = (await test_db.execute(select(Feedback))).scalars().one()
    assert row.category == "idea"


@pytest.mark.asyncio
async def test_unknown_category_rejected(async_client, test_db):
    r = await async_client.post(
        "/api/feedback", json={"message": "bad", "category": "wishlist"}
    )
    assert r.status_code == 422


# --- #286: persistence + admin read endpoint ----------------------------------


@pytest.mark.asyncio
async def test_admin_list_requires_api_key(async_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    # No header → 401.
    r = await async_client.get("/api/feedback")
    assert r.status_code == 401
    # Wrong header → 401.
    r = await async_client.get("/api/feedback", headers={"X-Api-Key": "nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_returns_rows_newest_first(async_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    await async_client.post("/api/feedback", json={"message": "first", "category": "bug"})
    await async_client.post("/api/feedback", json={"message": "second", "category": "other"})

    r = await async_client.get("/api/feedback", headers={"X-Api-Key": "s3cret"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # Newest first.
    assert data[0]["message"] == "second"
    assert data[0]["category"] == "other"
    assert data[1]["message"] == "first"
    # Shape includes the admin read-model fields — no user_id/submitter_email
    # anymore (accounts were removed).
    assert set(data[0].keys()) == {"id", "category", "message", "created_at"}


@pytest.mark.asyncio
async def test_admin_list_pagination(async_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    for i in range(3):
        await async_client.post("/api/feedback", json={"message": f"m{i}"})

    r = await async_client.get(
        "/api/feedback?limit=1&offset=0", headers={"X-Api-Key": "s3cret"}
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    r2 = await async_client.get(
        "/api/feedback?limit=1&offset=1", headers={"X-Api-Key": "s3cret"}
    )
    assert r2.json()[0]["message"] != r.json()[0]["message"]


# --- #519: right-most X-Forwarded-For so clients can't forge their rate key ----


def _make_request(xff: str | None, client_host: str | None = "10.0.0.1") -> _StarletteRequest:
    """Build a minimal Starlette Request with an optional XFF header + peer."""
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/feedback",
        "headers": headers,
        "client": (client_host, 12345) if client_host is not None else None,
    }
    return _StarletteRequest(scope)


def test_client_ip_takes_rightmost_entry_for_single_alb_hop(monkeypatch):
    # Default one trusted hop: ALB appends the real peer to the RIGHT, so the
    # right-most entry is the real client, not the client-supplied left entry.
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    req = _make_request("1.2.3.4, 203.0.113.9")
    assert _client_ip(req) == "203.0.113.9"


def test_client_ip_forged_xff_maps_to_same_real_client(monkeypatch):
    # Acceptance criterion: two requests from the same real client that forge
    # DIFFERENT left-most XFF values must resolve to the same key.
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    a = _client_ip(_make_request("1.2.3.4, 203.0.113.9"))
    b = _client_ip(_make_request("9.9.9.9, 203.0.113.9"))
    c = _client_ip(_make_request("evil, spoof, chain, 203.0.113.9"))
    assert a == b == c == "203.0.113.9"


def test_client_ip_two_trusted_hops(monkeypatch):
    # With two trusted proxies the chain is `client, real, proxy1`; the entry
    # two-from-the-right is the real client.
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    req = _make_request("1.2.3.4, 203.0.113.9, 10.0.0.7")
    assert _client_ip(req) == "203.0.113.9"


def test_client_ip_chain_shorter_than_hop_count_falls_back_to_leftmost(monkeypatch):
    # A chain shorter than the trusted-hop count (misconfig or missing hop)
    # yields the left-most entry rather than raising / wrapping negative.
    monkeypatch.setattr(settings, "trusted_proxy_count", 3)
    req = _make_request("203.0.113.9")
    assert _client_ip(req) == "203.0.113.9"


def test_client_ip_single_entry_direct_client(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    req = _make_request("203.0.113.9")
    assert _client_ip(req) == "203.0.113.9"


def test_client_ip_zero_trusted_hops_ignores_xff(monkeypatch):
    # No trusted proxy → XFF is fully untrusted; use the socket peer only.
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    req = _make_request("1.2.3.4, 203.0.113.9", client_host="10.0.0.1")
    assert _client_ip(req) == "10.0.0.1"


def test_client_ip_no_xff_uses_socket_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    req = _make_request(None, client_host="198.51.100.5")
    assert _client_ip(req) == "198.51.100.5"


def test_client_ip_no_xff_no_peer_is_unknown(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    req = _make_request(None, client_host=None)
    assert _client_ip(req) == "unknown"


def test_client_ip_ignores_empty_and_whitespace_entries(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    # Trailing comma / whitespace must not become the (empty) key.
    req = _make_request(" 1.2.3.4 ,  203.0.113.9 , ")
    assert _client_ip(req) == "203.0.113.9"


@pytest.mark.asyncio
async def test_forged_xff_cannot_rotate_rate_limit_bucket(async_client, monkeypatch):
    # End-to-end acceptance: an attacker rotating the left-most (forged) XFF on
    # every request, while the ALB appends the same real client IP, stays in ONE
    # bucket and still hits 429 after the limit.
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    feedback_rate_limiter._attempts.clear()
    real_client = "203.0.113.42"
    for i in range(5):
        r = await async_client.post(
            "/api/feedback",
            json={"message": "spam"},
            headers={"X-Forwarded-For": f"10.0.0.{i}, {real_client}"},
        )
        assert r.status_code == 202, f"request {i} unexpectedly blocked"
    blocked = await async_client.post(
        "/api/feedback",
        json={"message": "spam"},
        headers={"X-Forwarded-For": f"9.9.9.9, {real_client}"},
    )
    assert blocked.status_code == 429
    feedback_rate_limiter._attempts.clear()
