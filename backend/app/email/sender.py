"""EmailSender protocol — the interface all sender implementations must satisfy."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailSender(Protocol):
    """Protocol for sending transactional email.

    Implementations must be async-safe. The FakeSender is used in all
    tests and in local dev (email_sender_backend != "ses" or debug=True).
    The SesSender is used in production.
    """

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> None:
        """Send a single transactional email.

        Parameters
        ----------
        to:
            Recipient email address (plain address, no display-name wrapping).
        subject:
            Email subject line.
        html:
            HTML body of the email.
        text:
            Plain-text body of the email (fallback for clients that don't render HTML).

        Raises
        ------
        Any exception from the underlying transport. Callers that don't want
        send errors to propagate should catch and log at the call site.
        """
        ...
