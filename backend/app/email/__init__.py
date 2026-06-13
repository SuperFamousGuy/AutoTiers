"""Email sending infrastructure.

Provides:
- EmailSender: Protocol (structural type) that all senders implement.
- SesSender: AWS SES implementation via aiobotocore.
- FakeSender: In-memory capture for tests and local dev.
- make_email_sender: factory that reads settings.email_sender_backend.
"""
from app.email.sender import EmailSender
from app.email.fake_sender import FakeSender
from app.email.ses_sender import SesSender

__all__ = ["EmailSender", "FakeSender", "SesSender", "make_email_sender"]


def make_email_sender() -> "EmailSender":
    """Return the configured EmailSender based on settings.

    When email_sender_backend == "ses", returns a SesSender.
    Any other value (including "fake") returns a FakeSender.
    The caller is responsible for storing the returned instance on app.state.
    """
    from app.config import settings

    if settings.email_sender_backend == "ses" and not settings.debug:
        return SesSender(
            from_address=settings.ses_from_address,
            region=settings.ses_region,
        )
    return FakeSender()
