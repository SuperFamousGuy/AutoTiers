"""AWS SES email sender via aiobotocore.

Credentials come from the ECS task IAM role — no env-var credentials.
aiobotocore creates an async boto3-compatible session that reads credentials
from the environment chain: EC2/ECS metadata → ~/.aws → env vars.

The caller (app.state.email_sender) is created once at startup; the
aiobotocore session and client are created fresh per send() call to avoid
connection-pool issues across async task contexts.

IAM requirement: ses:SendEmail (simple sends) and ses:SendRawEmail
(attachment sends) on the verified sender identity ARN.
"""
import logging
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Optional, Sequence

from app.email.sender import EmailAttachment

logger = logging.getLogger(__name__)


class SesSender:
    """Send email via AWS SES using aiobotocore.

    Parameters
    ----------
    from_address:
        The verified SES sender, e.g. "AutoTiers <noreply@autotiers.com>".
    region:
        AWS region where the SES identity is verified, e.g. "us-east-1".
    """

    def __init__(self, *, from_address: str, region: str) -> None:
        self._from_address = from_address
        self._region = region

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
        """Send via SES.

        Creates a fresh aiobotocore session per call. This is intentional —
        aiobotocore sessions are not concurrency-safe across async contexts
        when sharing a single client, and at the current call volume
        (transactional, low-frequency) the overhead is negligible.

        With no attachments this uses the SES SendEmail API exactly as before.
        With attachments it builds a MIME multipart message and uses
        SendRawEmail so the files ride along inline. reply_to maps to either
        ReplyToAddresses (SendEmail) or a Reply-To header (raw MIME).
        """
        import aiobotocore.session  # import here to keep it optional for tests

        session = aiobotocore.session.get_session()
        async with session.create_client("ses", region_name=self._region) as client:
            if attachments:
                raw = self._build_raw_message(
                    to=to,
                    subject=subject,
                    html=html,
                    text=text,
                    reply_to=reply_to,
                    attachments=attachments,
                )
                await client.send_raw_email(RawMessage={"Data": raw})
                return

            kwargs: dict = {
                "Source": self._from_address,
                "Destination": {"ToAddresses": [to]},
                "Message": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text, "Charset": "UTF-8"},
                        "Html": {"Data": html, "Charset": "UTF-8"},
                    },
                },
            }
            if reply_to:
                kwargs["ReplyToAddresses"] = [reply_to]
            await client.send_email(**kwargs)

    def _build_raw_message(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        reply_to: Optional[str],
        attachments: Sequence[EmailAttachment],
    ) -> bytes:
        """Build a MIME message with text+html body and file attachments.

        Uses the stdlib EmailMessage builder, which produces a correctly
        structured multipart/mixed -> multipart/alternative tree.
        """
        msg = EmailMessage()
        msg["From"] = self._from_address
        msg["To"] = to
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to
        msg["Message-ID"] = make_msgid()

        # text + html alternative body.
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        for att in attachments:
            maintype, _, subtype = att.content_type.partition("/")
            if not maintype or not subtype:
                # Defensive: fall back to a generic binary type so a bad
                # content_type never crashes the send.
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(
                att.content,
                maintype=maintype,
                subtype=subtype,
                filename=att.filename,
            )

        return msg.as_bytes()
