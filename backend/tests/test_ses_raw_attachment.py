"""Unit test for SesSender._build_raw_message (MIME assembly for #287)."""
from email import message_from_bytes

from app.email.sender import EmailAttachment
from app.email.ses_sender import SesSender


def test_build_raw_message_includes_body_and_attachment():
    sender = SesSender(from_address="AutoTiers <noreply@autotiers.test>", region="us-east-1")
    att = EmailAttachment(
        filename="shot.png", content_type="image/png", content=b"\x89PNG\x00\x01"
    )
    raw = sender._build_raw_message(
        to="team@autotiers.test",
        subject="AutoTiers feedback [Bug] from alice@example.com",
        html="<p>hi</p>",
        text="hi",
        reply_to="alice@example.com",
        attachments=[att],
    )
    msg = message_from_bytes(raw)
    assert msg["To"] == "team@autotiers.test"
    assert msg["Reply-To"] == "alice@example.com"
    assert msg.is_multipart()

    parts = list(msg.walk())
    content_types = [p.get_content_type() for p in parts]
    assert "text/plain" in content_types
    assert "text/html" in content_types
    assert "image/png" in content_types

    # The attachment carries the filename and the raw bytes round-trip.
    image_part = next(p for p in parts if p.get_content_type() == "image/png")
    assert image_part.get_filename() == "shot.png"
    assert image_part.get_payload(decode=True) == b"\x89PNG\x00\x01"
