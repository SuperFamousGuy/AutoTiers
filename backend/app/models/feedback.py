"""Feedback model — persists in-app feedback submissions.

Every POST /api/feedback writes one row. Submissions are always anonymous
(accounts were removed in the v1 teardown): there is no user identity to
attach and no email is sent — the row is the sole durable record, read by
admins via the existing X-Api-Key-gated GET route.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Wire enum value: "bug" | "idea" | "other". Stored as a plain string so a
    # future category addition needs no DB migration; the API validates the enum.
    category: Mapped[str] = mapped_column(String, nullable=False, server_default="idea")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_feedback_created_at", "created_at"),
    )
