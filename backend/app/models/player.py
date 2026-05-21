from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str] = mapped_column(String(10), nullable=False)
    team: Mapped[Optional[str]] = mapped_column(String(5))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    years_exp: Mapped[Optional[int]] = mapped_column(Integer)
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    gsis_id: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    espn_id: Mapped[Optional[str]] = mapped_column(String(20), index=True)

    stats: Mapped[list["PlayerStat"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    projections: Mapped[list["Projection"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    adp_entries: Mapped[list["ADPData"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class PlayerStat(Base):
    __tablename__ = "player_stats"
    __table_args__ = (UniqueConstraint("player_id", "season", name="uq_player_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.id"), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)

    targets: Mapped[Optional[int]] = mapped_column(Integer)
    receptions: Mapped[Optional[int]] = mapped_column(Integer)
    rec_yards: Mapped[Optional[float]] = mapped_column(Float)
    rec_tds: Mapped[Optional[int]] = mapped_column(Integer)
    rush_att: Mapped[Optional[int]] = mapped_column(Integer)
    rush_yards: Mapped[Optional[float]] = mapped_column(Float)
    rush_tds: Mapped[Optional[int]] = mapped_column(Integer)
    pass_att: Mapped[Optional[int]] = mapped_column(Integer)
    pass_yards: Mapped[Optional[float]] = mapped_column(Float)
    pass_tds: Mapped[Optional[int]] = mapped_column(Integer)
    interceptions: Mapped[Optional[int]] = mapped_column(Integer)
    snaps: Mapped[Optional[int]] = mapped_column(Integer)
    snap_pct: Mapped[Optional[float]] = mapped_column(Float)
    carry_share: Mapped[Optional[float]] = mapped_column(Float)
    target_share: Mapped[Optional[float]] = mapped_column(Float)
    games_played: Mapped[Optional[int]] = mapped_column(Integer)
    red_zone_looks: Mapped[Optional[int]] = mapped_column(Integer)
    actual_tds: Mapped[Optional[int]] = mapped_column(Integer)
    expected_tds: Mapped[Optional[float]] = mapped_column(Float)

    player: Mapped["Player"] = relationship(back_populates="stats")
