from datetime import date
from typing import Optional
from sqlalchemy import Integer, String, Float, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PlayerContract(Base):
    __tablename__ = "player_contracts"
    __table_args__ = (UniqueConstraint("player_id", "season", name="uq_player_contracts_player_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_hit: Mapped[float] = mapped_column(Float, nullable=False)
    base_salary: Mapped[Optional[float]] = mapped_column(Float)
    signing_bonus: Mapped[Optional[float]] = mapped_column(Float)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
