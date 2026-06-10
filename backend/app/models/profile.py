import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import JSON, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.database import Base

if TYPE_CHECKING:
    from app.models.linked_league import LinkedLeague

# JSONB on Postgres, JSON on SQLite (used in tests). SQLAlchemy doesn't
# auto-fall-back JSONB to JSON, so we declare the variant explicitly.
_JSON_OR_JSONB = JSONB().with_variant(JSON(), "sqlite")


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_profiles_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    settings_json: Mapped[dict] = mapped_column(_JSON_OR_JSONB, nullable=False)
    rules_json: Mapped[dict] = mapped_column(_JSON_OR_JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    linked_league: Mapped[Optional["LinkedLeague"]] = relationship(
        "LinkedLeague",
        cascade="all, delete-orphan",
        uselist=False,
    )
