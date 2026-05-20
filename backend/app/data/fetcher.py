"""
Stub DataFetcher — returns no data.
Real implementations for nfl_data_py, FantasyPros, ESPN, and Sleeper
are added in Plan 2 (Data Pipeline).
"""
from sqlalchemy.ext.asyncio import AsyncSession


class DataFetcher:
    async def refresh_all(self, db: AsyncSession) -> dict[str, str]:
        """Fetch all data sources and upsert into the database. Returns status per source."""
        return {
            "nfl_data_py": "stub — not implemented",
            "fantasypros": "stub — not implemented",
            "espn": "stub — not implemented",
            "sleeper": "stub — not implemented",
        }

    async def last_updated(self, db: AsyncSession) -> dict[str, str | None]:
        """Return the most recent last_updated timestamp per data source."""
        from sqlalchemy import select, func
        from app.models.projection import Projection

        result = await db.execute(
            select(Projection.source, func.max(Projection.last_updated))
            .group_by(Projection.source)
        )
        rows = result.all()
        return {source: str(updated) if updated else None for source, updated in rows}


fetcher = DataFetcher()
