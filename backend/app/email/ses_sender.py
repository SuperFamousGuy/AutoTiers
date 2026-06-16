"""AWS SES email sender via aiobotocore.

Credentials come from the ECS task IAM role — no env-var credentials.
aiobotocore creates an async boto3-compatible session that reads credentials
from the environment chain: EC2/ECS metadata → ~/.aws → env vars.

The caller (app.state.email_sender) is created once at startup; the
aiobotocore session and client are created fresh per send() call to avoid
connection-pool issues across async task contexts.

IAM requirement: ses:SendEmail on the verified sender identity ARN.
"""
import logging
from typing import Optional

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
    ) -> None:
        """Send via SES SendEmail API.

        Creates a fresh aiobotocore session per call. This is intentional —
        aiobotocore sessions are not concurrency-safe across async contexts
        when sharing a single client, and at the current call volume
        (transactional, low-frequency) the overhead is negligible.

        When ``reply_to`` is provided it is passed as SES ReplyToAddresses so
        the recipient's reply is directed to that address rather than the
        verified From sender. Omitted entirely when None to leave all other
        transactional mail unchanged.
        """
        import aiobotocore.session  # import here to keep it optional for tests

        session = aiobotocore.session.get_session()
        async with session.create_client("ses", region_name=self._region) as client:
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
