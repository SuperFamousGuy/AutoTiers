from datetime import date
from typing import Optional
from sqlalchemy import Integer, String, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TeamSeason(Base):
    __tablename__ = "team_seasons"
    __table_args__ = (UniqueConstraint("team", "season", name="uq_team_seasons_team_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team: Mapped[str] = mapped_column(String(5), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    points_scored: Mapped[int] = mapped_column(Integer, nullable=False)
    points_rank: Mapped[Optional[int]] = mapped_column(Integer)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
