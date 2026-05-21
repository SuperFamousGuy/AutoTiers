from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DataSourceStatus(Base):
    __tablename__ = "data_source_status"

    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_attempted: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
