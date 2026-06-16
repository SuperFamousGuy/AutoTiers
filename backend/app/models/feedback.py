"""Feedback model — persists in-app feedback submissions.

Every POST /api/feedback writes one row BEFORE the email is sent, so a feedback
submission is never lost if SES bounces (the email send can fail after the row
is committed; the row is the durable record). user_id is nullable: anonymous
submissions are valid. submitter_email is a denormalized snapshot of the
authenticated user's email at submission time so the admin read view does not
have to join users (and survives a later account deletion via SET NULL).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable FK: anonymous submissions have no user. ON DELETE SET NULL keeps
    # the feedback row (the content is still useful) if the user is later deleted.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Snapshot of the submitter's email for admin readability; None for anonymous.
    submitter_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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
