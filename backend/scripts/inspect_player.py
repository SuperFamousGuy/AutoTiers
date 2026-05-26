"""
Inspect why each built-in rule did or didn't fire for a given player.

Usage (in the api container, or any env with DATABASE_URL set):
    python -m scripts.inspect_player "Derrick Henry"

Resolves the player by case-insensitive substring match against Player.name.
Prints metadata, all stat rows (most recent first), the computed PlayerContext
fields the rules engine sees, and a PASS/FAIL line per built-in rule.

This is a one-off diagnostic, not a production endpoint.
"""
from __future__ import annotations

import asyncio
import statistics
import sys
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.engine.builtin_rules import BUILTIN_RULES, OVER_THE_HILL_AGE
from app.engine.rules import PlayerContext, _OPS, apply_rules
from app.models import PlayerContract, TeamSeason
from app.models.player import Player


def _fmt(v: object) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if not v.is_integer() else str(int(v))
    return str(v)


async def _compute_bad_offense_teams(db, current_year: int) -> set[str]:
    cutoff = current_year - 3
    rows = (await db.scalars(
        select(TeamSeason).where(TeamSeason.season >= cutoff)
    )).all()
    by_team: dict[str, list[int]] = {}
    for r in rows:
        by_team.setdefault(r.team, []).append(r.points_scored)
    team_avg = {
        team: sum(pts) / len(pts)
        for team, pts in by_team.items()
        if len(pts) >= 2
    }
    bottom = sorted(team_avg.items(), key=lambda kv: kv[1])[:8]
    return {team for team, _ in bottom}


async def _compute_above_market_pids(db, current_year: int) -> set[str]:
    contract_rows = (await db.scalars(
        select(PlayerContract).where(PlayerContract.season == current_year)
    )).all()
    pid_to_cap = {pc.player_id: pc.cap_hit for pc in contract_rows}
    players = (await db.scalars(select(Player))).all()
    pid_to_pos = {p.id: p.position for p in players}

    by_pos: dict[str, list[float]] = {}
    for pid, cap in pid_to_cap.items():
        pos = pid_to_pos.get(pid)
        if pos in ("QB", "RB", "WR", "TE"):
            by_pos.setdefault(pos, []).append(cap)

    threshold = {
        pos: statistics.median(caps) * 1.5
        for pos, caps in by_pos.items()
        if len(caps) >= 5
    }
    return {
        pid for pid, cap in pid_to_cap.items()
        if (pos := pid_to_pos.get(pid)) in threshold and cap > threshold[pos]
    }


async def inspect(name_query: str) -> None:
    async with AsyncSessionLocal() as db:
        # Fuzzy substring match (case-insensitive).
        matches = (await db.scalars(
            select(Player)
            .where(Player.name.ilike(f"%{name_query}%"))
            .options(selectinload(Player.stats))
        )).all()

        if not matches:
            print(f"No player found matching '{name_query}'.")
            return

        if len(matches) > 1:
            print(f"Multiple players match '{name_query}':")
            for p in matches:
                print(f"  - {p.name} ({p.position}, {p.team})")
            print("Refine the query.")
            return

        p = matches[0]
        current_year = datetime.utcnow().year

        bad_offense_teams = await _compute_bad_offense_teams(db, current_year)
        above_market_pids = await _compute_above_market_pids(db, current_year)

        # ---------- Player metadata ----------
        print(f"\nPlayer: {p.name}")
        print(f"  id:         {p.id}")
        print(f"  gsis_id:    {p.gsis_id}")
        print(f"  position:   {p.position}")
        print(f"  team:       {p.team}")
        print(f"  age:        {_fmt(p.age)}")
        print(f"  years_exp:  {_fmt(p.years_exp)}")

        # ---------- Stat rows ----------
        stats_sorted = sorted(p.stats, key=lambda s: s.season, reverse=True)
        if not stats_sorted:
            print("\nNo PlayerStat rows for this player.")
            most_recent = None
            two_seasons_ago_stat = None
        else:
            most_recent = stats_sorted[0]
            two_seasons_ago_stat = next(
                (s for s in stats_sorted if s.season == current_year - 2), None
            )
            print("\nStat rows (most recent first):")
            for s in stats_sorted:
                marker = "  ← most-recent" if s is most_recent else ""
                print(f"\n  Season {s.season}:{marker}")
                print(f"    games_played:    {_fmt(s.games_played)}")
                print(f"    rush_att:        {_fmt(s.rush_att)}")
                print(f"    receptions:      {_fmt(s.receptions)}")
                print(f"    targets:         {_fmt(s.targets)}")
                print(f"    snap_pct:        {_fmt(s.snap_pct)}")
                print(f"    carry_share:     {_fmt(s.carry_share)}")
                print(f"    target_share:    {_fmt(s.target_share)}")
                print(f"    red_zone_looks:  {_fmt(s.red_zone_looks)}")
                print(f"    actual_tds:      {_fmt(s.actual_tds)}")
                print(f"    expected_tds:    {_fmt(s.expected_tds)}")

        # ---------- PlayerContext (what the engine sees) ----------
        stat = most_recent
        is_over_the_hill: Optional[bool] = None
        if p.age is not None and p.position in OVER_THE_HILL_AGE:
            is_over_the_hill = p.age >= OVER_THE_HILL_AGE[p.position]

        prior_touches: Optional[int] = None
        if p.position == "RB" and stat is not None:
            prior_touches = (stat.rush_att or 0) + (stat.receptions or 0)

        injured_two_years_ago: Optional[bool] = None
        if p.position in ("RB", "WR") and two_seasons_ago_stat is not None:
            injured_two_years_ago = (two_seasons_ago_stat.games_played or 0) < 12

        bad_offense_team: Optional[bool] = None
        if p.position in ("QB", "RB", "WR", "TE"):
            bad_offense_team = p.team in bad_offense_teams

        above_market_contract: Optional[bool] = None
        if p.position in ("QB", "RB", "WR", "TE"):
            above_market_contract = p.id in above_market_pids

        actual_tds_above_expected: Optional[float] = None
        if stat and stat.actual_tds is not None and stat.expected_tds is not None:
            actual_tds_above_expected = stat.actual_tds - stat.expected_tds

        ctx = PlayerContext(
            player_id=p.id,
            position=p.position,
            age=p.age,
            snap_pct=stat.snap_pct if stat else None,
            carry_share=stat.carry_share if stat else None,
            target_share=stat.target_share if stat else None,
            games_played=stat.games_played if stat else None,
            years_exp=p.years_exp or 0,
            adp=None,
            projected_score=0.0,  # not used by any rule
            new_team=False,
            new_coach=False,
            actual_tds=stat.actual_tds if stat else None,
            expected_tds=stat.expected_tds if stat else None,
            actual_tds_above_expected=actual_tds_above_expected,
            red_zone_looks=stat.red_zone_looks if stat else None,
            is_over_the_hill=is_over_the_hill,
            projection_unavailable=False,  # would need projection lookup
            prior_touches=prior_touches,
            injured_two_years_ago=injured_two_years_ago,
            bad_offense_team=bad_offense_team,
            above_market_contract=above_market_contract,
        )

        # ---------- Rule evaluation ----------
        print("\nRule eligibility (most-recent-season fields):")
        print(f"  {'Rule':<32} {'Condition':<42} {'Player value':<20} Result")
        print(f"  {'-' * 32} {'-' * 42} {'-' * 20} ------")

        for rule in BUILTIN_RULES:
            cond_strs: list[str] = []
            val_strs: list[str] = []
            results: list[bool] = []
            for c in rule.conditions:
                cond_strs.append(f"{c.field} {c.operator} {c.value!r}")
                val = getattr(ctx, c.field, None)
                val_strs.append(_fmt(val))
                op_fn = _OPS.get(c.operator)
                if val is None or op_fn is None:
                    results.append(False)
                else:
                    try:
                        results.append(bool(op_fn(val, c.value)))
                    except Exception:
                        results.append(False)
            all_pass = all(results)
            cond_str = " AND ".join(cond_strs)
            val_str = " · ".join(val_strs)
            outcome = "PASS" if all_pass else "fail"
            print(f"  {rule.name:<32} {cond_str:<42} {val_str:<20} {outcome}")

        # ---------- Computed-field summary ----------
        print("\nComputed context fields:")
        print(f"  is_over_the_hill:       {_fmt(is_over_the_hill)}")
        print(f"  prior_touches:          {_fmt(prior_touches)}")
        print(f"  injured_two_years_ago:  {_fmt(injured_two_years_ago)}")
        print(f"  bad_offense_team:       {_fmt(bad_offense_team)}")
        print(f"  above_market_contract:  {_fmt(above_market_contract)}")

        # ---------- Apply rules end-to-end ----------
        result = apply_rules(100.0, ctx, BUILTIN_RULES)
        if result.rule_applications:
            print(f"\napply_rules() fired {len(result.rule_applications)} rules on a baseline of 100.0:")
            for app in result.rule_applications:
                arrow = "→" if app.effect_type.value != "flag" else " "
                print(
                    f"  {app.name:<32} delta={app.delta:+.2f}  {arrow} {app.after_score:.2f}"
                )
        else:
            print("\napply_rules() fired 0 rules.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.inspect_player \"<player name>\"")
        sys.exit(1)
    asyncio.run(inspect(" ".join(sys.argv[1:])))
