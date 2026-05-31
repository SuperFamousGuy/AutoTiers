import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import JSON, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.database import Base

# Same JSON/JSONB variant pattern used by Profile.
_JSON_OR_JSONB = JSONB().with_variant(JSON(), "sqlite")


class LinkedLeague(Base):
    __tablename__ = "linked_leagues"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)  # "sleeper" | "espn"
    league_id: Mapped[str] = mapped_column(String, nullable=False)
    username_or_swid: Mapped[str] = mapped_column(String, nullable=False)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    league_metadata_json: Mapped[dict] = mapped_column(_JSON_OR_JSONB, nullable=False)
    keepers_json: Mapped[list] = mapped_column(_JSON_OR_JSONB, nullable=False)
    adp_json: Mapped[Optional[dict]] = mapped_column(_JSON_OR_JSONB, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
