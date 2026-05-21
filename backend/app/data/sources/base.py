"""Source-agnostic protocol and result type for data fetchers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SourceResult:
    source: str
    rows_upserted: int
    last_attempted: datetime
    success: bool
    error: Optional[str] = None


class SourceFetcher(Protocol):
    name: str

    async def fetch(self, db: AsyncSession) -> SourceResult: ...
