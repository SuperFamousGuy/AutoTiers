"""FakeSender — in-memory email capture for tests and local development.

Usage in tests:
    fake = FakeSender()
    app.state.email_sender = fake
    # ... make HTTP calls ...
    assert len(fake.sent) == 1
    assert fake.sent[0]["to"] == "user@example.com"
    assert "reset" in fake.sent[0]["subject"].lower()
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str
    text: str


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
    ) -> None:
        self.sent.append(SentEmail(to=to, subject=subject, html=html, text=text))

    def clear(self) -> None:
        self.sent.clear()
