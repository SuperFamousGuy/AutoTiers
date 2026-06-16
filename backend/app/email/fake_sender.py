"""FakeSender — in-memory email capture for tests and local development.

Usage in tests:
    fake = FakeSender()
    app.state.email_sender = fake
    # ... make HTTP calls ...
    assert len(fake.sent) == 1
    assert fake.sent[0].to == "user@example.com"
    assert "reset" in fake.sent[0].subject.lower()
    assert fake.sent[0].reply_to == "submitter@example.com"
    assert fake.sent[0].attachments[0].filename == "screenshot.png"
"""
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.email.sender import EmailAttachment


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str
    text: str
    reply_to: Optional[str] = None
    attachments: list[EmailAttachment] = field(default_factory=list)


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
        attachments: Optional[Sequence[EmailAttachment]] = None,
    ) -> None:
        self.sent.append(
            SentEmail(
                to=to,
                subject=subject,
                html=html,
                text=text,
                reply_to=reply_to,
                attachments=list(attachments or []),
            )
        )

    def clear(self) -> None:
        self.sent.clear()
