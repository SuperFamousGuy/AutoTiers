"""EmailSender protocol — the interface all sender implementations must satisfy."""
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class EmailAttachment:
    """A single email attachment.

    filename:
        Display name shown in the recipient's mail client. Callers are
        responsible for passing a sanitized basename — do not pass raw,
        user-controlled paths.
    content_type:
        MIME type, e.g. "image/png". Used for the attachment's Content-Type.
    content:
        Raw decoded bytes of the attachment.
    """

    filename: str
    content_type: str
    content: bytes


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
        reply_to: Optional[str] = None,
        attachments: Optional[Sequence[EmailAttachment]] = None,
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
        reply_to:
            Optional Reply-To address. When set, replies from the recipient go
            to this address instead of the From sender. Used by feedback so the
            team can reply directly to the submitter. Omitted (None) by default
            to preserve the existing behaviour of all other transactional mail.
        attachments:
            Optional sequence of EmailAttachment. When present, the implementation
            sends a MIME multipart message (SES raw email) so the files ride
            along with the body. None/empty preserves the existing simple-send
            path used by all other transactional mail.

        Raises
        ------
        Any exception from the underlying transport. Callers that don't want
        send errors to propagate should catch and log at the call site.
        """
        ...
