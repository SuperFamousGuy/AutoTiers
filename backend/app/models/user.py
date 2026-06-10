import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    yahoo_subject: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    yahoo_access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    yahoo_refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    google_subject: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_active_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL", use_alter=True, name="fk_users_last_active_profile"),
        nullable=True,
    )

    favorites: Mapped[Optional["UserFavorites"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
