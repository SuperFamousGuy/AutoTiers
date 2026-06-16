"""FakeSender — in-memory email capture for tests and local development.

Usage in tests:
    fake = FakeSender()
    app.state.email_sender = fake
    # ... make HTTP calls ...
    assert len(fake.sent) == 1
    assert fake.sent[0].to == "user@example.com"
    assert "reset" in fake.sent[0].subject.lower()
    assert fake.sent[0].reply_to == "submitter@example.com"
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str
    text: str
    reply_to: Optional[str] = None


class FakeSender:
    """Collects outbound emails into `self.sent` list instead of sending them.

    Thread/task-safe enough for single-process test runs.
    Call `clear()` between tests (or create a fresh instance per test).
    """

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        reply_to: Optional[str] = None,
    ) -> None:
        self.sent.append(
            SentEmail(to=to, subject=subject, html=html, text=text, reply_to=reply_to)
        )

    def clear(self) -> None:
        self.sent.clear()
