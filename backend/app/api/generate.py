import csv
import dataclasses
import io
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
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


def _get_adp(adp_entries: list[ADPData], fmt: str) -> Optional[float]:
    for a in adp_entries:
        if a.format == fmt:
            return a.adp
    return None


async def _run_generate(req: GenerateRequest, db: AsyncSession) -> list[TieredPlayer]:
    settings = _build_league_settings(req)
    scoring_fmt = req.scoring_format.value

    # Merge built-in + user-provided rules.
    # Use dataclasses.replace to avoid mutating the shared BUILTIN_RULES globals.
    builtin_by_name = {r.name: r for r in BUILTIN_RULES}
    rules: list[Rule] = []
    for schema in req.rules:
        if schema.name in builtin_by_name:
            br = builtin_by_name[schema.name]
            rules.append(dataclasses.replace(br, enabled=schema.enabled, weight=schema.weight))
        else:
            rules.append(_schema_to_rule(schema))
    # Add any built-in rules not mentioned by the user (with defaults)
    mentioned = {s.name for s in req.rules}
    for r in BUILTIN_RULES:
        if r.name not in mentioned:
            rules.append(r)

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

        ctx = PlayerContext(
            player_id=player.id,
            position=player.position,
            age=player.age or 0,
            snap_pct=stat.snap_pct if stat else None,
            carry_share=stat.carry_share if stat else None,
            target_share=stat.target_share if stat else None,
            games_played=stat.games_played if stat else None,
            years_exp=player.years_exp or 0,
            adp=_get_adp(player.adp_entries, scoring_fmt),
            projected_score=blended,
            new_team=False,
            new_coach=False,
            actual_tds=stat.actual_tds if stat else None,
            expected_tds=stat.expected_tds if stat else None,
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

    return assign_tiers(tiered)


@router.post("/generate", response_model=GenerateResponse)
async def generate_tiers(req: GenerateRequest, db: AsyncSession = Depends(get_db)) -> GenerateResponse:
    ranked = await _run_generate(req, db)
    today = str(date.today())
    return GenerateResponse(
        players=[TieredPlayerOut(**p.__dict__) for p in ranked],
        total=len(ranked),
        data_as_of=today,
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
