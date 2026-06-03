"""User favorites: favorite player IDs and favorite NFL team abbreviations.

One row per user. Both lists are stored as JSON arrays. Caps (20 players,
4 teams) are enforced at the API layer, not in the DB schema, so that an
existing user above-cap from a future cap change is not broken by storage.
"""
import uuid
from sqlalchemy import String, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserFavorites(Base):
    __tablename__ = "user_favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    favorite_player_ids: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    favorite_teams: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )

    user: Mapped["User"] = relationship(back_populates="favorites")
