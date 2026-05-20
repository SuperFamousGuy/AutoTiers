from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TeamContext(Base):
    __tablename__ = "team_context"
    __table_args__ = (UniqueConstraint("team", "season", name="uq_team_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team: Mapped[str] = mapped_column(String(5), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    off_line_grade: Mapped[Optional[float]] = mapped_column(Float)
    new_head_coach: Mapped[bool] = mapped_column(Boolean, default=False)
    coaching_scheme: Mapped[Optional[str]] = mapped_column(String(50))
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
