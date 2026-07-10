import asyncio
import dataclasses
import logging
import statistics
import time
from datetime import datetime
from typing import Optional, Protocol, Sequence
from fastapi import APIRouter, Depends
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
from app.engine.rules import Rule, PlayerContext, apply_rules
from app.engine.builtin_rules import BUILTIN_RULES, compute_is_over_the_hill
from app.engine.xfp import (
    compute_league_averages,
    compute_per_position_sigmas,
    compute_opportunity_score_z,
    compute_xfp,
    _MIN_GAMES_PLAYED,
    _MIN_OPPORTUNITY_BY_POSITION,
)
from app.engine.tiers import TieredPlayer, assign_tiers, compute_vbd_scores
from app.schemas.generate import GenerateRequest, GenerateResponse, TieredPlayerOut, RuleApplicationOut
from app.data.matching import normalize_name
from app.data.teams import DOME_TEAMS, ELEVATION_TEAM, COLD_WEATHER_TEAMS
from app.data.status import RETIRED_SOURCES

router = APIRouter()

logger = logging.getLogger(__name__)


async def _compute_data_as_of(db: AsyncSession) -> Optional[str]:
    """Return ISO date of the oldest successful source refresh, or None if no source has succeeded.

    Retired sources (#402) are excluded. ``purge_retired_status()`` normally
    deletes their rows on the first post-retirement refresh, but a multi-day
    scheduler outage spanning a retirement (see ``freshness.py``) can leave a
    stale row behind whose old ``last_updated`` would win the ``min()`` and make
    the banner report a date from a source no longer feeding any projection (#579).
    """
    from app.models import DataSourceStatus
    rows = (await db.scalars(
        select(DataSourceStatus).where(
            DataSourceStatus.last_updated.is_not(None),
            DataSourceStatus.source.not_in(RETIRED_SOURCES),
        )
    )).all()
    if not rows:
        return None
    oldest = min(r.last_updated for r in rows)
    return oldest.date().isoformat()


async def _compute_never_succeeded(db: AsyncSession) -> list[str]:
    """Return sorted source names that have been attempted but never succeeded.

    A ``DataSourceStatus`` row with ``last_attempted`` set and ``last_updated``
    still NULL means the scheduler has run for that source but every attempt has
    failed since day one (broken credentials, a changed endpoint, …). Such a
    source contributes nothing to ``blend_scores``/``_avg_projection`` yet is
    silently dropped from the ``_compute_data_as_of`` ``min()``, so the banner
    reports a fresh date from only the working sources. Surfacing these sources
    separately lets the frontend warn ("CBS projections have never loaded")
    instead of showing a falsely-clean banner (#547).

    Retired sources (#402) are excluded: their rows are purged on refresh, and a
    lingering one should read as noise, not a live failure.
    """
    from app.models import DataSourceStatus
    rows = (await db.scalars(
        select(DataSourceStatus.source).where(
            DataSourceStatus.last_attempted.is_not(None),
            DataSourceStatus.last_updated.is_(None),
            DataSourceStatus.source.not_in(RETIRED_SOURCES),
        )
    )).all()
    return sorted(rows)


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
        te_premium_bonus=req.te_premium_bonus,
    )


def _build_rules_for_position(position: str, req: "GenerateRequest") -> list[Rule]:
    """Return the full BUILTIN_RULES list with per-position overrides applied.

    For each built-in rule, apply the client's enabled/weight for this position
    if an override exists. Otherwise use the built-in default. The built-in
    `positions` field on each Rule is preserved unchanged — the engine's
    position gate still applies.

    Unknown rule names in the override are silently ignored (they simply won't
    match any built-in and the built-in defaults are used for all rules).
    Unknown position strings return built-in defaults (no crash).
    """
    override_map = {o.name: o for o in req.rules.get(position, [])}
    result: list[Rule] = []
    for builtin in BUILTIN_RULES:
        o = override_map.get(builtin.name)
        if o is not None:
            result.append(dataclasses.replace(builtin, enabled=o.enabled, weight=o.weight))
        else:
            result.append(builtin)
    return result


def _get_stat(stats: list[PlayerStat], season: int) -> Optional[PlayerStat]:
    """Return the stat row for exactly ``season``, or ``None``.

    Deliberately does NOT fall back to an older season. ``NflDataFetcher``
    retains up to three prior seasons and never deletes rows
    (``data/sources/nfl_data.py``), so a player who missed last season (injury,
    retirement, out of the league) still has an older row on file. Returning
    that stale row would feed a full ~16-game workload into ``blend_scores``'s
    prior-year games ramp (``engine/scoring.py``), hiding the missed season and
    blending a 2-3-year-old season in at full prior-year weight — the exact case
    the ramp exists to catch (#608). Callers pass ``current_year - 1`` so the
    "prior year" everywhere in generate means genuinely last season.
    """
    for s in stats:
        if s.season == season:
            return s
    return None


def _get_projection(projections: list[Projection], source: str, fmt: str) -> Optional[float]:
    for p in projections:
        if p.source == source and p.scoring_format == fmt:
            return p.projected_points
    return None


# The "espn" source is blended separately via ``weight_espn`` (#502), so it must
# be excluded from the consensus average to keep the two weight budgets over
# genuinely independent, non-overlapping source pools. Including it here would
# double-count ESPN once the source is re-enabled: once as its own weighted term
# and again folded into the consensus mean (#538).
_CONSENSUS_EXCLUDED_SOURCES = frozenset({"espn"})


def _avg_projection(projections: list[Projection], fmt: str) -> Optional[float]:
    """Average the consensus projection sources for a player at the given format.

    Returns the mean of all source projections that exist for this player and
    format, EXCLUDING sources that are blended separately (currently "espn",
    which has its own ``weight_espn`` term — see ``_CONSENSUS_EXCLUDED_SOURCES``).
    Each remaining source counts equally. None if no consensus projections exist.
    """
    values = [
        p.projected_points
        for p in projections
        if p.scoring_format == fmt and p.source not in _CONSENSUS_EXCLUDED_SOURCES
    ]
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


class _HasIdAndPosition(Protocol):
    """Minimal structural type ``_compute_above_market_pids`` needs.

    It only reads ``.id`` and ``.position``, so it accepts either an ORM
    ``Player`` or a session-free ``_PlayerSnapshot`` (#577).
    """
    id: str
    position: str


async def _compute_above_market_pids(
    db: AsyncSession, current_year: int, players: Sequence[_HasIdAndPosition]
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


# ---- Plain snapshots handed to the CPU-bound worker thread (#577) -----------
# The tiering computation runs off the event loop via ``asyncio.to_thread``.
# A worker thread must NOT touch the ORM session (accessing an unloaded attr
# would trigger lazy I/O against the async connection from the wrong thread and
# crash). So every field the computation reads is copied into these frozen,
# session-free structures while we are still on the event loop. Attribute names
# mirror the ORM models so the existing pure helpers (`_get_stat`,
# `_get_projection`, `_avg_projection`, `_get_adp`, the `xfp.*` functions, and
# `_StatWithPosition`) operate on snapshots unchanged.


@dataclasses.dataclass(frozen=True)
class _StatSnapshot:
    season: int
    games_played: Optional[int]
    targets: Optional[int]
    receptions: Optional[int]
    rec_yards: Optional[float]
    rec_tds: Optional[int]
    rush_att: Optional[int]
    rush_yards: Optional[float]
    rush_tds: Optional[int]
    pass_att: Optional[int]
    pass_yards: Optional[float]
    pass_tds: Optional[int]
    interceptions: Optional[int]
    snap_pct: Optional[float]
    carry_share: Optional[float]
    target_share: Optional[float]
    actual_tds: Optional[int]
    expected_tds: Optional[float]
    red_zone_looks: Optional[int]


@dataclasses.dataclass(frozen=True)
class _ProjSnapshot:
    source: str
    scoring_format: str
    projected_points: float


@dataclasses.dataclass(frozen=True)
class _AdpSnapshot:
    format: str
    adp: float


@dataclasses.dataclass(frozen=True)
class _PlayerSnapshot:
    id: str
    name: str
    position: str
    team: Optional[str]
    age: Optional[int]
    years_exp: Optional[int]
    # Immutable sequences so the frozen snapshot is thread-safe by construction:
    # a worker thread can't mutate them in-place (shallow-freeze gap, #577).
    stats: tuple[_StatSnapshot, ...]
    projections: tuple[_ProjSnapshot, ...]
    adp_entries: tuple[_AdpSnapshot, ...]


def _snapshot_stat(s: PlayerStat) -> _StatSnapshot:
    return _StatSnapshot(
        season=s.season,
        games_played=s.games_played,
        targets=s.targets,
        receptions=s.receptions,
        rec_yards=s.rec_yards,
        rec_tds=s.rec_tds,
        rush_att=s.rush_att,
        rush_yards=s.rush_yards,
        rush_tds=s.rush_tds,
        pass_att=s.pass_att,
        pass_yards=s.pass_yards,
        pass_tds=s.pass_tds,
        interceptions=s.interceptions,
        snap_pct=s.snap_pct,
        carry_share=s.carry_share,
        target_share=s.target_share,
        actual_tds=s.actual_tds,
        expected_tds=s.expected_tds,
        red_zone_looks=s.red_zone_looks,
    )


def _snapshot_player(p: Player) -> _PlayerSnapshot:
    """Copy the eager-loaded ORM player (and its stats/projections/adp) into a
    plain, session-free snapshot the worker thread can safely read (#577)."""
    return _PlayerSnapshot(
        id=p.id,
        name=p.name,
        position=p.position,
        team=p.team,
        age=p.age,
        years_exp=p.years_exp,
        stats=tuple(_snapshot_stat(s) for s in p.stats),
        projections=tuple(
            _ProjSnapshot(pr.source, pr.scoring_format, pr.projected_points)
            for pr in p.projections
        ),
        adp_entries=tuple(_AdpSnapshot(a.format, a.adp) for a in p.adp_entries),
    )


async def _run_generate(req: GenerateRequest, db: AsyncSession, current_user: Optional[User] = None) -> list[TieredPlayer]:
    settings = _build_league_settings(req)
    scoring_fmt = req.scoring_format.value

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
    # Copy the ORM rows into plain snapshots *now*, on the event loop, so the
    # CPU-bound tiering below can run in a worker thread without ever touching
    # the async session (#577).
    players = [_snapshot_player(p) for p in result.scalars().all()]

    above_market_pids = await _compute_above_market_pids(db, current_year, players)

    # Server-side favorites lookup. Anonymous calls: empty sets, is_favorite
    # is None per player, the Favorites rule silently no-ops. Done here (on the
    # event loop) so the worker thread below needs no DB access.
    favorite_pids_set: set[str] = set()
    favorite_teams_set: set[str] = set()
    if current_user is not None:
        fav_row = (await db.scalars(
            select(UserFavorites).where(UserFavorites.user_id == current_user.id)
        )).one_or_none()
        if fav_row is not None:
            favorite_pids_set = set(fav_row.favorite_player_ids or [])
            favorite_teams_set = set(fav_row.favorite_teams or [])

    # All DB I/O is done. Hand the pure-Python CPU work (per-player scoring +
    # rules + VBD + Jenks clustering) to a worker thread so it stops blocking
    # the single event loop that also serves other /generate requests,
    # /api/data/health, and the in-process scheduler callbacks (#577). The
    # request-level timing log makes any regression in this cost visible before
    # it becomes an incident.
    t0 = time.perf_counter()
    ranked = await asyncio.to_thread(
        _compute_ranked_players,
        players,
        settings=settings,
        req=req,
        scoring_fmt=scoring_fmt,
        keepers_normalized=keepers_normalized,
        bad_offense_teams=bad_offense_teams,
        above_market_pids=above_market_pids,
        favorite_pids_set=favorite_pids_set,
        favorite_teams_set=favorite_teams_set,
        current_year=current_year,
    )
    logger.info(
        "generate: tiered %d/%d players off-loop in %.1fms",
        len(ranked), len(players), (time.perf_counter() - t0) * 1000,
    )
    return ranked


def _compute_ranked_players(
    players: list[_PlayerSnapshot],
    *,
    settings: LeagueSettings,
    req: GenerateRequest,
    scoring_fmt: str,
    keepers_normalized: set[str],
    bad_offense_teams: set[str],
    above_market_pids: set[str],
    favorite_pids_set: set[str],
    favorite_teams_set: set[str],
    current_year: int,
) -> list[TieredPlayer]:
    """Pure-Python tiering: per-player scoring/rules + VBD + Jenks clustering.

    No DB access and no ``await`` — this runs on a worker thread via
    ``asyncio.to_thread`` (#577) and reads only the plain snapshots and
    pre-fetched sets passed in, never the ORM session. Keeping it a standalone
    sync function (rather than a closure) makes it directly unit-testable and
    keeps the event-loop/worker boundary explicit.
    """
    # ---- Opportunity-score (xFP) pre-pass ----------------------------------
    # Compute per-position league averages of pts/target, pts/carry, pts/RZ
    # using the SAME settings that determine each player's actual FP. Then
    # compute per-position σ_gap from (FP - xFP) distributions. Both feed
    # into per-player z-scores below.
    prior_season = current_year - 1
    prior_stats_with_pos = []
    for p in players:
        s = _get_stat(p.stats, prior_season)
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
        fp = _score_receiving(ps_for_gap, settings, sp.position) + _score_rushing(ps_for_gap, settings) + _score_tds_only(ps_for_gap, settings)
        gaps_by_position.setdefault(sp.position, []).append(fp - xfp_val)

    position_sigmas = compute_per_position_sigmas(gaps_by_position)
    # ------------------------------------------------------------------------

    # ``favorite_pids_set`` / ``favorite_teams_set`` were resolved on the event
    # loop (see ``_run_generate``) and passed in — no DB access from this thread.
    has_any_favorites = bool(favorite_pids_set or favorite_teams_set)

    # Pre-compute per-position rule lists once before the player loop.
    # _build_rules_for_position is O(len(BUILTIN_RULES)) per call; calling it
    # per player would rebuild the same override_map for every player of the
    # same position. With up to 6 distinct positions in a player pool, this
    # reduces total rule-list builds from O(players) to O(positions).
    position_rules_cache: dict[str, list[Rule]] = {
        pos: _build_rules_for_position(pos, req)
        for pos in {p.position for p in players}
    }

    tiered: list[TieredPlayer] = []
    for player in players:
        if keepers_normalized and normalize_name(player.name) in keepers_normalized:
            continue
        stat = _get_stat(player.stats, prior_season)
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

        # Pass the ESPN projection (if any) through to the blend so weight_espn
        # is not a validated-but-inert field (#502). espn_pts is None in
        # production today because EspnFetcher is intentionally not invoked
        # (see sources/fetcher.py), making this a no-op — but if the "espn"
        # source is ever re-enabled the schema, response field, and blend math
        # stay in agreement instead of silently absorbing weight_espn into the
        # prior_year/consensus ratio.
        blended = blend_scores(
            prior_year_actual=prior_actual,
            espn_projection=espn_pts,
            consensus_projection=avg_proj,
            settings=settings,
            prior_year_games=(stat.games_played if stat is not None else None),
            full_season_games=req.full_season_games,
            ramp_shape=req.prior_year_ramp,
        )

        projection_unavailable = avg_proj is None

        flags_list: list[str] = []
        if prior_actual is None and projection_unavailable:
            flags_list.append("Rookie — Limited Data")
        elif projection_unavailable:
            flags_list.append("Projection Unavailable")

        # Prior-season rush attempts — the shared rushing-volume field. For QBs
        # it drives the mobile-vs-pocket "Over the Hill" age cliff (#576); a QB
        # with no prior stat row stays None and is classified as a pocket passer.
        prior_rush_att: Optional[int] = stat.rush_att if stat is not None else None

        is_over_the_hill = compute_is_over_the_hill(
            player.position, player.age, prior_rush_att
        )

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
        if player.position in ("QB", "RB", "WR", "TE", "K"):
            two_seasons_ago = current_year - 2
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
            is_favorite_player = player.id in favorite_pids_set
            is_favorite_team = player.team is not None and player.team in favorite_teams_set
        else:
            is_favorite_player = None
            is_favorite_team = None

        # Double-gate invariant (DOME_TEAMS / ELEVATION_TEAM / COLD_WEATHER_TEAMS):
        # these context fields are *intentionally* only populated for position "K".
        # Every non-K player reaches the rules engine with None here, and
        # `_evaluate` short-circuits to False on a None field (engine/rules.py).
        # That is the second gate, and it is *independent* of each kicker rule's
        # own `positions=["K"]` gate. The two together are the "double gate":
        # the rule-level gate (apply_rules) and this context-level gate.
        # Note the /generate rules payload canNOT defeat the rule-level gate:
        # `_build_rules_for_position` only overrides `enabled`/`weight` and
        # preserves each rule's `positions`, so a client cannot re-point
        # "Dome Kicker"/"Mile High Kicker" at, say, "WR". The value of this
        # context gate is defense-in-depth: if the rule-level `positions=["K"]`
        # gate were ever removed or relaxed *in code*, the bonus still could not
        # leak to non-kickers, because their context field stays None here.
        # WARNING: if these fields are ever backfilled for non-K players, that
        # second gate disappears and the rule-level position gate becomes the
        # *only* defense — keep the `if player.position == "K"` guards (or add an
        # explicit position lock) before doing so.
        plays_in_dome: Optional[bool] = None
        if player.position == "K":
            plays_in_dome = player.team in DOME_TEAMS

        is_denver_kicker: Optional[bool] = None
        if player.position == "K":
            is_denver_kicker = player.team == ELEVATION_TEAM

        cold_weather_kicker: Optional[bool] = None
        if player.position == "K":
            cold_weather_kicker = player.team in COLD_WEATHER_TEAMS

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
            prior_rush_att=prior_rush_att,
            injured_two_years_ago=injured_two_years_ago,
            bad_offense_team=bad_offense_team,
            above_market_contract=above_market_contract,
            opportunity_score_z=opportunity_score_z,
            is_favorite=is_favorite_player or is_favorite_team,
            plays_in_dome=plays_in_dome,
            is_denver_kicker=is_denver_kicker,
            cold_weather_kicker=cold_weather_kicker,
        )

        rules_for_player = position_rules_cache[player.position]
        rule_result = apply_rules(blended, ctx, rules_for_player)
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
            is_favorite_player=is_favorite_player,
            is_favorite_team=is_favorite_team,
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

    overall_tier_count = req.overall_tier_count if req.overall_tier_count is not None else req.league_size
    return _cap_and_assign_tiers(
        tiered,
        league_size=req.league_size,
        draft_rounds=req.draft_rounds,
        tiebreak_adp_attr=tiebreak_adp_attr,
        overall_tier_count=overall_tier_count,
        qb_starters=req.qb_starters,
    )


def _cap_and_assign_tiers(
    tiered: list[TieredPlayer],
    *,
    league_size: int,
    draft_rounds: int,
    tiebreak_adp_attr: str,
    overall_tier_count: int,
    qb_starters: int,
) -> list[TieredPlayer]:
    """Trim ``tiered`` to a draftable roster, then tier and rank that roster.

    Cap selection. Two-pass:
      1. Per-position floor: every position gets at least league_size * 2 players
         (so every team can draft 2). This prevents K/DST starvation when their
         adjusted scores are dwarfed by RB/WR/QB projections.
      2. Fill remaining budget (cap - len(floor)) with the highest-VBD
         not-yet-selected players regardless of position.
    If floor exceeds cap (e.g., short draft_rounds), floor wins — better to
    include extras than to miss a position.

    The cross-position "remaining budget" fill ranks on vbd_score, not raw
    adjusted_score: raw point totals are not comparable across positions (QB
    totals run structurally higher), so a raw-score fill over-includes marginal
    QBs and under-includes draftable RB/WR/TE depth. VBD (replacement-adjusted
    score) is the metric built for exactly this cross-position comparison. We
    compute it on the *full* pre-cap ``tiered`` pool below and reuse it inside
    ``assign_tiers`` (``compute_vbd=False``) rather than letting it recompute on
    the narrower capped pool. Within a single position vbd_score is a constant
    offset from adjusted_score, so the per-position floor ordering is unchanged.
    See #557.

    The cap is display-only: it decides which players are returned, NOT which
    players anchor the VBD replacement baseline. Because VBD is computed on the
    full, un-capped ``tiered`` pool before the cap is applied, each position's
    replacement level is anchored on the position's true Nth-ranked player rather
    than the worst survivor of the cap. Without this, a short ``draft_rounds``
    (where the floor alone exceeds the overall cap, e.g. league_size=12,
    draft_rounds<=12) starves RB/WR groups below their 2.5x replacement rank and
    silently inflates the replacement baseline (issue #540).
    """
    # Compute VBD on the full pre-cap pool so (a) the cross-position cap fill can
    # rank by replacement-adjusted value (#557) and (b) the replacement baseline
    # anchors on each position's true Nth-ranked player, not the worst cap
    # survivor (#540). assign_tiers is then called with compute_vbd=False so it
    # does not recompute on the narrower capped pool.
    compute_vbd_scores(tiered, league_size, qb_starters)

    POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
    overall_cap = league_size * draft_rounds
    per_position_min = league_size * 2

    by_position: dict[str, list[TieredPlayer]] = {p: [] for p in POSITIONS}
    for p in tiered:
        if p.position in by_position:
            by_position[p.position].append(p)
    for pos in by_position:
        by_position[pos].sort(key=lambda x: x.vbd_score, reverse=True)

    # Floor: top per_position_min for each position
    guaranteed: list[TieredPlayer] = []
    for pos in POSITIONS:
        guaranteed.extend(by_position[pos][:per_position_min])

    # Fill remaining budget with highest-VBD not-already-selected players
    guaranteed_ids = {p.player_id for p in guaranteed}
    remaining_pool = sorted(
        (p for p in tiered if p.player_id not in guaranteed_ids),
        key=lambda p: p.vbd_score,
        reverse=True,
    )
    remaining_budget = max(0, overall_cap - len(guaranteed))
    capped = guaranteed + remaining_pool[:remaining_budget]
    capped.sort(key=lambda p: p.vbd_score, reverse=True)

    return assign_tiers(
        capped,
        league_size=league_size,
        tiebreak_adp_attr=tiebreak_adp_attr,
        overall_tier_count=overall_tier_count,
        qb_starters=qb_starters,
        compute_vbd=False,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_tiers(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(_get_current_user_impl),
) -> GenerateResponse:
    ranked = await _run_generate(req, db, current_user)
    data_as_of = await _compute_data_as_of(db)
    never_succeeded = await _compute_never_succeeded(db)
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
        never_succeeded=never_succeeded,
    )
