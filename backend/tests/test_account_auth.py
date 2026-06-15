"""Tests for Slices 1-5 of the account-auth-modernization feature.

Covers:
- Slice 1: New User fields (email_verified, password_changed_at) + AuthToken model
- Slice 2: FakeSender, email templates
- Slice 3: POST /auth/password/forgot, POST /auth/password/reset
- Slice 4: POST /auth/email/resend-verification, GET /auth/email/verify, signup sends verification
- Slice 5: POST /auth/password/change, POST /auth/password/set
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import User
from app.models.auth_token import AuthToken
from app.schemas.auth import UserOut


# ---------------------------------------------------------------------------
# Slice 1 — Data model
# ---------------------------------------------------------------------------

class TestUserOutNewFields:
    """UserOut now exposes has_password, email_verified, password_changed_at."""

    def _make_mock_user(self, **kwargs):
        from unittest.mock import MagicMock
        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = kwargs.get("email", "u@x.com")
        user.yahoo_subject = kwargs.get("yahoo_subject", None)
        user.yahoo_access_token = kwargs.get("yahoo_access_token", None)
        user.google_subject = kwargs.get("google_subject", None)
        user.last_active_profile_id = None
        user.password_hash = kwargs.get("password_hash", None)
        user.email_verified = kwargs.get("email_verified", False)
        user.password_changed_at = kwargs.get("password_changed_at", None)
        return user

    def test_has_password_false_when_no_hash(self):
        user = self._make_mock_user(password_hash=None)
        out = UserOut.model_validate(user)
        assert out.has_password is False

    def test_has_password_true_when_hash_set(self):
        user = self._make_mock_user(password_hash="$argon2id$v=19$...")
        out = UserOut.model_validate(user)
        assert out.has_password is True

    def test_email_verified_false_default(self):
        user = self._make_mock_user(email_verified=False)
        out = UserOut.model_validate(user)
        assert out.email_verified is False

    def test_email_verified_true_propagates(self):
        user = self._make_mock_user(email_verified=True)
        out = UserOut.model_validate(user)
        assert out.email_verified is True

    def test_password_changed_at_none_default(self):
        user = self._make_mock_user(password_changed_at=None)
        out = UserOut.model_validate(user)
        assert out.password_changed_at is None

    def test_password_changed_at_propagates(self):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        user = self._make_mock_user(password_changed_at=ts)
        out = UserOut.model_validate(user)
        assert out.password_changed_at == ts

    def test_yahoo_fantasy_connected_still_works(self):
        user = self._make_mock_user(yahoo_access_token="enc_tok")
        out = UserOut.model_validate(user)
        assert out.yahoo_fantasy_connected is True


class TestAuthTokenModel:
    """AuthToken is registered in Base.metadata and creates correctly."""

    @pytest.mark.asyncio
    async def test_auth_token_creates_and_retrieves(self, test_db):
        user = User(email="u@x.com", password_hash="ph")
        test_db.add(user)
        await test_db.flush()

        now = datetime.now(timezone.utc)
        token = AuthToken(
            user_id=user.id,
            token_hash="abc123",
            token_type="password_reset",
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        test_db.add(token)
        await test_db.commit()

        fetched = await test_db.scalar(select(AuthToken).where(AuthToken.token_hash == "abc123"))
        assert fetched is not None
        assert fetched.token_type == "password_reset"
        assert fetched.used_at is None

    def test_auth_token_fk_has_cascade_delete(self):
        """The FK from auth_tokens.user_id to users.id specifies ON DELETE CASCADE."""
        from sqlalchemy import inspect as sa_inspect
        table = AuthToken.__table__
        fks = list(table.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk.ondelete == "CASCADE"


# ---------------------------------------------------------------------------
# Slice 2 — Email sender / FakeSender / templates
# ---------------------------------------------------------------------------

class TestFakeSender:
    @pytest.mark.asyncio
    async def test_fake_sender_collects_messages(self):
        from app.email.fake_sender import FakeSender
        sender = FakeSender()
        await sender.send(to="a@b.com", subject="Hi", html="<p>hi</p>", text="hi")
        assert len(sender.sent) == 1
        assert sender.sent[0].to == "a@b.com"
        assert sender.sent[0].subject == "Hi"

    @pytest.mark.asyncio
    async def test_fake_sender_clear(self):
        from app.email.fake_sender import FakeSender
        sender = FakeSender()
        await sender.send(to="a@b.com", subject="Hi", html="<p>hi</p>", text="hi")
        sender.clear()
        assert len(sender.sent) == 0

    def test_fake_sender_implements_protocol(self):
        from app.email.fake_sender import FakeSender
        from app.email.sender import EmailSender
        assert isinstance(FakeSender(), EmailSender)


class TestEmailTemplates:
    def test_reset_password_template_contains_url(self):
        from app.email.templates import reset_password_email
        html, text = reset_password_email("https://app.example.com?reset_token=abc")
        assert "https://app.example.com?reset_token=abc" in html
        assert "https://app.example.com?reset_token=abc" in text

    def test_reset_password_template_mentions_expiry(self):
        from app.email.templates import reset_password_email
        html, text = reset_password_email("https://example.com/reset")
        assert "1 hour" in text
        assert "1 hour" in html

    def test_verify_email_template_contains_url(self):
        from app.email.templates import verify_email_email
        html, text = verify_email_email("https://app.example.com?verify_token=xyz")
        assert "https://app.example.com?verify_token=xyz" in html
        assert "https://app.example.com?verify_token=xyz" in text

    def test_verify_email_template_mentions_expiry(self):
        from app.email.templates import verify_email_email
        html, text = verify_email_email("https://example.com/verify")
        assert "72 hours" in text
        assert "72 hours" in html


# ---------------------------------------------------------------------------
# Slice 3 — Forgot password
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signup_response_includes_new_fields(async_client):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    assert r.status_code == 201
    body = r.json()
    user = body["user"]
    assert "has_password" in user
    assert user["has_password"] is True
    assert "email_verified" in user
    assert user["email_verified"] is False
    assert "password_changed_at" in user
    assert user["password_changed_at"] is None


@pytest.mark.asyncio
async def test_signup_sends_verification_email(async_client, fake_sender):
    r = await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    assert r.status_code == 201
    # BackgroundTasks run during the response in ASGI test client
    assert len(fake_sender.sent) == 1
    sent = fake_sender.sent[0]
    assert sent.to == "alice@example.com"
    assert "verify" in sent.subject.lower()
    assert "verify_token" in sent.text


@pytest.mark.asyncio
async def test_forgot_password_always_returns_202(async_client):
    """Non-enumeration: unknown email still returns 202."""
    r = await async_client.post("/api/auth/password/forgot", json={
        "email": "ghost@example.com",
    })
    assert r.status_code == 202
    assert "reset link" in r.json()["detail"].lower() or "registered" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_forgot_password_sends_email_for_known_user(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    r = await async_client.post("/api/auth/password/forgot", json={
        "email": "alice@example.com",
    })
    assert r.status_code == 202
    assert len(fake_sender.sent) == 1
    sent = fake_sender.sent[0]
    assert sent.to == "alice@example.com"
    assert "reset" in sent.subject.lower()
    assert "reset_token" in sent.text


@pytest.mark.asyncio
async def test_forgot_password_does_not_send_for_unknown_email(async_client, fake_sender):
    r = await async_client.post("/api/auth/password/forgot", json={
        "email": "nobody@example.com",
    })
    assert r.status_code == 202
    assert len(fake_sender.sent) == 0


@pytest.mark.asyncio
async def test_forgot_password_rate_limit(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    # 3 requests succeed
    for _ in range(3):
        r = await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
        assert r.status_code == 202

    # 4th request is rate-limited
    r = await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_reset_password_success(async_client, fake_sender, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    fake_sender.clear()

    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    assert len(fake_sender.sent) == 1

    # Extract the reset token from the email
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    r = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    # Session cookie issued
    assert "autotiers_session" in r.cookies

    # Verify DB state
    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))
    await test_db.refresh(user)
    assert user.password_changed_at is not None
    assert user.email_verified is True  # Reset implies inbox control


@pytest.mark.asyncio
async def test_reset_password_sets_email_verified_true(async_client, fake_sender, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    fake_sender.clear()

    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })

    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))
    await test_db.refresh(user)
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_reset_password_can_login_after_reset(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    fake_sender.clear()

    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })
    async_client.cookies.clear()

    r = await async_client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "new shiny password!",
    })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_token_single_use(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    fake_sender.clear()

    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    # First use succeeds
    r1 = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })
    assert r1.status_code == 200

    # Second use fails
    r2 = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "another password!!",
    })
    assert r2.status_code == 400
    assert "already been used" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_reset_password_invalid_token(async_client):
    r = await async_client.post("/api/auth/password/reset", json={
        "token": "notarealtoken",
        "new_password": "new shiny password!",
    })
    assert r.status_code == 400
    assert "Invalid" in r.json()["detail"] or "expired" in r.json()["detail"]


@pytest.mark.asyncio
async def test_reset_password_expired_token(async_client, fake_sender, test_db):
    """An expired token (used_at IS NULL but expires_at in the past) returns 400."""
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expired_token = AuthToken(
        user_id=user.id,
        token_hash=token_hash,
        token_type="password_reset",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=2),  # already expired
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    test_db.add(expired_token)
    await test_db.commit()

    r = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_forgot_password_one_active_token_per_user(async_client, fake_sender, test_db):
    """Re-issuing a reset token deletes the old one."""
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    # Issue first token
    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    first_token_text = fake_sender.sent[0].text
    first_line = [line for line in first_token_text.split("\n") if "reset_token=" in line][0]
    first_raw_token = first_line.split("reset_token=")[1].strip()

    # Issue second token (should invalidate first)
    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    second_token_text = fake_sender.sent[1].text
    second_line = [line for line in second_token_text.split("\n") if "reset_token=" in line][0]
    second_raw_token = second_line.split("reset_token=")[1].strip()

    # First token is now gone from DB
    first_hash = hashlib.sha256(first_raw_token.encode()).hexdigest()
    result = await test_db.scalar(select(AuthToken).where(AuthToken.token_hash == first_hash))
    assert result is None

    # Second token still works
    r = await async_client.post("/api/auth/password/reset", json={
        "token": second_raw_token,
        "new_password": "new shiny password!",
    })
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Slice 4 — Email verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_email_success(async_client, fake_sender, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    # The signup sends a verification email
    assert len(fake_sender.sent) == 1
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "verify_token=" in line][0]
    raw_token = token_line.split("verify_token=")[1].strip()

    r = await async_client.get(f"/api/auth/email/verify?token={raw_token}")
    assert r.status_code == 204

    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))
    await test_db.refresh(user)
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_verify_email_invalid_token(async_client):
    r = await async_client.get("/api/auth/email/verify?token=invalidtoken")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_verify_email_single_use(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "verify_token=" in line][0]
    raw_token = token_line.split("verify_token=")[1].strip()

    # First use
    r1 = await async_client.get(f"/api/auth/email/verify?token={raw_token}")
    assert r1.status_code == 204

    # Second use
    r2 = await async_client.get(f"/api/auth/email/verify?token={raw_token}")
    assert r2.status_code == 400
    assert "already been used" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_resend_verification_sends_email(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    r = await async_client.post("/api/auth/email/resend-verification")
    assert r.status_code == 202
    assert len(fake_sender.sent) == 1
    assert "verify" in fake_sender.sent[0].subject.lower()


@pytest.mark.asyncio
async def test_resend_verification_requires_auth(async_client):
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/email/resend-verification")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_resend_verification_already_verified_returns_400(async_client, fake_sender, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    # Manually mark as verified
    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))
    user.email_verified = True
    await test_db.commit()

    r = await async_client.post("/api/auth/email/resend-verification")
    assert r.status_code == 400
    assert "already verified" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resend_verification_rate_limit(async_client, fake_sender):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    for _ in range(3):
        r = await async_client.post("/api/auth/email/resend-verification")
        assert r.status_code == 202

    r = await async_client.post("/api/auth/email/resend-verification")
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# Slice 4 (#274) — resend-verification surfaces send failures instead of lying
# ---------------------------------------------------------------------------

class _RaisingSender:
    """Email sender stub whose send() always raises, simulating an SES
    MessageRejected / transport error. Used to verify the resend-verification
    endpoint surfaces send failures (#274) rather than swallowing them."""

    def __init__(self) -> None:
        self.attempts = 0

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        self.attempts += 1
        raise RuntimeError("simulated SES MessageRejected")


@pytest.mark.asyncio
async def test_resend_verification_send_failure_returns_502(async_client):
    """When the underlying email send fails, the endpoint must return an error
    status (502) the frontend catch handles — NOT a false 202 (#274).

    Sincerity: against the old fire-and-forget code this assertion fails,
    because the old handler returned 202 regardless of the send outcome.
    """
    from app.main import app

    await async_client.post("/api/auth/signup", json={
        "email": "bob@example.com",
        "password": "correct horse battery",
    })

    # Swap in a sender that always raises. The fake_sender fixture's teardown
    # deletes app.state.email_sender afterward, so this does not leak.
    raising = _RaisingSender()
    app.state.email_sender = raising

    r = await async_client.post("/api/auth/email/resend-verification")

    assert r.status_code == 502
    # The send was actually attempted inline (not fire-and-forget).
    assert raising.attempts == 1
    # Misleading-copy guard (bug-class #1): the error names the email send as
    # the cause, not a generic failure.
    detail = r.json()["detail"].lower()
    assert "verification email" in detail
    assert "try again" in detail


@pytest.mark.asyncio
async def test_resend_verification_send_failure_is_not_2xx(async_client):
    """Defense-in-depth: the failure response must be a non-2xx that the
    frontend banner treats as retryable (reverts to "default"). 429 is the only
    error the banner treats specially; a send failure must NOT be 429 (which
    would mislead the user into thinking they were rate-limited)."""
    from app.main import app

    await async_client.post("/api/auth/signup", json={
        "email": "carol@example.com",
        "password": "correct horse battery",
    })
    app.state.email_sender = _RaisingSender()

    r = await async_client.post("/api/auth/email/resend-verification")

    assert not (200 <= r.status_code < 300)
    assert r.status_code != 429


@pytest.mark.asyncio
async def test_resend_verification_success_still_202(async_client, fake_sender):
    """The happy path is unchanged: a successful inline send still returns 202
    and the email is captured. (Locks the success branch so the failure branch
    cannot be 'fixed' by making everything error.)"""
    await async_client.post("/api/auth/signup", json={
        "email": "dave@example.com",
        "password": "correct horse battery",
    })
    fake_sender.clear()

    r = await async_client.post("/api/auth/email/resend-verification")

    assert r.status_code == 202
    assert len(fake_sender.sent) == 1
    assert "verify" in fake_sender.sent[0].subject.lower()


@pytest.mark.asyncio
async def test_verify_email_expired_token(async_client, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expired_token = AuthToken(
        user_id=user.id,
        token_hash=token_hash,
        token_type="email_verify",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        created_at=datetime.now(timezone.utc) - timedelta(hours=73),
    )
    test_db.add(expired_token)
    await test_db.commit()

    r = await async_client.get(f"/api/auth/email/verify?token={raw_token}")
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Slice 5 — Change / Set password
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_password_success(async_client, test_db):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })

    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "correct horse battery",
        "new_password": "even better battery",
    })
    assert r.status_code == 204

    # Can log in with new password
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "even better battery",
    })
    assert r.status_code == 200

    # password_changed_at is set
    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))
    await test_db.refresh(user)
    assert user.password_changed_at is not None


@pytest.mark.asyncio
async def test_change_password_wrong_current_password(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })

    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "wrong password!!",
        "new_password": "even better battery",
    })
    assert r.status_code == 400
    assert "incorrect" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_change_password_same_as_current(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })

    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "correct horse battery",
        "new_password": "correct horse battery",
    })
    assert r.status_code == 400
    assert "differ" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_change_password_requires_auth(async_client):
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "old",
        "new_password": "new password here",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_password_rejects_short_new_password(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "correct horse battery",
        "new_password": "short",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_change_password_fails_when_no_password_set(async_client, test_db):
    """OAuth-only users (no password) cannot use change-password."""
    # Create an OAuth-only user
    user = User(google_subject="google-sub-123", email="oauthuser@example.com")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    token = encode_jwt(user.id)
    async_client.cookies.set(JWT_COOKIE_NAME, token)

    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "anything",
        "new_password": "new password here",
    })
    assert r.status_code == 400
    assert "set-password" in r.json()["detail"]


@pytest.mark.asyncio
async def test_set_password_success(async_client, test_db):
    """OAuth-only user can set a password for the first time."""
    user = User(google_subject="google-sub-456", email="oauthuser2@example.com")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    token = encode_jwt(user.id)
    async_client.cookies.set(JWT_COOKIE_NAME, token)

    r = await async_client.post("/api/auth/password/set", json={
        "new_password": "brand new password",
    })
    assert r.status_code == 204

    # Verify DB state
    await test_db.refresh(user)
    assert user.password_hash is not None
    assert user.password_changed_at is not None

    # Now can log in with email + new password
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/login", json={
        "email": "oauthuser2@example.com",
        "password": "brand new password",
    })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_set_password_fails_when_password_already_set(async_client):
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    r = await async_client.post("/api/auth/password/set", json={
        "new_password": "another password!",
    })
    assert r.status_code == 400
    assert "change-password" in r.json()["detail"]


@pytest.mark.asyncio
async def test_set_password_requires_email(async_client, test_db):
    """A user with no email cannot set a password."""
    user = User(yahoo_subject="yahoo-sub-789")  # no email
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    token = encode_jwt(user.id)
    async_client.cookies.set(JWT_COOKIE_NAME, token)

    r = await async_client.post("/api/auth/password/set", json={
        "new_password": "brand new password",
    })
    assert r.status_code == 400
    assert "email address" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_set_password_requires_auth(async_client):
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/password/set", json={
        "new_password": "brand new password",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_set_password_rejects_short_password(async_client, test_db):
    user = User(google_subject="google-sub-short", email="short@example.com")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME
    token = encode_jwt(user.id)
    async_client.cookies.set(JWT_COOKIE_NAME, token)

    r = await async_client.post("/api/auth/password/set", json={
        "new_password": "short",
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Cross-slice — token type isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_token_cannot_be_used_as_verify_token(async_client, fake_sender):
    """A password_reset token type cannot be used on the email/verify endpoint."""
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    fake_sender.clear()

    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    # Try to use the reset token on the verify endpoint
    r = await async_client.get(f"/api/auth/email/verify?token={raw_token}")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_verify_token_cannot_be_used_as_reset_token(async_client, fake_sender):
    """An email_verify token cannot be used on the password/reset endpoint."""
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    # The signup sent a verify token
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "verify_token=" in line][0]
    raw_token = token_line.split("verify_token=")[1].strip()

    # Try to use the verify token on the password-reset endpoint
    r = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Issue #241 — Session invalidation via token_version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_password_invalidates_prior_sessions(async_client, fake_sender, test_db):
    """After password reset, a cookie minted with the old token_version returns 401."""
    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME

    # Signup — user is now at token_version=0.
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    # Capture the old session cookie (version=0).
    old_session_cookie = async_client.cookies.get(JWT_COOKIE_NAME)
    assert old_session_cookie is not None

    async_client.cookies.clear()
    fake_sender.clear()

    # Request a reset.
    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    # Consume the reset — this bumps token_version to 1 and issues new cookie.
    r = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "new shiny password!",
    })
    assert r.status_code == 200
    new_session_cookie = async_client.cookies.get(JWT_COOKIE_NAME)
    assert new_session_cookie is not None

    # The new session cookie must work.
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 200

    # The OLD cookie (version=0) must be rejected now that version=1.
    async_client.cookies.clear()
    async_client.cookies.set(JWT_COOKIE_NAME, old_session_cookie)
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 401, "old session cookie should be invalid after reset"


@pytest.mark.asyncio
async def test_change_password_invalidates_prior_sessions(async_client, fake_sender, test_db):
    """After change_password, the old cookie is rejected; the acting device stays logged in."""
    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME

    # Signup — captures version=0 cookie.
    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    old_session_cookie = async_client.cookies.get(JWT_COOKIE_NAME)
    assert old_session_cookie is not None

    # Simulate a second device: manually build a token at version=0.
    user = await test_db.scalar(select(User).where(User.email == "alice@example.com"))
    other_device_token = encode_jwt(user.id, token_version=0)

    # Change password on the first device.
    r = await async_client.post("/api/auth/password/change", json={
        "current_password": "correct horse battery",
        "new_password": "even better battery",
    })
    assert r.status_code == 204

    # First device (the one that changed the password) must still be logged in
    # because change_password re-issues the cookie with the new version.
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 200, "acting device should remain logged in"

    # The other device's old cookie (version=0) must now be rejected.
    async_client.cookies.clear()
    async_client.cookies.set(JWT_COOKIE_NAME, other_device_token)
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 401, "other device's old cookie should be invalid after change"


@pytest.mark.asyncio
async def test_set_password_does_not_bump_token_version(async_client, test_db):
    """set_password (OAuth-only adding a first password) must NOT bump token_version.

    This is additive — there are no prior password-sessions to invalidate.
    """
    from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME

    user = User(google_subject="google-sub-setpw", email="setpw@example.com")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    assert user.token_version == 0

    token = encode_jwt(user.id, token_version=0)
    async_client.cookies.set(JWT_COOKIE_NAME, token)

    r = await async_client.post("/api/auth/password/set", json={
        "new_password": "brand new password",
    })
    assert r.status_code == 204

    await test_db.refresh(user)
    assert user.token_version == 0, "set_password must not bump token_version"

    # Session issued before set_password still works.
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_legacy_token_without_v_claim_works_for_version_zero_user(async_client, test_db):
    """A pre-#241 token (no 'v' claim) is treated as version=0.

    Existing users start at token_version=0, so they stay logged in across deploy.
    """
    import jwt as pyjwt
    from datetime import datetime, timezone
    from app.config import settings
    from app.auth.jwt import JWT_COOKIE_NAME

    user = User(email="legacy@example.com", password_hash="ph")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    assert user.token_version == 0

    # Build a legacy token without the "v" claim.
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(days=30)}
    legacy_token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    async_client.cookies.set(JWT_COOKIE_NAME, legacy_token)
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 200, "legacy token without 'v' claim must work for version-0 user"


# ---------------------------------------------------------------------------
# Issue #242 — Atomic reset-token consumption (concurrent use)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_token_consumption_exactly_one_succeeds(async_client, fake_sender, test_db):
    """Two concurrent consumptions of the same token: exactly one succeeds (200),
    the other gets 400 'already been used'.
    """
    import asyncio

    await async_client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "correct horse battery",
    })
    async_client.cookies.clear()
    fake_sender.clear()

    await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    # Fire two simultaneous reset requests with the same token.
    r1, r2 = await asyncio.gather(
        async_client.post("/api/auth/password/reset", json={
            "token": raw_token, "new_password": "new shiny password!",
        }),
        async_client.post("/api/auth/password/reset", json={
            "token": raw_token, "new_password": "another new password!",
        }),
    )

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 400], (
        f"Expected exactly one success and one failure; got {statuses}"
    )

    # The failure must be 'already been used', not 'expired' or 'invalid'.
    failed = r1 if r1.status_code == 400 else r2
    assert "already been used" in failed.json()["detail"], (
        f"Expected 'already been used', got: {failed.json()['detail']}"
    )


# ---------------------------------------------------------------------------
# Issue #243 — Test coverage gaps
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oauth_only_user_can_reset_and_set_password(async_client, fake_sender, test_db):
    """OAuth-only user (google_subject set, password_hash None) can request a reset,
    consume the token, set a new password, and log in with it.
    Also asserts email_verified is True after reset (inbox control proven).
    """
    # Create an OAuth-only user whose email is NOT yet verified, so the
    # post-reset assertion actually proves reset flips email_verified.
    user = User(
        google_subject="google-sub-oauthonly",
        email="oauthonly@example.com",
        email_verified=False,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    assert user.password_hash is None

    # Request a password reset.
    r = await async_client.post("/api/auth/password/forgot", json={
        "email": "oauthonly@example.com",
    })
    assert r.status_code == 202
    assert len(fake_sender.sent) == 1

    # Extract the token.
    sent_text = fake_sender.sent[0].text
    token_line = [line for line in sent_text.split("\n") if "reset_token=" in line][0]
    raw_token = token_line.split("reset_token=")[1].strip()

    # Consume the token — this sets a password on the OAuth-only account.
    r = await async_client.post("/api/auth/password/reset", json={
        "token": raw_token,
        "new_password": "freshly minted password",
    })
    assert r.status_code == 200

    # reset must flip email_verified False→True (inbox control proven).
    await test_db.refresh(user)
    assert user.email_verified is True
    assert user.password_hash is not None

    # Can log in with the new password.
    async_client.cookies.clear()
    r = await async_client.post("/api/auth/login", json={
        "email": "oauthonly@example.com",
        "password": "freshly minted password",
    })
    assert r.status_code == 200, "should be able to log in with newly set password"


@pytest.mark.asyncio
async def test_mixed_case_email_reset_exact_local_part_match(async_client, fake_sender, test_db):
    """Signed up as Alice@example.com; reset request as alice@example.com.

    Documented behavior (commit 1060588): the DB lookup uses the email as
    Pydantic EmailStr normalises it (domain lowercased, local part preserved).
    Pydantic stores 'Alice@example.com' in the DB. A reset request for
    'alice@example.com' has a different local part — it should NOT find the
    user (no reset email sent). The rate-limit key uses .lower() so both
    addresses share the same throttle bucket.
    """
    # Sign up with mixed-case local part.
    r = await async_client.post("/api/auth/signup", json={
        "email": "Alice@example.com",
        "password": "correct horse battery",
    })
    assert r.status_code == 201
    fake_sender.clear()

    # Confirm what the DB stored.
    user = await test_db.scalar(select(User).where(User.email == "Alice@example.com"))
    assert user is not None, "signup must store Alice@example.com with capital A"

    # Reset request with all-lowercase local part.
    r = await async_client.post("/api/auth/password/forgot", json={
        "email": "alice@example.com",  # different local part from what signup stored
    })
    assert r.status_code == 202  # non-enumerating — always 202
    # No email sent because the DB lookup found no match for 'alice@example.com'.
    assert len(fake_sender.sent) == 0, (
        "reset with mismatched local part must not send email "
        "(DB stores 'Alice@...', lookup key is 'alice@...')"
    )

    # Confirm the rate-limit key collapses both to lowercase.
    # 3 more requests with the canonical form should still exhaust the limit.
    for _ in range(2):
        r = await async_client.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
        assert r.status_code == 202

    r = await async_client.post("/api/auth/password/forgot", json={"email": "Alice@example.com"})
    assert r.status_code == 429, (
        "rate-limit key must be case-insensitive (both Alice@ and alice@ share the bucket)"
    )
