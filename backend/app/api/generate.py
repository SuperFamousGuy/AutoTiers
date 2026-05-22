import csv
import dataclasses
import io
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models.adp import ADPData
from app.engine.scoring import LeagueSettings, PlayerStats, calculate_fantasy_points, blend_scores
from app.engine.rules import Rule, RuleCondition, RuleEffect, PlayerContext, apply_rules
from app.engine.builtin_rules import BUILTIN_RULES
from app.engine.tiers import TieredPlayer, assign_tiers
from app.schemas.generate import GenerateRequest, GenerateResponse, TieredPlayerOut

router = APIRouter()


async def _compute_data_as_of(db: AsyncSession) -> Optional[str]:
    """Return ISO date of the oldest successful source refresh, or None if no source has succeeded."""
    from app.models import DataSourceStatus
    rows = (await db.scalars(select(DataSourceStatus).where(DataSourceStatus.last_updated.is_not(None)))).all()
    if not rows:
        return None
    oldest = min(r.last_updated for r in rows)
    return oldest.date().isoformat()


def _build_league_settings(req: GenerateRequest) -> LeagueSettings:
    return LeagueSettings(
        scoring_format=req.scoring_format,
        league_type=req.league_type,
        league_size=req.league_size,
        qb_td_points=req.qb_td_points,
        bonus_100yd_rushing=req.bonus_100yd_rushing,
        bonus_100yd_receiving=req.bonus_100yd_receiving,
        bonus_first_downs=req.bonus_first_downs,
        weight_prior_year=req.weight_prior_year,
        weight_espn=req.weight_espn,
        weight_consensus=req.weight_consensus,
    )


def _schema_to_rule(schema) -> Rule:
    return Rule(
        name=schema.name,
        conditions=[RuleCondition(field=c.field, operator=c.operator, value=c.value) for c in schema.conditions],
        effect=RuleEffect(type=schema.effect.type, value=schema.effect.value),
        enabled=schema.enabled,
        weight=schema.weight,
    )


def _get_stat(stats: list[PlayerStat]) -> Optional[PlayerStat]:
    if not stats:
        return None
    return max(stats, key=lambda s: s.season)


def _get_projection(projections: list[Projection], source: str, fmt: str) -> Optional[float]:
    for p in projections:
        if p.source == source and p.scoring_format == fmt:
            return p.projected_points
    return None


def _get_adp(adp_entries: list[ADPData], scoring_fmt: str, league_type: str = "redraft") -> Optional[float]:
    if league_type == "dynasty":
        adp_fmt = "dynasty"
    elif scoring_fmt == "te_premium":
        adp_fmt = "ppr"
    else:
        adp_fmt = scoring_fmt
    for a in adp_entries:
        if a.format == adp_fmt:
            return a.adp
    return None


async def _run_generate(req: GenerateRequest, db: AsyncSession) -> list[TieredPlayer]:
    settings = _build_league_settings(req)
    scoring_fmt = req.scoring_format.value

    # Merge built-in + user-provided rules, deduplicating by name.
    # For each built-in: apply user's enabled/weight overrides if submitted.
    # Custom rules (names not in BUILTIN_RULES) are appended after.
    # User-submitted values always take precedence; last write wins for any
    # remaining duplicates via the merged dict.
    builtin_by_name = {r.name: r for r in BUILTIN_RULES}
    user_rule_map = {
        schema.name: dataclasses.replace(builtin_by_name[schema.name], enabled=schema.enabled, weight=schema.weight)
        for schema in req.rules
        if schema.name in builtin_by_name
    }
    custom_rules = [
        _schema_to_rule(schema)
        for schema in req.rules
        if schema.name not in builtin_by_name
    ]
    merged: dict[str, Rule] = {}
    for br in BUILTIN_RULES:
        if br.name in user_rule_map:
            merged[br.name] = user_rule_map[br.name]
        else:
            merged[br.name] = br
    for cr in custom_rules:
        merged[cr.name] = cr  # custom always wins (already deduplicated by name)
    rules = list(merged.values())

    result = await db.execute(
        select(Player)
        .options(
            selectinload(Player.stats),
            selectinload(Player.projections),
            selectinload(Player.adp_entries),
        )
    )
    players = result.scalars().all()

    tiered: list[TieredPlayer] = []
    for player in players:
        stat = _get_stat(player.stats)
        espn_pts = _get_projection(player.projections, "espn", scoring_fmt)
        fp_pts = _get_projection(player.projections, "fantasypros", scoring_fmt)

        prior_actual: Optional[float] = None
        if stat:
            ps = PlayerStats(
                targets=stat.targets or 0,
                receptions=stat.receptions or 0,
                rec_yards=stat.rec_yards or 0.0,
                rec_tds=stat.rec_tds or 0,
                rush_att=stat.rush_att or 0,
                rush_yards=stat.rush_yards or 0.0,
                rush_tds=stat.rush_tds or 0,
                pass_att=stat.pass_att or 0,
                pass_yards=stat.pass_yards or 0.0,
                pass_tds=stat.pass_tds or 0,
                interceptions=stat.interceptions or 0,
                games_played=stat.games_played or 1,
            )
            prior_actual = calculate_fantasy_points(ps, settings, position=player.position)

        blended = blend_scores(
            prior_year_actual=prior_actual,
            espn_projection=espn_pts,
            consensus_projection=fp_pts,
            settings=settings,
        )

        flags_list: list[str] = []
        if prior_actual is None and espn_pts is None and fp_pts is None:
            flags_list.append("Rookie — Limited Data")
        elif espn_pts is None and fp_pts is None:
            flags_list.append("Projection Unavailable")

        league_type_val = req.league_type.value if hasattr(req.league_type, "value") else req.league_type
        ctx = PlayerContext(
            player_id=player.id,
            position=player.position,
            age=player.age,
            snap_pct=stat.snap_pct if stat else None,
            carry_share=stat.carry_share if stat else None,
            target_share=stat.target_share if stat else None,
            games_played=stat.games_played if stat else None,
            years_exp=player.years_exp or 0,
            adp=_get_adp(player.adp_entries, scoring_fmt, league_type_val),
            projected_score=blended,
            new_team=False,
            new_coach=False,
            actual_tds=stat.actual_tds if stat else None,
            expected_tds=stat.expected_tds if stat else None,
            actual_tds_above_expected=(
                stat.actual_tds - stat.expected_tds
                if stat and stat.actual_tds is not None and stat.expected_tds is not None
                else None
            ),
            red_zone_looks=stat.red_zone_looks if stat else None,
        )

        rule_result = apply_rules(blended, ctx, rules)
        rule_result.flags.extend(flags_list)

        tiered.append(TieredPlayer(
            player_id=player.id,
            name=player.name,
            position=player.position,
            team=player.team,
            age=player.age,
            adjusted_score=rule_result.adjusted_score,
            projected_score_raw=blended,
            prior_year_actual=prior_actual,
            adp_standard=_get_adp(player.adp_entries, "standard"),
            adp_ppr=_get_adp(player.adp_entries, "ppr"),
            adp_dynasty=_get_adp(player.adp_entries, "dynasty"),
            flags=rule_result.flags,
            rules_applied=rule_result.rules_applied,
            overall_rank=0,
            overall_tier=0,
            positional_tier="",
        ))

    league_type_str = req.league_type.value if hasattr(req.league_type, "value") else req.league_type
    scoring_fmt_str = req.scoring_format.value if hasattr(req.scoring_format, "value") else req.scoring_format
    if league_type_str == "dynasty":
        tiebreak_adp_attr = "adp_dynasty"
    elif scoring_fmt_str in ("ppr", "te_premium"):
        tiebreak_adp_attr = "adp_ppr"
    else:
        tiebreak_adp_attr = "adp_standard"

    # Cap selection. Two-pass:
    #   1. Per-position floor: every position gets at least league_size * 2 players
    #      (so every team can draft 2). This prevents K/DST starvation when their
    #      adjusted scores are dwarfed by RB/WR/QB projections.
    #   2. Fill remaining budget (cap - len(floor)) with the highest-scoring
    #      not-yet-selected players regardless of position.
    # If floor exceeds cap (e.g., short draft_rounds), floor wins — better to
    # include extras than to miss a position.
    POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
    overall_cap = req.league_size * req.draft_rounds
    per_position_min = req.league_size * 2

    by_position: dict[str, list[TieredPlayer]] = {p: [] for p in POSITIONS}
    for p in tiered:
        if p.position in by_position:
            by_position[p.position].append(p)
    for pos in by_position:
        by_position[pos].sort(key=lambda x: x.adjusted_score, reverse=True)

    # Floor: top per_position_min for each position
    guaranteed: list[TieredPlayer] = []
    for pos in POSITIONS:
        guaranteed.extend(by_position[pos][:per_position_min])

    # Fill remaining budget with highest-scoring not-already-selected players
    guaranteed_ids = {p.player_id for p in guaranteed}
    remaining_pool = sorted(
        (p for p in tiered if p.player_id not in guaranteed_ids),
        key=lambda p: p.adjusted_score,
        reverse=True,
    )
    remaining_budget = max(0, overall_cap - len(guaranteed))
    capped = guaranteed + remaining_pool[:remaining_budget]
    capped.sort(key=lambda p: p.adjusted_score, reverse=True)

    return assign_tiers(capped, league_size=req.league_size, tiebreak_adp_attr=tiebreak_adp_attr)


@router.post("/generate", response_model=GenerateResponse)
async def generate_tiers(req: GenerateRequest, db: AsyncSession = Depends(get_db)) -> GenerateResponse:
    ranked = await _run_generate(req, db)
    data_as_of = await _compute_data_as_of(db)
    return GenerateResponse(
        players=[TieredPlayerOut(**p.__dict__) for p in ranked],
        total=len(ranked),
        data_as_of=data_as_of,
    )


@router.post("/generate/csv", response_class=Response)
async def generate_csv(req: GenerateRequest, db: AsyncSession = Depends(get_db)) -> Response:
    tiered_players = await _run_generate(req, db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "overall_rank", "player", "position", "team", "age",
        "overall_tier", "positional_tier",
        "adjusted_score", "projected_score_raw", "prior_year_actual",
        "adp_standard", "adp_ppr", "adp_dynasty",
        "flags", "rules_applied",
    ])
    for p in tiered_players:
        writer.writerow([
            p.overall_rank, p.name, p.position, p.team, p.age,
            p.overall_tier, p.positional_tier,
            round(p.adjusted_score, 2), round(p.projected_score_raw, 2),
            round(p.prior_year_actual, 2) if p.prior_year_actual is not None else "",
            p.adp_standard or "", p.adp_ppr or "", p.adp_dynasty or "",
            ";".join(p.flags), ";".join(p.rules_applied),
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tiers.csv"'},
    )
