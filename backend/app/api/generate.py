import csv
import dataclasses
import io
import statistics
from datetime import date, datetime
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
from app.models import TeamSeason, PlayerContract, UserFavorites, User
from app.auth.dependencies import _get_current_user_impl
from app.engine.scoring import LeagueSettings, PlayerStats, calculate_fantasy_points, blend_scores, _score_receiving, _score_rushing, _score_tds_only
from app.engine.rules import Rule, RuleCondition, RuleEffect, PlayerContext, apply_rules
from app.engine.builtin_rules import BUILTIN_RULES, OVER_THE_HILL_AGE
from app.engine.xfp import (
    compute_league_averages,
    compute_per_position_sigmas,
    compute_opportunity_score_z,
    compute_xfp,
    _MIN_GAMES_PLAYED,
    _MIN_OPPORTUNITY_BY_POSITION,
)
from app.engine.tiers import TieredPlayer, assign_tiers
from app.schemas.generate import GenerateRequest, GenerateResponse, TieredPlayerOut, RuleApplicationOut
from app.data.matching import normalize_name

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
        description=schema.description,
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


def _avg_projection(projections: list[Projection], fmt: str) -> Optional[float]:
    """Average all projection sources for a player at the given scoring format.

    Returns the mean of all source projections that exist for this player and
    format. Each source counts equally. None if no projections exist.
    """
    values = [p.projected_points for p in projections if p.scoring_format == fmt]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _get_adp(adp_entries: list[ADPData], scoring_fmt: str, league_type: str = "redraft") -> Optional[float]:
    if league_type == "dynasty":
        adp_fmt = "dynasty"
    else:
        adp_fmt = scoring_fmt
    for a in adp_entries:
        if a.format == adp_fmt:
            return a.adp
    return None


async def _compute_bad_offense_teams(db: AsyncSession, current_year: int) -> set[str]:
    """Bottom-8 teams by 3-year average points scored.

    Requires at least 2 of 3 seasons of data per team; teams with fewer
    are excluded from ranking entirely.
    """
    cutoff = current_year - 3
    ts_rows = (await db.scalars(
        select(TeamSeason).where(TeamSeason.season >= cutoff)
    )).all()
    points_by_team: dict[str, list[int]] = {}
    for r in ts_rows:
        points_by_team.setdefault(r.team, []).append(r.points_scored)
    team_avg = {
        team: sum(pts) / len(pts)
        for team, pts in points_by_team.items()
        if len(pts) >= 2
    }
    sorted_teams = sorted(team_avg.items(), key=lambda kv: kv[1])
    return {team for team, _ in sorted_teams[:8]}


async def _compute_above_market_pids(
    db: AsyncSession, current_year: int, players: list[Player]
) -> set[str]:
    """Players whose cap hit exceeds 1.5× the median for their position.

    Only computes thresholds for positions with at least 5 contracts on file.
    """
    contract_rows = (await db.scalars(
        select(PlayerContract).where(PlayerContract.season == current_year)
    )).all()
    pid_to_caphit = {pc.player_id: pc.cap_hit for pc in contract_rows}
    pid_to_pos = {p.id: p.position for p in players}

    contracts_by_pos: dict[str, list[float]] = {}
    for pid, cap in pid_to_caphit.items():
        pos = pid_to_pos.get(pid)
        if pos in ("QB", "RB", "WR", "TE"):
            contracts_by_pos.setdefault(pos, []).append(cap)

    pos_threshold: dict[str, float] = {
        pos: statistics.median(caps) * 1.5
        for pos, caps in contracts_by_pos.items()
        if len(caps) >= 5
    }
    return {
        pid for pid, cap in pid_to_caphit.items()
        if (pos := pid_to_pos.get(pid)) in pos_threshold and cap > pos_threshold[pos]
    }


@dataclasses.dataclass
class _StatWithPosition:
    """Pairs a PlayerStat with its parent player's position, so xfp.* sees both.

    The xfp module reads `.position` plus the PlayerStat numeric attributes.
    The ORM PlayerStat itself doesn't carry the position (it's on the parent
    Player). __getattr__ delegates everything except `position` to the wrapped
    stat so xfp sees a uniform interface.
    """
    stat: object  # PlayerStat at runtime; using object to avoid forward-ref cycles
    position: str

    def __getattr__(self, name):
        return getattr(self.stat, name)


async def _run_generate(req: GenerateRequest, db: AsyncSession, current_user: Optional[User] = None) -> list[TieredPlayer]:
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

    keepers_normalized: set[str] = (
        {normalize_name(n) for n in req.keepers} if req.keepers else set()
    )

    current_year = datetime.utcnow().year
    bad_offense_teams = await _compute_bad_offense_teams(db, current_year)

    result = await db.execute(
        select(Player)
        .options(
            selectinload(Player.stats),
            selectinload(Player.projections),
            selectinload(Player.adp_entries),
        )
    )
    players = result.scalars().all()

    above_market_pids = await _compute_above_market_pids(db, current_year, players)

    # ---- Opportunity-score (xFP) pre-pass ----------------------------------
    # Compute per-position league averages of pts/target, pts/carry, pts/RZ
    # using the SAME settings that determine each player's actual FP. Then
    # compute per-position σ_gap from (FP - xFP) distributions. Both feed
    # into per-player z-scores below.
    prior_stats_with_pos = []
    for p in players:
        s = _get_stat(p.stats)
        if s is None:
            continue
        prior_stats_with_pos.append(_StatWithPosition(stat=s, position=p.position))

    league_avg = compute_league_averages(prior_stats_with_pos, settings)

    # Build (FP - xFP) gap distribution per position to derive σ.
    gaps_by_position: dict[str, list[float]] = {}
    for sp in prior_stats_with_pos:
        # Mirror the filters used in compute_league_averages and compute_opportunity_score_z
        # so the σ_gap distribution is built from the same population the z-score uses.
        # Without these, injury-truncated and zero-opportunity players inflate σ,
        # compressing z-scores toward zero and suppressing rule firings.
        if (sp.stat.games_played or 0) < _MIN_GAMES_PLAYED:
            continue
        opportunity = (sp.stat.targets or 0) + (sp.stat.rush_att or 0) + (sp.stat.red_zone_looks or 0)
        if opportunity < _MIN_OPPORTUNITY_BY_POSITION.get(sp.position, 50):
            continue
        xfp_val = compute_xfp(sp, league_avg)
        if xfp_val is None:
            continue
        ps_for_gap = PlayerStats(
            targets=sp.stat.targets or 0, receptions=sp.stat.receptions or 0,
            rec_yards=sp.stat.rec_yards or 0.0, rec_tds=sp.stat.rec_tds or 0,
            rush_att=sp.stat.rush_att or 0, rush_yards=sp.stat.rush_yards or 0.0,
            rush_tds=sp.stat.rush_tds or 0,
            pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
            games_played=sp.stat.games_played or 1,
        )
        fp = _score_receiving(ps_for_gap, settings) + _score_rushing(ps_for_gap, settings) + _score_tds_only(ps_for_gap, settings)
        gaps_by_position.setdefault(sp.position, []).append(fp - xfp_val)

    position_sigmas = compute_per_position_sigmas(gaps_by_position)
    # ------------------------------------------------------------------------

    # Server-side favorites lookup. Anonymous calls: empty sets, is_favorite
    # is None per player, the Favorites rule silently no-ops.
    favorite_pids_set: set[str] = set()
    favorite_teams_set: set[str] = set()
    if current_user is not None:
        fav_row = (await db.scalars(
            select(UserFavorites).where(UserFavorites.user_id == current_user.id)
        )).one_or_none()
        if fav_row is not None:
            favorite_pids_set = set(fav_row.favorite_player_ids or [])
            favorite_teams_set = set(fav_row.favorite_teams or [])
    has_any_favorites = bool(favorite_pids_set or favorite_teams_set)

    tiered: list[TieredPlayer] = []
    for player in players:
        if keepers_normalized and normalize_name(player.name) in keepers_normalized:
            continue
        stat = _get_stat(player.stats)
        avg_proj = _avg_projection(player.projections, scoring_fmt)
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

        league_type_val = req.league_type.value if hasattr(req.league_type, "value") else req.league_type
        player_adp = _get_adp(player.adp_entries, scoring_fmt, league_type_val)

        blended = blend_scores(
            prior_year_actual=prior_actual,
            espn_projection=None,
            consensus_projection=avg_proj,
            settings=settings,
        )

        projection_unavailable = avg_proj is None

        flags_list: list[str] = []
        if prior_actual is None and projection_unavailable:
            flags_list.append("Rookie — Limited Data")
        elif projection_unavailable:
            flags_list.append("Projection Unavailable")

        is_over_the_hill: Optional[bool] = None
        if player.age is not None and player.position in OVER_THE_HILL_AGE:
            is_over_the_hill = player.age >= OVER_THE_HILL_AGE[player.position]

        prior_touches: Optional[int] = None
        if player.position == "RB" and stat is not None:
            prior_touches = (stat.rush_att or 0) + (stat.receptions or 0)

        bad_offense_team: Optional[bool] = None
        if player.position in ("QB", "RB", "WR", "TE"):
            bad_offense_team = player.team in bad_offense_teams

        above_market_contract: Optional[bool] = None
        if player.position in ("QB", "RB", "WR", "TE"):
            above_market_contract = player.id in above_market_pids

        injured_two_years_ago: Optional[bool] = None
        if player.position in ("RB", "WR"):
            two_seasons_ago = datetime.utcnow().year - 2
            two_yrs_ago_stat = next(
                (s for s in player.stats if s.season == two_seasons_ago),
                None,
            )
            if two_yrs_ago_stat is not None:
                injured_two_years_ago = (two_yrs_ago_stat.games_played or 0) < 12

        opportunity_score_z: Optional[float] = None
        if stat is not None:
            sp_for_z = _StatWithPosition(stat=stat, position=player.position)
            opportunity_score_z = compute_opportunity_score_z(sp_for_z, league_avg, position_sigmas, settings)

        if has_any_favorites:
            is_favorite = (
                player.id in favorite_pids_set
                or (player.team is not None and player.team in favorite_teams_set)
            )
        else:
            is_favorite = None

        ctx = PlayerContext(
            player_id=player.id,
            position=player.position,
            age=player.age,
            snap_pct=stat.snap_pct if stat else None,
            carry_share=stat.carry_share if stat else None,
            target_share=stat.target_share if stat else None,
            games_played=stat.games_played if stat else None,
            years_exp=player.years_exp or 0,
            adp=player_adp,
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
            is_over_the_hill=is_over_the_hill,
            projection_unavailable=projection_unavailable,
            prior_touches=prior_touches,
            injured_two_years_ago=injured_two_years_ago,
            bad_offense_team=bad_offense_team,
            above_market_contract=above_market_contract,
            opportunity_score_z=opportunity_score_z,
            is_favorite=is_favorite,
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
            avg_projection=avg_proj,
            espn_projection=espn_pts,
            fantasypros_projection=fp_pts,
            adp_standard=_get_adp(player.adp_entries, "standard"),
            adp_ppr=_get_adp(player.adp_entries, "ppr"),
            adp_dynasty=_get_adp(player.adp_entries, "dynasty"),
            flags=rule_result.flags,
            rules_applied=rule_result.rules_applied,
            rule_applications=rule_result.applications,
            overall_rank=0,
            overall_tier=0,
            positional_tier="",
        ))

    league_type_str = req.league_type.value if hasattr(req.league_type, "value") else req.league_type
    scoring_fmt_str = req.scoring_format.value if hasattr(req.scoring_format, "value") else req.scoring_format
    if league_type_str == "dynasty":
        tiebreak_adp_attr = "adp_dynasty"
    elif scoring_fmt_str == "ppr":
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
async def generate_tiers(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(_get_current_user_impl),
) -> GenerateResponse:
    ranked = await _run_generate(req, db, current_user)
    data_as_of = await _compute_data_as_of(db)
    league_adp_normalized: dict[str, float] = (
        {normalize_name(k): v for k, v in req.league_adp.items()} if req.league_adp else {}
    )
    return GenerateResponse(
        players=[
            TieredPlayerOut(
                **{k: v for k, v in p.__dict__.items() if k != "rule_applications"},
                rule_applications=[RuleApplicationOut(**a.__dict__) for a in p.rule_applications],
                league_adp=league_adp_normalized.get(normalize_name(p.name)),
            )
            for p in ranked
        ],
        total=len(ranked),
        data_as_of=data_as_of,
    )


@router.post("/generate/csv", response_class=Response)
async def generate_csv(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(_get_current_user_impl),
) -> Response:
    tiered_players = await _run_generate(req, db, current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "overall_rank", "player", "position", "team", "age",
        "overall_tier", "positional_tier",
        "adjusted_score", "vbd_score", "position_replacement",
        "projected_score_raw",
        "prior_year_actual", "espn_projection", "fantasypros_projection", "avg_projection",
        "adp_standard", "adp_ppr", "adp_dynasty",
        "flags", "rules_applied", "rule_deltas",
    ])
    for p in tiered_players:
        # Format per-rule deltas as "name: ±X.X; name: ±X.X"
        rule_deltas_str = "; ".join(
            f"{app.name}: {'flagged' if app.effect_type.value == 'flag' else f'{app.delta:+.1f}'}"
            for app in p.rule_applications
        )
        writer.writerow([
            p.overall_rank, p.name, p.position, p.team, p.age,
            p.overall_tier, p.positional_tier,
            round(p.adjusted_score, 2), round(p.vbd_score, 2), round(p.position_replacement, 2),
            round(p.projected_score_raw, 2),
            round(p.prior_year_actual, 2) if p.prior_year_actual is not None else "",
            round(p.espn_projection, 2) if p.espn_projection is not None else "",
            round(p.fantasypros_projection, 2) if p.fantasypros_projection is not None else "",
            round(p.avg_projection, 2) if p.avg_projection is not None else "",
            p.adp_standard or "", p.adp_ppr or "", p.adp_dynasty or "",
            ";".join(p.flags), ";".join(p.rules_applied), rule_deltas_str,
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tiers.csv"'},
    )
