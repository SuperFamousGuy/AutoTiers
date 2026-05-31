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
    # league_id / league_metadata_json / keepers_json are nullable: users can
    # link a provider account without selecting a league (so we can pull
    # auth-gated rankings later even if they haven't joined a league).
    league_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    username_or_swid: Mapped[str] = mapped_column(String, nullable=False)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    league_metadata_json: Mapped[Optional[dict]] = mapped_column(_JSON_OR_JSONB, nullable=True)
    keepers_json: Mapped[Optional[list]] = mapped_column(_JSON_OR_JSONB, nullable=True)
    adp_json: Mapped[Optional[dict]] = mapped_column(_JSON_OR_JSONB, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
