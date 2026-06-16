"""Tests for POST /api/feedback (in-app feedback → fixed team inbox via SES)."""
import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_anonymous_feedback_sends_to_fixed_inbox(async_client, fake_sender, monkeypatch):
    # Override the configured recipient to a non-default value so this test
    # fails if the route ever hard-codes the default "feedback@autotiers.example".
    custom_inbox = "team-inbox-override@autotiers.test"
    monkeypatch.setattr(settings, "feedback_recipient", custom_inbox)

    r = await async_client.post("/api/feedback", json={"message": "Love the app!"})
    assert r.status_code == 202
    assert r.json() == {"detail": "Thanks for the feedback!"}

    assert len(fake_sender.sent) == 1
    sent = fake_sender.sent[0]
    # Recipient comes from config, not the submitting user, not hardcoded.
    assert sent.to == custom_inbox
    assert sent.to == settings.feedback_recipient
    assert "Love the app!" in sent.text
    # Anonymous submission is labelled as such, and subject says "anonymous".
    assert "anonymous" in sent.subject.lower()
    assert "anonymous" in sent.text.lower()
    # #288: no submitter address → no Reply-To header.
    assert sent.reply_to is None


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
    # #288: Reply-To is the authenticated submitter so the team can reply directly.
    assert sent.reply_to == "alice@example.com"


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


# --- #285: category selector ---------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category,label",
    [("bug", "Bug"), ("idea", "Idea"), ("other", "Other")],
)
async def test_category_appears_in_subject_and_body(
    async_client, fake_sender, category, label
):
    r = await async_client.post(
        "/api/feedback", json={"message": "categorized", "category": category}
    )
    assert r.status_code == 202
    sent = fake_sender.sent[0]
    # Label in subject as a bracketed tag, and as a "Type:" line in both bodies.
    assert f"[{label}]" in sent.subject
    assert f"Type: {label}" in sent.text
    assert f"<strong>Type:</strong> {label}" in sent.html


@pytest.mark.asyncio
async def test_category_defaults_to_idea_when_omitted(async_client, fake_sender):
    # Backward compatibility: an old client sending no category still works and
    # is treated as "idea".
    r = await async_client.post("/api/feedback", json={"message": "no category field"})
    assert r.status_code == 202
    sent = fake_sender.sent[0]
    assert "[Idea]" in sent.subject
    assert "Type: Idea" in sent.text


@pytest.mark.asyncio
async def test_unknown_category_rejected(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback", json={"message": "bad", "category": "wishlist"}
    )
    assert r.status_code == 422
    assert fake_sender.sent == []


# --- #286: persistence + admin read endpoint ----------------------------------


@pytest.mark.asyncio
async def test_feedback_persists_row_on_submit(async_client, fake_sender, test_db):
    from sqlalchemy import select
    from app.models import Feedback

    r = await async_client.post(
        "/api/feedback", json={"message": "persist me", "category": "bug"}
    )
    assert r.status_code == 202

    rows = (await test_db.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.message == "persist me"
    assert row.category == "bug"
    assert row.user_id is None          # anonymous
    assert row.submitter_email is None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_authenticated_feedback_persists_user_and_email(async_client, fake_sender, test_db):
    from sqlalchemy import select
    from app.models import Feedback, User

    await async_client.post("/api/auth/signup", json={
        "email": "bob@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    r = await async_client.post("/api/feedback", json={"message": "from bob", "category": "idea"})
    assert r.status_code == 202

    row = (await test_db.execute(select(Feedback))).scalars().one()
    assert row.submitter_email == "bob@example.com"
    assert row.message == "from bob"
    user = (await test_db.execute(select(User).where(User.email == "bob@example.com"))).scalars().one()
    assert row.user_id == user.id


@pytest.mark.asyncio
async def test_feedback_row_persists_even_when_email_send_fails(async_client, fake_sender, monkeypatch, test_db):
    # persist-then-send: a transport failure still leaves the durable row.
    from sqlalchemy import select
    from app.models import Feedback

    async def boom(*args, **kwargs):
        raise RuntimeError("SES down")

    monkeypatch.setattr(fake_sender, "send", boom)
    r = await async_client.post("/api/feedback", json={"message": "save despite bounce"})
    assert r.status_code == 502  # caller still told the email failed

    rows = (await test_db.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    assert rows[0].message == "save despite bounce"


@pytest.mark.asyncio
async def test_admin_list_requires_api_key(async_client, fake_sender, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    # No header → 401.
    r = await async_client.get("/api/feedback")
    assert r.status_code == 401
    # Wrong header → 401.
    r = await async_client.get("/api/feedback", headers={"X-Api-Key": "nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_returns_rows_newest_first(async_client, fake_sender, monkeypatch):
    from app.config import settings

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
    # Shape includes the admin read-model fields.
    assert set(data[0].keys()) == {
        "id", "user_id", "submitter_email", "category", "message", "created_at"
    }


@pytest.mark.asyncio
async def test_admin_list_pagination(async_client, fake_sender, monkeypatch):
    from app.config import settings

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


# --- #287: screenshot attachment (SES raw-MIME inline) -------------------------

import base64 as _b64


def _png_b64(num_bytes: int = 64) -> str:
    # A minimal valid-enough PNG header + padding; content is opaque to the
    # endpoint (it only checks declared type + decoded size), so bytes suffice.
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, num_bytes - 8)
    return _b64.b64encode(data).decode()


@pytest.mark.asyncio
async def test_feedback_with_screenshot_attaches_to_email(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback",
        json={
            "message": "see attached",
            "screenshot": _png_b64(),
            "screenshot_name": "bug.png",
            "screenshot_type": "image/png",
        },
    )
    assert r.status_code == 202
    sent = fake_sender.sent[0]
    assert len(sent.attachments) == 1
    att = sent.attachments[0]
    assert att.filename == "bug.png"
    assert att.content_type == "image/png"
    assert att.content.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_feedback_without_screenshot_has_no_attachment(async_client, fake_sender):
    r = await async_client.post("/api/feedback", json={"message": "no image"})
    assert r.status_code == 202
    assert fake_sender.sent[0].attachments == []


@pytest.mark.asyncio
async def test_screenshot_disallowed_type_rejected(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback",
        json={
            "message": "bad type",
            "screenshot": _png_b64(),
            "screenshot_name": "evil.svg",
            "screenshot_type": "image/svg+xml",
        },
    )
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_screenshot_over_size_limit_rejected(async_client, fake_sender):
    # 2 MB + 1 byte of decoded data → rejected by the server gate.
    big = _b64.b64encode(b"\x89PNG" + b"\x00" * (2 * 1024 * 1024)).decode()
    r = await async_client.post(
        "/api/feedback",
        json={
            "message": "too big",
            "screenshot": big,
            "screenshot_name": "huge.png",
            "screenshot_type": "image/png",
        },
    )
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_screenshot_invalid_base64_rejected(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback",
        json={
            "message": "not base64",
            "screenshot": "!!!not base64!!!",
            "screenshot_name": "x.png",
            "screenshot_type": "image/png",
        },
    )
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_screenshot_metadata_without_data_rejected(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback",
        json={
            "message": "meta only",
            "screenshot_name": "x.png",
            "screenshot_type": "image/png",
        },
    )
    assert r.status_code == 422
    assert fake_sender.sent == []


@pytest.mark.asyncio
async def test_screenshot_filename_is_sanitized_to_basename(async_client, fake_sender):
    r = await async_client.post(
        "/api/feedback",
        json={
            "message": "path traversal name",
            "screenshot": _png_b64(),
            "screenshot_name": "../../etc/passwd.png",
            "screenshot_type": "image/png",
        },
    )
    assert r.status_code == 202
    att = fake_sender.sent[0].attachments[0]
    assert att.filename == "passwd.png"  # basename only, no path components
