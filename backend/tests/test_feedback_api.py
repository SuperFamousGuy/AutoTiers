"""Tests for POST /api/feedback (in-app feedback → fixed team inbox via SES)."""
import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_anonymous_feedback_sends_to_fixed_inbox(async_client, fake_sender):
    r = await async_client.post("/api/feedback", json={"message": "Love the app!"})
    assert r.status_code == 202
    assert r.json() == {"detail": "Thanks for the feedback!"}

    assert len(fake_sender.sent) == 1
    sent = fake_sender.sent[0]
    # Recipient comes from config, not the submitting user, not hardcoded.
    assert sent.to == settings.feedback_recipient
    assert "Love the app!" in sent.text
    # Anonymous submission is labelled as such, and subject says "anonymous".
    assert "anonymous" in sent.subject.lower()
    assert "anonymous" in sent.text.lower()


@pytest.mark.asyncio
async def test_authenticated_feedback_attaches_user_email(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()  # drop the signup verification email

    r = await async_client.post("/api/feedback", json={"message": "Found a bug in tiers"})
    assert r.status_code == 202

    assert len(fake_sender.sent) == 1
    sent = fake_sender.sent[0]
    assert sent.to == settings.feedback_recipient
    # Submitter email attached server-side for reply context.
    assert "alice@example.com" in sent.subject
    assert "alice@example.com" in sent.text
    assert "Found a bug in tiers" in sent.text


@pytest.mark.asyncio
async def test_feedback_email_never_taken_from_request_body(async_client, fake_sender):
    # An attacker-supplied "email" field in the body must be ignored entirely.
    r = await async_client.post(
        "/api/feedback",
        json={"message": "spoof attempt", "email": "attacker@evil.test"},
    )
    assert r.status_code == 202
    sent = fake_sender.sent[0]
    assert "attacker@evil.test" not in sent.text
    assert "attacker@evil.test" not in sent.subject


@pytest.mark.asyncio
async def test_empty_message_rejected(async_client, fake_sender):
    r = await async_client.post("/api/feedback", json={"message": ""})
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_whitespace_only_message_rejected(async_client, fake_sender):
    r = await async_client.post("/api/feedback", json={"message": "   \n\t  "})
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_oversize_message_rejected(async_client, fake_sender):
    r = await async_client.post("/api/feedback", json={"message": "x" * 4001})
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_message_is_trimmed_before_send(async_client, fake_sender):
    r = await async_client.post("/api/feedback", json={"message": "  padded  "})
    assert r.status_code == 202
    sent = fake_sender.sent[0]
    assert "padded" in sent.text
    # The verbatim message block should be the trimmed value.
    assert "  padded  " not in sent.text


@pytest.mark.asyncio
async def test_html_in_message_is_escaped_in_html_body(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback",
        json={"message": "<script>alert(1)</script>"},
    )
    assert r.status_code == 202
    sent = fake_sender.sent[0]
    # HTML body must escape; raw tag must not appear unescaped.
    assert "<script>" not in sent.html
    assert "&lt;script&gt;" in sent.html


@pytest.mark.asyncio
async def test_rate_limited_after_burst(async_client, fake_sender):
    from app.auth.rate_limit import feedback_rate_limiter

    feedback_rate_limiter._attempts.clear()
    # Limit is 5 per window; the 6th from the same key is blocked.
    for _ in range(5):
        ok = await async_client.post("/api/feedback", json={"message": "spam"})
        assert ok.status_code == 202
    blocked = await async_client.post("/api/feedback", json={"message": "spam"})
    assert blocked.status_code == 429
    feedback_rate_limiter._attempts.clear()


@pytest.mark.asyncio
async def test_transport_failure_returns_502(async_client, fake_sender, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("SES down")

    monkeypatch.setattr(fake_sender, "send", boom)
    r = await async_client.post("/api/feedback", json={"message": "will fail"})
    assert r.status_code == 502
    assert "try again" in r.json()["detail"].lower()
