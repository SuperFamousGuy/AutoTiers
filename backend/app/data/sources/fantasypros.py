"""FantasyPros scraper — consensus projections + ADP. Resolves players via fuzzy match."""
from __future__ import annotations

import logging
import re
from datetime import datetime, date
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.matching import PositionMatchIndex, fuzzy_match
from app.data.sources.base import SourceResult
from app.models import Player, Projection, ADPData


logger = logging.getLogger(__name__)

_POSITIONS = ("qb", "rb", "wr", "te", "k", "dst")
_ADP_FORMATS = {"standard": "overall", "half_ppr": "half-point-ppr", "ppr": "ppr"}


class FantasyProsFetcher:
    name: ClassVar[str] = "fantasypros"
    base_url: ClassVar[str] = "https://www.fantasypros.com"

    async def fetch(self, db: AsyncSession) -> SourceResult:
        attempted = datetime.utcnow()
        today = date.today()
        upserted = 0
        # Shared across projections (position × format) and ADP so fuzzy_match
        # issues one position query + one normalization pass for the whole run.
        match_index = PositionMatchIndex()
        # Per-request isolation (parity with cbs.py / cbs_rankings.py, issue #834).
        # Previously the whole 21-request loop was wrapped in one try/except that
        # returned rows_upserted=0 on the first failure WITHOUT rolling back. But
        # each parse runs a SELECT that autoflushes the prior iterations' db.add()s
        # into the open transaction, and the orchestrator's single end-of-run
        # commit then persisted those "phantom" rows even though the SourceResult
        # claimed zero — a status/reality mismatch. Now every sub-fetch is isolated:
        # a transient failure on request N is logged and skipped, whatever succeeded
        # is committed, and rows_upserted/success stay consistent with what actually
        # persisted (success is False iff any sub-fetch failed).
        fetch_errors: list[str] = []

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0, follow_redirects=True,
                                          headers={"User-Agent": "Mozilla/5.0 AutoTiers/0.1"}) as client:
                # Projections: position × scoring_format
                for position in _POSITIONS:
                    for ff_format, ff_param in [("standard", "STD"), ("half_ppr", "HALF"), ("ppr", "PPR")]:
                        try:
                            resp = await client.get(f"/nfl/projections/{position}.php", params={"scoring": ff_param, "week": "draft"})
                            resp.raise_for_status()
                            upserted += await self._parse_projections(
                                db, resp.text, position.upper(), ff_format, today, match_index
                            )
                        except Exception as e:  # noqa: BLE001 — isolate per-request failures
                            logger.warning("[fantasypros] failed to fetch %s %s projections: %s",
                                           position, ff_format, e)
                            fetch_errors.append(f"projections {position}/{ff_format}: {e}")
                            continue

                # ADP per format
                for adp_format, slug in _ADP_FORMATS.items():
                    try:
                        resp = await client.get(f"/nfl/adp/{slug}.php")
                        resp.raise_for_status()
                        upserted += await self._parse_adp(db, resp.text, adp_format, today, match_index)
                    except Exception as e:  # noqa: BLE001 — isolate per-request failures
                        logger.warning("[fantasypros adp] failed to fetch %s adp: %s", adp_format, e)
                        fetch_errors.append(f"adp {adp_format}: {e}")
                        continue
        except Exception as e:
            # Client construction / unexpected failure outside a per-request guard.
            # Roll back so we never leave earlier iterations' autoflushed writes in
            # the session for the orchestrator's final commit to persist while we
            # report rows_upserted=0 (the exact mismatch #834 guards against).
            await db.rollback()
            return SourceResult(source=self.name, rows_upserted=0,
                                last_attempted=attempted, success=False, error=str(e))

        await db.commit()

        if fetch_errors:
            # Partial run: some sub-fetches succeeded and are now committed, others
            # failed. Report the true committed count and success=False so status
            # and reality agree.
            return SourceResult(source=self.name, rows_upserted=upserted,
                                last_attempted=attempted, success=False,
                                error="; ".join(fetch_errors))

        return SourceResult(source=self.name, rows_upserted=upserted,
                            last_attempted=attempted, success=True, error=None)

    async def _parse_projections(
        self, db: AsyncSession, html: str, position: str, scoring_format: str, today: date,
        match_index: PositionMatchIndex | None = None,
    ) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="data")
        if table is None:
            return 0

        # Find the FPTS column index by inspecting the header row.
        # FantasyPros has tables with columns like: Player, ATT, CMP, YDS, TDS, INTS, ..., FPTS
        # We want FPTS (season total). Older versions had FPTS as the last column;
        # newer versions sometimes append an "AVG" column after it. Look up by header text.
        fpts_idx: int | None = None
        header_row = table.find("thead")
        if header_row is not None:
            header_cells = header_row.find_all("th")
            for i, th in enumerate(header_cells):
                text = th.get_text(strip=True).upper()
                if text == "FPTS":
                    fpts_idx = i
                    break

        # Fallback: assume last cell (legacy behavior). Log a warning so we know.
        if fpts_idx is None:
            logger.warning(
                "[fantasypros] FPTS header column not found for %s; falling back to last cell",
                position,
            )

        # Sanity-check threshold: season-total projections should be way above
        # per-game numbers. Log a warning if scraped values look too small.
        season_total_min_expected = {"QB": 100, "RB": 50, "WR": 50, "TE": 30}

        # Batch the existence check: one SELECT for every existing projection of
        # this (source, scoring_format) up front, then look up / insert against
        # the dict. Avoids an N+1 of one round-trip SELECT per scraped row.
        existing_by_player: dict[str, Projection] = {
            row.player_id: row
            for row in (await db.scalars(
                select(Projection).where(
                    Projection.source == "fantasypros",
                    Projection.scoring_format == scoring_format,
                )
            )).all()
        }

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            name, team = self._parse_player_cell(cells[0])
            if not name:
                continue

            # Read the FPTS column.
            try:
                if fpts_idx is not None and fpts_idx < len(cells):
                    points_cell = cells[fpts_idx]
                else:
                    points_cell = cells[-1]
                points = float(points_cell.get_text(strip=True).replace(",", ""))
            except (ValueError, IndexError):
                continue

            # Sanity check: if a top-row player has way-too-small projection,
            # we might still be reading per-game data. Just log; don't fail.
            if upserted == 0 and points < season_total_min_expected.get(position, 0):
                logger.warning(
                    "[fantasypros] %s top player %s has FPTS=%.1f which looks like per-game data, "
                    "not season-total. Check the scraper URL/column logic.",
                    position, name, points,
                )

            player = await fuzzy_match(db, name, team, position, index=match_index)
            if player is None:
                logger.warning("[fantasypros] unmatched %s | %s %s", position, name, team or "?")
                continue

            existing = existing_by_player.get(player.id)
            if existing is None:
                new_row = Projection(player_id=player.id, source="fantasypros",
                                     scoring_format=scoring_format, projected_points=points,
                                     last_updated=today)
                db.add(new_row)
                existing_by_player[player.id] = new_row
            else:
                existing.projected_points = points
                existing.last_updated = today
            upserted += 1
        return upserted

    async def _parse_adp(
        self, db: AsyncSession, html: str, fmt: str, today: date,
        match_index: PositionMatchIndex | None = None,
    ) -> int:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="data")
        if table is None:
            return 0

        # Batch the existence check: one SELECT for every existing ADP row of
        # this (adp_source, format) up front, then look up / insert against the
        # dict instead of one round-trip SELECT per scraped row.
        existing_by_player: dict[str, ADPData] = {
            row.player_id: row
            for row in (await db.scalars(
                select(ADPData).where(
                    ADPData.adp_source == "fantasypros",
                    ADPData.format == fmt,
                )
            )).all()
        }

        upserted = 0
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            name, team = self._parse_player_cell(cells[1])
            pos_text = cells[2].get_text(strip=True)
            # Strip trailing tier digits, e.g. "WR1" → "WR"
            position = re.sub(r"\d+$", "", pos_text)
            try:
                adp_val = float(cells[3].get_text(strip=True))
            except ValueError:
                continue
            if not name:
                continue

            player = await fuzzy_match(db, name, team, position, index=match_index)
            if player is None:
                logger.warning("[fantasypros adp] unmatched %s %s | %s", fmt, name, team or "?")
                continue

            existing = existing_by_player.get(player.id)
            if existing is None:
                new_row = ADPData(player_id=player.id, format=fmt, adp=adp_val,
                                  adp_source="fantasypros", last_updated=today)
                db.add(new_row)
                existing_by_player[player.id] = new_row
            else:
                existing.adp = adp_val
                existing.last_updated = today
            upserted += 1
        return upserted

    @staticmethod
    def _parse_player_cell(cell) -> tuple[str, str]:
        """Pull (name, team) from a FantasyPros player cell. Name is the <a> text, team is the <small>."""
        a = cell.find("a")
        small = cell.find("small")
        name = a.get_text(strip=True) if a else cell.get_text(strip=True)
        team = small.get_text(strip=True) if small else ""
        return name, team
