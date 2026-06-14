"""FastAPI dependency for resolving the email sender from app.state."""
from fastapi import Request
from app.email.sender import EmailSender


async def get_email_sender(request: Request) -> EmailSender:
    """Resolve the EmailSender from app.state.email_sender.

    In tests, override app.state.email_sender with a FakeSender instance
    before constructing the test client — the overridden value will be
    returned here.
    """
    return request.app.state.email_sender
