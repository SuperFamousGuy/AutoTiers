"""Read/write helpers for DataSourceStatus rows."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSourceStatus


# Sources we no longer fetch. Stale status rows left over from prior
# deployments are purged on refresh so they don't linger as perpetual
# errors/noise in API and UI responses (see issue #402, spotrac).
RETIRED_SOURCES = ("spotrac",)


async def upsert_status(
    db: AsyncSession,
    source: str,
    last_attempted: datetime,
    success: bool,
    rows_upserted: int,
    error: Optional[str],
) -> None:
    """Upsert a status row. `last_updated` only advances on success."""
    existing = await db.scalar(select(DataSourceStatus).where(DataSourceStatus.source == source))
    if existing is None:
        existing = DataSourceStatus(source=source, last_attempted=last_attempted, rows_upserted=0)
        db.add(existing)
    existing.last_attempted = last_attempted
    existing.last_error = error
    if success:
        existing.last_updated = last_attempted
        existing.rows_upserted = rows_upserted


async def purge_retired_status(db: AsyncSession) -> None:
    """Delete status rows for sources we no longer fetch (issue #402).

    Caller is responsible for committing; refresh_all() flushes this alongside
    the freshly-upserted status rows.
    """
    await db.execute(delete(DataSourceStatus).where(DataSourceStatus.source.in_(RETIRED_SOURCES)))


async def get_all_status(db: AsyncSession) -> dict[str, dict]:
    """Return a {source: {...}} dict for all sources currently tracked."""
    rows = (await db.scalars(select(DataSourceStatus))).all()
    return {
        r.source: {
            "last_updated": r.last_updated.isoformat() if r.last_updated else None,
            "last_attempted": r.last_attempted.isoformat() if r.last_attempted else None,
            "last_error": r.last_error,
            "rows_upserted": r.rows_upserted,
        }
        for r in rows
    }
