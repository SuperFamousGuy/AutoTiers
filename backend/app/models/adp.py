from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ADPData(Base):
    __tablename__ = "adp_data"
    __table_args__ = (
        UniqueConstraint("player_id", "format", "adp_source", name="uq_adp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)  # standard | half_ppr | ppr | dynasty
    adp: Mapped[float] = mapped_column(Float, nullable=False)
    adp_source: Mapped[str] = mapped_column(String(30), nullable=False)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)

    player: Mapped["Player"] = relationship(back_populates="adp_entries")
