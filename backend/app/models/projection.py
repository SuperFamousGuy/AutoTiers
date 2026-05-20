from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Projection(Base):
    __tablename__ = "projections"
    __table_args__ = (
        UniqueConstraint("player_id", "source", "scoring_format", name="uq_projection"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # espn | fantasypros
    scoring_format: Mapped[str] = mapped_column(String(20), nullable=False)
    projected_points: Mapped[float] = mapped_column(Float, nullable=False)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)

    player: Mapped["Player"] = relationship(back_populates="projections")
