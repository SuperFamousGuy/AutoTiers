import pytest
from datetime import date, datetime
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.models import DataSourceStatus


async def _seed(db):
    players = [
        Player(id="wr1", name="Chase",     position="WR", team="CIN", age=25, years_exp=4),
        Player(id="rb1", name="Henry",     position="RB", team="TEN", age=30, years_exp=9),
        Player(id="qb1", name="Allen",     position="QB", team="BUF", age=28, years_exp=6),
    ]
    for p in players:
        db.add(p)

    stats = [
        PlayerStat(player_id="wr1", season=2025, receptions=100, rec_yards=1400.0, rec_tds=10,
                   targets=120, rush_att=0, rush_yards=0.0, rush_tds=0,
                   pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
                   games_played=17, carry_share=None, target_share=0.30,
                   snap_pct=0.95, red_zone_looks=12, actual_tds=10, expected_tds=9.0),
        PlayerStat(player_id="rb1", season=2025, rush_att=280, rush_yards=1600.0, rush_tds=16,
                   receptions=30, rec_yards=200.0, rec_tds=1, targets=40,
                   pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
                   games_played=17, carry_share=0.72, target_share=None,
                   snap_pct=0.70, red_zone_looks=25, actual_tds=17, expected_tds=14.0),
        PlayerStat(player_id="qb1", season=2025, pass_att=580, pass_yards=4300.0, pass_tds=36,
                   interceptions=6, rush_att=50, rush_yards=400.0, rush_tds=6,
                   receptions=0, rec_yards=0.0, rec_tds=0, targets=0,
                   games_played=17, carry_share=None, target_share=None,
                   snap_pct=1.0, red_zone_looks=0, actual_tds=42, expected_tds=None),
    ]
    for s in stats:
        db.add(s)

    projs = [
        Projection(player_id="wr1", source="espn",        scoring_format="ppr", projected_points=350.0, last_updated=date.today()),
        Projection(player_id="wr1", source="fantasypros",  scoring_format="ppr", projected_points=340.0, last_updated=date.today()),
        Projection(player_id="rb1", source="espn",        scoring_format="ppr", projected_points=330.0, last_updated=date.today()),
        Projection(player_id="rb1", source="fantasypros",  scoring_format="ppr", projected_points=320.0, last_updated=date.today()),
        Projection(player_id="qb1", source="espn",        scoring_format="ppr", projected_points=410.0, last_updated=date.today()),
        Projection(player_id="qb1", source="fantasypros",  scoring_format="ppr", projected_points=400.0, last_updated=date.today()),
    ]
    for proj in projs:
        db.add(proj)

    await db.commit()


_GENERATE_BODY = {
    "scoring_format": "ppr",
    "league_type": "standard",
    "league_size": 12,
    "qb_td_points": 4.0,
    "bonus_100yd_rushing": False,
    "bonus_100yd_receiving": False,
    "bonus_first_downs": False,
    "weight_prior_year": 0.30,
    "weight_espn": 0.0,
    "weight_consensus": 0.70,
    "rules": {},
}


async def test_health(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_generate_returns_all_players(async_client, test_db):
    await _seed(test_db)
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    ranks = sorted(p["overall_rank"] for p in data["players"])
    assert ranks == [1, 2, 3]


async def test_generate_rank_one_has_highest_score(async_client, test_db):
    await _seed(test_db)
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    by_rank = {p["overall_rank"]: p for p in resp.json()["players"]}
    # Ranking is by VBD (points above position replacement), not raw adjusted_score.
    rank1_score = by_rank[1]["vbd_score"]
    assert all(rank1_score >= by_rank[r]["vbd_score"] for r in [2, 3])


async def test_generate_empty_db_returns_empty(async_client):
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_generate_invalid_weights_returns_422(async_client):
    body = {**_GENERATE_BODY, "weight_prior_year": 0.5, "weight_espn": 0.5, "weight_consensus": 0.5}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 422


async def test_generate_negative_weight_returns_422(async_client):
    # Sums to 1.0 but a negative weight would silently drop that source under
    # the >0 active-set rule in blend_scores; the boundary must reject it.
    body = {**_GENERATE_BODY, "weight_prior_year": -0.2, "weight_espn": 0.0, "weight_consensus": 1.2}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 422


def test_370_touches_categorized_as_regression():
    from app.api.rules import _categorize
    assert _categorize("370 Touches") == "Regression"


def test_year_after_categorized_as_regression():
    from app.api.rules import _categorize
    assert _categorize("Year After the Year After") == "Regression"


def test_bad_offense_categorized_as_situation():
    from app.api.rules import _categorize
    assert _categorize("Bad Offense") == "Situation"


def test_follow_the_money_categorized_as_situation():
    from app.api.rules import _categorize
    assert _categorize("Follow the Money") == "Situation"


async def test_generate_computes_prior_touches_for_rbs(async_client, test_db):
    # Insert an RB with prior_touches >= 370 (rush_att + receptions)
    rb = Player(id="test-workhorse", name="Test Workhorse",
                position="RB", team="SF", age=26, years_exp=4)
    test_db.add(rb)
    test_db.add(PlayerStat(
        player_id=rb.id, season=2025,
        rush_att=300, receptions=80,
        rec_yards=600.0, rec_tds=4, rush_yards=1300.0, rush_tds=12,
        pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0, targets=95,
        games_played=17, carry_share=0.70, target_share=None,
        snap_pct=0.80, red_zone_looks=20, actual_tds=16, expected_tds=14.0,
    ))
    test_db.add(Projection(player_id=rb.id, source="espn",
                           scoring_format="ppr", projected_points=300.0, last_updated=date.today()))
    test_db.add(Projection(player_id=rb.id, source="fantasypros",
                           scoring_format="ppr", projected_points=290.0, last_updated=date.today()))
    await test_db.commit()

    body = {**_GENERATE_BODY, "rules": {"RB": [{"name": "370 Touches", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    players = resp.json()["players"]
    workhorse = next(p for p in players if p["player_id"] == "test-workhorse")
    assert "370 Touches" in workhorse["rules_applied"]


async def test_generate_computes_injured_two_years_ago_for_rb(async_client, test_db):
    current_year = datetime.utcnow().year
    two_yrs_ago = current_year - 2

    rb = Player(id="test-bounceback", name="Test Bounceback",
                position="RB", team="SF", age=26, years_exp=4)
    test_db.add(rb)
    test_db.add(PlayerStat(player_id=rb.id, season=two_yrs_ago, games_played=8))
    await test_db.commit()

    body = {**_GENERATE_BODY, "rules": {"RB": [{"name": "Year After the Year After", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    players = resp.json()["players"]
    bounceback = next(p for p in players if p["player_id"] == "test-bounceback")
    assert "Year After the Year After" in bounceback["rules_applied"]


@pytest.mark.asyncio
async def test_generate_flags_bad_offense_team(async_client, test_db):
    from app.models import Player, TeamSeason, Projection
    current_year = datetime.utcnow().year

    # 32 fake teams with descending points (lowest = worst).
    teams = [f"T{i:02d}" for i in range(32)]
    for season in (current_year - 1, current_year - 2, current_year - 3):
        for i, team in enumerate(teams):
            test_db.add(TeamSeason(team=team, season=season,
                                   points_scored=500 - i * 10))
    bad_team = teams[-1]
    good_team = teams[0]

    test_db.add(Player(id="bad-wr", name="Bad WR", position="WR", team=bad_team))
    test_db.add(Player(id="good-wr", name="Good WR", position="WR", team=good_team))
    await test_db.commit()
    # Add projections so both players survive cap/ranking.
    test_db.add(Projection(player_id="bad-wr", source="fantasypros",
                           scoring_format="ppr", projected_points=250.0,
                           last_updated=date.today()))
    test_db.add(Projection(player_id="good-wr", source="fantasypros",
                           scoring_format="ppr", projected_points=250.0,
                           last_updated=date.today()))
    await test_db.commit()

    body = {**_GENERATE_BODY, "rules": {"WR": [{"name": "Bad Offense", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    players = resp.json()["players"]
    bad = next(p for p in players if p["player_id"] == "bad-wr")
    good = next(p for p in players if p["player_id"] == "good-wr")
    assert "Bad Offense" in bad["rules_applied"]
    assert "Bad Offense" not in good["rules_applied"]


@pytest.mark.asyncio
async def test_generate_flags_above_market_contract(async_client, test_db):
    from app.models import Player, Projection, PlayerContract
    current_year = datetime.utcnow().year

    # Five WRs needed so the per-position threshold computes (len(caps) >= 5).
    # Cap hits: [5M, 10M, 20M, 30M, 35M] -> median = 20M, 1.5x = 30M
    # rich-wr at 35M is above-market; mid/low are not.
    wr_data = [
        ("rich-wr", "Rich WR", "SF", 35_000_000),
        ("hi-mid-wr", "Hi Mid WR", "GB", 30_000_000),
        ("mid-wr", "Mid WR", "KC", 20_000_000),
        ("lo-mid-wr", "Lo Mid WR", "LAR", 10_000_000),
        ("low-wr", "Low WR", "DAL", 5_000_000),
    ]
    for pid, name, team, cap in wr_data:
        test_db.add(Player(id=pid, name=name, position="WR", team=team))
    await test_db.commit()
    for pid, _, _, cap in wr_data:
        test_db.add(PlayerContract(
            player_id=pid, season=current_year, cap_hit=cap,
            last_updated=date.today(),
        ))
        test_db.add(Projection(
            player_id=pid, source="fantasypros", scoring_format="ppr",
            projected_points=250.0, last_updated=date.today(),
        ))
    await test_db.commit()

    body = {**_GENERATE_BODY, "rules": {"WR": [{"name": "Follow the Money", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    players = resp.json()["players"]
    rich = next(p for p in players if p["player_id"] == "rich-wr")
    mid = next(p for p in players if p["player_id"] == "mid-wr")
    assert "Follow the Money" in rich["rules_applied"]
    assert "Follow the Money" not in mid["rules_applied"]


@pytest.mark.asyncio
async def test_generate_excludes_teams_with_insufficient_data_from_bad_offense(async_client, test_db):
    """A team with <2 seasons of points data must be excluded from the bottom-8 ranking.

    Even if its one season of data would otherwise place it dead-last in scoring,
    it should NOT trigger Bad Offense for its players. Regression test for the
    `len(pts) >= 2` guard in _run_generate.
    """
    from app.models import Player, TeamSeason, Projection
    current_year = datetime.utcnow().year

    # 31 teams with all 3 seasons of data; their lowest-scoring 8 will form the
    # bottom-8 baseline.
    teams = [f"T{i:02d}" for i in range(31)]
    for season in (current_year - 1, current_year - 2, current_year - 3):
        for i, team in enumerate(teams):
            test_db.add(TeamSeason(team=team, season=season,
                                   points_scored=500 - i * 10))

    # 1 team with only ONE season of data, set to be dead last on points.
    # Without the guard, this team would be bottom-1. With the guard, excluded.
    insufficient_team = "T99"
    test_db.add(TeamSeason(team=insufficient_team, season=current_year - 1,
                           points_scored=0))

    test_db.add(Player(id="insufficient-wr", name="Insufficient WR",
                       position="WR", team=insufficient_team))
    await test_db.commit()
    test_db.add(Projection(player_id="insufficient-wr", source="fantasypros",
                           scoring_format="ppr", projected_points=250.0,
                           last_updated=date.today()))
    await test_db.commit()

    body = {**_GENERATE_BODY, "rules": {"WR": [{"name": "Bad Offense", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    players = resp.json()["players"]
    player = next(p for p in players if p["player_id"] == "insufficient-wr")
    assert "Bad Offense" not in player["rules_applied"], (
        "Team with <2 seasons of data must be excluded from the bottom-8 "
        "ranking, so its players must not receive the Bad Offense rule."
    )


async def test_list_rules_returns_builtin_rules(async_client):
    resp = await async_client.get("/api/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 10
    assert all("name" in r and "conditions" in r for r in rules)


async def test_list_rules_includes_descriptions(async_client):
    resp = await async_client.get("/api/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) > 0
    for r in rules:
        if r["is_builtin"]:
            assert r["description"], f"Built-in rule '{r['name']}' has no description in API response"


async def test_data_status_returns_dict(async_client, test_db):
    resp = await async_client.get("/api/data/status")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


@pytest.mark.asyncio
async def test_data_status_returns_per_source_dict(async_client, test_db):
    test_db.add(DataSourceStatus(
        source="sleeper",
        last_updated=datetime(2026, 5, 20, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=1500,
    ))
    test_db.add(DataSourceStatus(
        source="espn",
        last_updated=datetime(2026, 5, 19, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error="HTTP 503", rows_upserted=0,
    ))
    await test_db.commit()

    resp = await async_client.get("/api/data/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"sleeper", "espn"}
    assert body["sleeper"]["rows_upserted"] == 1500
    assert body["sleeper"]["last_error"] is None
    assert body["espn"]["last_error"] == "HTTP 503"
    assert body["espn"]["last_updated"].startswith("2026-05-19")


@pytest.mark.asyncio
async def test_generate_data_as_of_uses_minimum_last_updated(async_client, test_db):
    """data_as_of should reflect the oldest source's last successful update, not request time."""
    test_db.add(DataSourceStatus(
        source="sleeper",
        last_updated=datetime(2026, 5, 20, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=1500,
    ))
    test_db.add(DataSourceStatus(
        source="espn",
        last_updated=datetime(2026, 5, 15, 3, 0, 0),  # oldest
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=600,
    ))
    test_db.add(DataSourceStatus(
        source="fantasypros",
        last_updated=datetime(2026, 5, 18, 3, 0, 0),
        last_attempted=datetime(2026, 5, 18, 3, 0, 0),
        last_error=None, rows_upserted=580,
    ))
    await _seed(test_db)

    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_as_of"].startswith("2026-05-15")  # the espn last_updated
    # All sources succeeded -> nothing flagged as never-succeeded (#547).
    assert body["never_succeeded"] == []


@pytest.mark.asyncio
async def test_generate_surfaces_never_succeeded_source(async_client, test_db):
    """A source attempted but never once successful is surfaced distinctly (#547).

    data_as_of still reflects only the healthy sources; the dead source is not
    silently dropped but reported in never_succeeded so the frontend can warn.
    """
    test_db.add(DataSourceStatus(
        source="sleeper",
        last_updated=datetime(2026, 5, 20, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=1500,
    ))
    # Attempted every night but has NEVER succeeded: last_updated stays NULL.
    test_db.add(DataSourceStatus(
        source="cbs",
        last_updated=None,
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error="HTTP 401", rows_upserted=0,
    ))
    await _seed(test_db)

    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    body = resp.json()
    # data_as_of semantics unchanged: only the healthy source counts.
    assert body["data_as_of"].startswith("2026-05-20")
    assert body["never_succeeded"] == ["cbs"]


@pytest.mark.asyncio
async def test_compute_never_succeeded_flags_only_never_updated(test_db):
    """Unit: helper reports the never-succeeded source, ignoring healthy ones."""
    from app.api.generate import _compute_never_succeeded

    test_db.add(DataSourceStatus(
        source="espn",
        last_updated=datetime(2026, 5, 20, 3, 0, 0),
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error=None, rows_upserted=600,
    ))
    test_db.add(DataSourceStatus(
        source="cbs",
        last_updated=None,
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error="boom", rows_upserted=0,
    ))
    await test_db.commit()

    assert await _compute_never_succeeded(test_db) == ["cbs"]


@pytest.mark.asyncio
async def test_compute_never_succeeded_ignores_retired_sources(test_db):
    """Retired sources (#402) are not surfaced as live failures (#547)."""
    from app.api.generate import _compute_never_succeeded
    from app.data.status import RETIRED_SOURCES

    retired = RETIRED_SOURCES[0]
    test_db.add(DataSourceStatus(
        source=retired,
        last_updated=None,
        last_attempted=datetime(2026, 5, 20, 3, 0, 0),
        last_error="gone", rows_upserted=0,
    ))
    await test_db.commit()

    assert await _compute_never_succeeded(test_db) == []


@pytest.mark.asyncio
async def test_generate_caps_players_by_draft_rounds(async_client, test_db):
    """Generate response should be capped at league_size * draft_rounds."""
    from app.models import Player, Projection
    from datetime import date

    # Seed 50 players, all WRs for simplicity
    for i in range(50):
        test_db.add(Player(id=f"wr_{i}", name=f"Player {i}", position="WR", team="DAL"))
    await test_db.commit()
    # Add a projection per player so they're all rankable
    for i in range(50):
        test_db.add(Projection(
            player_id=f"wr_{i}", source="espn", scoring_format="ppr",
            projected_points=300.0 - i,  # descending scores
            last_updated=date.today(),
        ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 0.0,
        "weight_consensus": 1.0, "draft_rounds": 3, "rules": {},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # cap = 10 * 3 = 30. We seeded 50. Response should have 30.
    assert body["total"] == 30
    assert len(body["players"]) == 30
    # Top player should be the one with highest projection (Player 0)
    assert body["players"][0]["name"] == "Player 0"


@pytest.mark.asyncio
async def test_generate_guarantees_position_coverage(async_client, test_db):
    """Every position should have at least league_size * 2 players (when available)."""
    from app.models import Player, Projection
    from datetime import date

    # Seed: 200 WRs (huge pool, all high-scoring), 5 Kickers (small pool, low-scoring),
    # 30 QBs (medium pool, medium-scoring), 0 of everything else.
    # With a flat top-N cap, no Ks would make it because WRs would crowd them out.
    seed_data = (
        [(f"wr_{i}", "WR", 300.0 - i * 0.5) for i in range(200)]  # 200 WRs, 300→200 pts
        + [(f"k_{i}", "K", 150.0 - i) for i in range(5)]            # 5 Kickers, 150→146 pts
        + [(f"qb_{i}", "QB", 280.0 - i) for i in range(30)]         # 30 QBs, 280→250 pts
    )
    for pid, pos, _ in seed_data:
        test_db.add(Player(id=pid, name=pid, position=pos, team="DAL"))
    await test_db.commit()
    for pid, _, pts in seed_data:
        test_db.add(Projection(
            player_id=pid, source="espn", scoring_format="ppr",
            projected_points=pts, last_updated=date.today(),
        ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 0.0,
        "weight_consensus": 1.0, "draft_rounds": 15, "rules": {},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    # Floor: 10 * 2 = 20 per position. WRs available=200 → 20 floor. Ks available=5 → 5 floor (all of them). QBs available=30 → 20 floor.
    # Floor total = 20 WR + 5 K + 20 QB = 45.
    # Cap = 10 * 15 = 150. Remaining budget = 150 - 45 = 105.
    # Fill with highest unselected. WRs 21-200 (180 available) all beat the cap, but we only need 105 more.
    # Total = 45 + 105 = 150 players.
    assert body["total"] == 150

    positions = [p["position"] for p in body["players"]]
    assert positions.count("K") == 5, f"Expected all 5 Ks, got {positions.count('K')}"
    assert positions.count("QB") >= 20, f"Expected >=20 QBs, got {positions.count('QB')}"
    assert positions.count("WR") >= 20, f"Expected >=20 WRs, got {positions.count('WR')}"


@pytest.mark.asyncio
async def test_generate_cap_fill_ranks_remaining_budget_by_vbd_not_raw(async_client, test_db):
    """#557: the cross-position "remaining budget" fill must rank on VBD, not raw score.

    Synthetic pool: 30 QBs with structurally higher raw scores but *lower* VBD, and
    30 RBs with lower raw scores but *higher* VBD. Per-position floor takes the top 20
    of each (40 total); the remaining 10 cap slots are contested by QB21-30 vs RB21-30.

    On raw score the QBs win every remaining slot (they out-score every RB), so a
    raw-ranked fill would return 30 QB / 20 RB. On VBD the RBs win, because QB totals
    run structurally higher than replacement while these marginal RBs still sit near/above
    their replacement rank. The fix must therefore preferentially fill with the RBs.
    """
    from app.models import Player, Projection
    from datetime import date

    # QBs: raw 380 -> 351 (flat, high). QB replacement ~ QB7 (round(10*0.67)) => VBD < 0 for the tail.
    # RBs: raw 300 -> 242 (steeper). RB replacement ~ RB25 (round(10*2.5)) => tail VBD near 0, above the QBs'.
    seed_data = (
        [(f"qb_{i}", "QB", 380.0 - i) for i in range(30)]
        + [(f"rb_{i}", "RB", 300.0 - i * 2) for i in range(30)]
    )
    for pid, pos, _ in seed_data:
        test_db.add(Player(id=pid, name=pid, position=pos, team="DAL"))
    await test_db.commit()
    for pid, _, pts in seed_data:
        # weight_consensus=1.0 drives the scores below, so seed a consensus
        # source. "espn" is intentionally excluded from the consensus average
        # (it blends via its own weight_espn term — see _CONSENSUS_EXCLUDED_SOURCES
        # / #549), so an espn-only seed would score to nothing here and collapse
        # the VBD ordering this test exercises.
        test_db.add(Projection(
            player_id=pid, source="fantasypros", scoring_format="ppr",
            projected_points=pts, last_updated=date.today(),
        ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 0.0,
        "weight_consensus": 1.0, "draft_rounds": 5, "rules": {},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    # Floor = 10*2 = 20 per position => 20 QB + 20 RB = 40. Cap = 10*5 = 50 => 10 remaining slots.
    assert body["total"] == 50
    positions = [p["position"] for p in body["players"]]
    # Every raw QB out-scores every RB, so a raw-ranked fill would give the 10 slots to QBs
    # (30 QB / 20 RB). VBD gives them to the RBs instead.
    assert positions.count("RB") == 30, f"Expected 30 RBs (higher VBD), got {positions.count('RB')}"
    assert positions.count("QB") == 20, f"Expected 20 QBs (lower VBD), got {positions.count('QB')}"


@pytest.mark.asyncio
async def test_generate_validates_draft_rounds_range(async_client):
    """draft_rounds must be 1-30; values outside that range return 422."""
    base_payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.40, "weight_espn": 0.30,
        "weight_consensus": 0.30, "rules": {},
    }
    # Too low
    resp = await async_client.post("/api/generate", json={**base_payload, "draft_rounds": 0})
    assert resp.status_code == 422
    # Too high
    resp = await async_client.post("/api/generate", json={**base_payload, "draft_rounds": 50})
    assert resp.status_code == 422
    # Default (omit) should work
    resp = await async_client.post("/api/generate", json=base_payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_generate_validates_prior_year_games_knobs(async_client):
    """#315: full_season_games must be 1-17 and prior_year_ramp must be a known shape."""
    base_payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.40, "weight_espn": 0.30,
        "weight_consensus": 0.30, "rules": {},
    }
    # full_season_games out of range -> 422
    resp = await async_client.post("/api/generate", json={**base_payload, "full_season_games": 0})
    assert resp.status_code == 422
    resp = await async_client.post("/api/generate", json={**base_payload, "full_season_games": 18})
    assert resp.status_code == 422
    # Unknown ramp shape -> 422
    resp = await async_client.post("/api/generate", json={**base_payload, "prior_year_ramp": "exponential"})
    assert resp.status_code == 422
    # Valid overrides accepted
    resp = await async_client.post(
        "/api/generate",
        json={**base_payload, "full_season_games": 17, "prior_year_ramp": "steep"},
    )
    assert resp.status_code == 200
    # Defaults (omit both) still work -> behaviour unchanged when unset
    resp = await async_client.post("/api/generate", json=base_payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_generate_validates_te_premium_bonus(async_client):
    """#525: te_premium_bonus must be within [0.0, 2.0]; omitting it defaults to off."""
    base_payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.40, "weight_espn": 0.30,
        "weight_consensus": 0.30, "rules": {},
    }
    # Below range -> 422
    resp = await async_client.post("/api/generate", json={**base_payload, "te_premium_bonus": -0.5})
    assert resp.status_code == 422
    # Above range -> 422
    resp = await async_client.post("/api/generate", json={**base_payload, "te_premium_bonus": 2.5})
    assert resp.status_code == 422
    # In-range value accepted
    resp = await async_client.post("/api/generate", json={**base_payload, "te_premium_bonus": 1.0})
    assert resp.status_code == 200
    # Omitting it (default 0.0) still works
    resp = await async_client.post("/api/generate", json=base_payload)
    assert resp.status_code == 200


async def test_generate_prior_year_knobs_change_blended_score(async_client, test_db):
    """#315: full_season_games and prior_year_ramp must actually reach blend_scores.

    This is the wiring test — deleting the two kwargs from the generate call site
    must make it FAIL (the three requests would otherwise all return the default
    blend). Seeds an injury-shortened RB (4 games) whose high consensus projection
    dwarfs the low prior actual, so the discount has a visible effect.
    """
    rb = Player(id="test-injured-knob", name="Test Injured Knob",
                position="RB", team="SF", age=26, years_exp=4)
    test_db.add(rb)
    # PPR prior actual ~83 pts over only 4 games (rec 40 + rush 25 + 3 TDs * 6).
    test_db.add(PlayerStat(
        player_id=rb.id, season=2025,
        rush_att=50, receptions=20, rec_yards=200.0, rec_tds=1,
        rush_yards=250.0, rush_tds=2, pass_att=0, pass_yards=0.0,
        pass_tds=0, interceptions=0, targets=28, games_played=4,
    ))
    test_db.add(Projection(player_id=rb.id, source="fantasypros",
                           scoring_format="ppr", projected_points=280.0, last_updated=date.today()))
    await test_db.commit()

    async def _raw_score(**overrides) -> float:
        resp = await async_client.post("/api/generate", json={**_GENERATE_BODY, **overrides})
        assert resp.status_code == 200
        p = next(p for p in resp.json()["players"] if p["player_id"] == rb.id)
        return p["projected_score_raw"]

    default_linear = await _raw_score()                                   # F=14, linear
    steep = await _raw_score(prior_year_ramp="steep")                     # F=14, steep
    threshold_met = await _raw_score(full_season_games=4)                 # 4 games == full season -> no discount

    # No discount keeps the full (low) prior -> lowest blend. Linear discounts it,
    # steep discounts it harder -> each step moves toward projection-only (280).
    assert threshold_met < default_linear < steep < 280.0
    # Sanity-pin the steep value against the Mathematician's curve.
    assert steep == pytest.approx(273.3, abs=0.5)


@pytest.mark.asyncio
async def test_generate_validates_qb_starters(async_client):
    """qb_starters must be 1 (standard) or 2 (superflex/2-QB); else 422 (#319)."""
    base_payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.40, "weight_espn": 0.30,
        "weight_consensus": 0.30, "rules": {},
    }
    # Out of range
    resp = await async_client.post("/api/generate", json={**base_payload, "qb_starters": 0})
    assert resp.status_code == 422
    resp = await async_client.post("/api/generate", json={**base_payload, "qb_starters": 3})
    assert resp.status_code == 422
    # Superflex is accepted
    resp = await async_client.post("/api/generate", json={**base_payload, "qb_starters": 2})
    assert resp.status_code == 200
    # Default (omit) should work
    resp = await async_client.post("/api/generate", json=base_payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_over_the_hill_position_aware_thresholds(async_client, test_db):
    """is_over_the_hill is position-aware (RB 28, WR 31, TE 31, K 40) and, for QB,
    rushing-volume-conditioned: mobile QBs (60+ prior rush att) at 31, pocket at 38 (#576)."""
    from app.models import Player, Projection, PlayerStat
    from datetime import date

    cases = [
        # (id, position, age, prior_rush_att, expect_over_the_hill_applied)
        ("rb_27", "RB", 27, None, False),  # under threshold
        ("rb_28", "RB", 28, None, True),   # at threshold
        ("wr_29", "WR", 29, None, False),
        ("wr_30", "WR", 30, None, False),  # 30-yo WR no longer over the hill (threshold raised to 31)
        ("wr_31", "WR", 31, None, True),   # 31-yo WR is at the new threshold
        ("te_30", "TE", 30, None, False),
        ("te_31", "TE", 31, None, True),
        # QB pocket passers (low / no rushing volume) — cliff is now 38.
        ("qb_pocket_37", "QB", 37, 10, False),  # 37-yo pocket QB no longer triggers (was 36)
        ("qb_pocket_38", "QB", 38, 10, True),   # pocket QB at the new cliff
        ("qb_no_stat_36", "QB", 36, None, False),  # no prior stat row -> pocket -> 36 < 38
        # QB dual-threats (60+ prior rush att) — cliff drops to 31.
        ("qb_mobile_30", "QB", 30, 120, False),  # mobile just under cliff
        ("qb_mobile_32", "QB", 32, 120, True),   # 32-yo mobile QB NOW triggers (was 36)
        ("k_39",  "K",  39, None, False),  # K under threshold (threshold is 40)
        ("k_40",  "K",  40, None, True),   # K at threshold
        ("rb_no_age", "RB", None, None, False),  # missing age
    ]
    for pid, pos, age, _rush, _ in cases:
        test_db.add(Player(id=pid, name=pid, position=pos, team="DAL", age=age))
    await test_db.commit()
    for pid, _, _, rush, _ in cases:
        test_db.add(Projection(
            player_id=pid, source="fantasypros", scoring_format="ppr",
            projected_points=100.0, last_updated=date.today(),
        ))
        if rush is not None:
            test_db.add(PlayerStat(
                player_id=pid, season=date.today().year - 1, rush_att=rush,
                games_played=17,
            ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 0.0,
        "weight_consensus": 1.0, "draft_rounds": 15,
        "rules": {
            "RB": [{"name": "Over the Hill", "enabled": True, "weight": 1.0}],
            "WR": [{"name": "Over the Hill", "enabled": True, "weight": 1.0}],
            "TE": [{"name": "Over the Hill", "enabled": True, "weight": 1.0}],
            "QB": [{"name": "Over the Hill", "enabled": True, "weight": 1.0}],
            "K":  [{"name": "Over the Hill", "enabled": True, "weight": 1.0}],
        },
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    by_id = {p["player_id"]: p for p in body["players"]}

    for pid, _, _, _, expected in cases:
        if pid not in by_id:
            continue  # player may have been capped out — acceptable
        applied = "Over the Hill" in by_id[pid]["rules_applied"]
        assert applied == expected, f"{pid} (age {by_id[pid]['age']}): expected rule_applied={expected}, got {applied}"


@pytest.mark.asyncio
async def test_generate_response_includes_score_breakdown(async_client, test_db):
    """TieredPlayerOut includes espn_projection, fantasypros_projection, rule_applications."""
    from app.models import Player, Projection
    from datetime import date

    test_db.add(Player(id="wr_1", name="Test WR", position="WR", team="DAL", age=25))
    await test_db.commit()
    test_db.add(Projection(player_id="wr_1", source="fantasypros", scoring_format="ppr",
                           projected_points=300.0, last_updated=date.today()))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 0.0,
        "weight_consensus": 1.0, "draft_rounds": 15, "rules": {},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["players"]) >= 1
    p = body["players"][0]
    # New fields exist
    assert "espn_projection" in p
    assert "fantasypros_projection" in p
    assert "rule_applications" in p
    # fantasypros_projection should be the value we seeded
    assert p["fantasypros_projection"] == 300.0
    # No rules → empty applications
    assert p["rule_applications"] == []


@pytest.mark.asyncio
async def test_partial_data_player_does_not_outrank_complete_data_player(async_client, test_db):
    """Player with only prior_year (no projection) should rank below player with full data."""
    from app.models import Player, Projection
    from datetime import date

    # Partial-data player: prior_year only, no projections (like Winston)
    test_db.add(Player(id="winston", name="Backup QB", position="QB", team="NYG", age=32))
    # Complete-data player: prior_year + FP projection
    test_db.add(Player(id="star", name="Star QB", position="QB", team="BUF", age=28))
    await test_db.commit()

    # No projections for winston
    # Star has a strong FP projection
    test_db.add(Projection(
        player_id="star", source="fantasypros", scoring_format="ppr",
        projected_points=400.0, last_updated=date.today(),
    ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.20, "weight_espn": 0.0, "weight_consensus": 0.80, "draft_rounds": 15,
        "rules": {"QB": [{"name": "Projection Unavailable", "enabled": True, "weight": 1.0}]},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    star = next((p for p in body["players"] if p["player_id"] == "star"), None)
    winston = next((p for p in body["players"] if p["player_id"] == "winston"), None)

    assert star is not None
    assert winston is not None
    # Star has full data with strong FP; winston has no data at all.
    # Winston should have adjusted_score = 0 (no prior year either) * 0.5 (rule) = 0
    # Star should be 0 * 0.20 + 400 * 0.80 = 320 (no prior year for star but he has FP)
    assert star["adjusted_score"] > winston["adjusted_score"]
    assert star["overall_rank"] < winston["overall_rank"]
    # Winston should have the Projection Unavailable rule applied
    assert "Projection Unavailable" in winston["rules_applied"]


@pytest.mark.asyncio
async def test_vbd_top_rb_outranks_top_qb_in_standard(async_client, test_db):
    """End-to-end VBD: top RB ranks above top QB with higher raw points,
    because RB drop-off to replacement is steeper than QB drop-off."""
    from app.models import Player, Projection

    # 13 QBs (FP 400 → 280): replacement = QB12 = 290, top QB VBD = 110
    # 31 RBs (FP 300 → 75): replacement = RB30 (12*2.5=30) ≈ 82.5, top RB VBD ≈ 217.5
    for i in range(13):
        test_db.add(Player(id=f"qb_{i}", name=f"QB{i}", position="QB", team="DAL", age=27))
    for i in range(31):
        test_db.add(Player(id=f"rb_{i}", name=f"RB{i}", position="RB", team="DAL", age=27))
    await test_db.commit()
    for i in range(13):
        test_db.add(Projection(
            player_id=f"qb_{i}", source="fantasypros", scoring_format="ppr",
            projected_points=400.0 - i * 10, last_updated=date.today(),
        ))
    for i in range(31):
        test_db.add(Projection(
            player_id=f"rb_{i}", source="fantasypros", scoring_format="ppr",
            projected_points=300.0 - i * 7.5, last_updated=date.today(),
        ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0, "draft_rounds": 15, "rules": {},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    top = body["players"][0]
    assert top["player_id"] == "rb_0", (
        f"VBD failed: expected top RB at #1, got {top['name']} ({top['position']})"
    )


@pytest.mark.asyncio
async def test_overall_tier_count_fallback_uses_league_size(async_client, test_db):
    """When overall_tier_count is omitted, the fallback must be league_size, not draft_rounds.

    Sincerity proof: we send league_size=8 and draft_rounds=25. The set of
    overall_tier values in the response must be exactly {1..8} — i.e. 8 tiers.
    If the code regresses to using draft_rounds, we'd get up to 25 tiers and
    the assertion `tiers_present == set(range(1, 9))` would fail.
    """
    from app.models import Player, Projection

    # Seed enough WRs for assign_tiers to produce multiple overall tiers.
    # Using irrational step so VBD scores are all unique (avoids ties collapsing tiers).
    for i in range(40):
        test_db.add(Player(id=f"wr_{i}", name=f"WR{i}", position="WR", team="DAL", age=25))
    await test_db.commit()
    for i in range(40):
        test_db.add(Projection(
            player_id=f"wr_{i}", source="fantasypros", scoring_format="ppr",
            projected_points=round(400.0 - i * 3.71, 2), last_updated=date.today(),
        ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard",
        # league_size=8 so the fallback should produce 8 tiers, not 25.
        "league_size": 8,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        # draft_rounds intentionally differs so a regression to draft_rounds is detectable.
        "draft_rounds": 25,
        # overall_tier_count intentionally omitted — exercises the fallback path.
        "rules": {},
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    tiers_present = {p["overall_tier"] for p in body["players"]}
    # Fallback is league_size=8 → exactly tiers 1..8.
    # If fallback regresses to draft_rounds=25, more tiers would appear and this fails.
    assert tiers_present == set(range(1, 9)), (
        f"Expected overall tiers 1..8 (league_size fallback), got: {sorted(tiers_present)}"
    )


# ---------------------------------------------------------------------------
# Integration tests: kicker dome and elevation rule wiring
# Validates that generate.py correctly populates plays_in_dome and
# is_denver_kicker from player.team, not just that the rules engine
# evaluates them correctly (which is covered by test_rules.py).
# ---------------------------------------------------------------------------

async def _seed_kickers(db):
    """Seed three kickers: dome (MIN), Denver (DEN), and outdoor (BUF).

    Projections use "ppr" scoring_format to match _GENERATE_BODY so
    _avg_projection returns a non-None value for each player.
    """
    kickers = [
        Player(id="k_min", name="Dome Kicker", position="K", team="MIN", age=30, years_exp=5),
        Player(id="k_den", name="Denver Kicker", position="K", team="DEN", age=28, years_exp=3),
        Player(id="k_buf", name="Outdoor Kicker", position="K", team="BUF", age=32, years_exp=7),
    ]
    for k in kickers:
        db.add(k)
    projs = [
        Projection(player_id="k_min", source="fantasypros", scoring_format="ppr",
                   projected_points=140.0, last_updated=date.today()),
        Projection(player_id="k_den", source="fantasypros", scoring_format="ppr",
                   projected_points=145.0, last_updated=date.today()),
        Projection(player_id="k_buf", source="fantasypros", scoring_format="ppr",
                   projected_points=130.0, last_updated=date.today()),
    ]
    for proj in projs:
        db.add(proj)
    await db.commit()


async def test_dome_kicker_rule_fires_for_dome_team(async_client, test_db):
    """MIN kicker gets 'Dome Kicker' in rules_applied via player.team wiring."""
    await _seed_kickers(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Dome Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Dome Kicker" in by_id["k_min"]["rules_applied"]


async def test_dome_kicker_rule_does_not_fire_for_outdoor_team(async_client, test_db):
    """BUF kicker does NOT get 'Dome Kicker' — outdoor stadium."""
    await _seed_kickers(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Dome Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Dome Kicker" not in by_id["k_buf"]["rules_applied"]


async def test_mile_high_kicker_rule_fires_for_denver(async_client, test_db):
    """DEN kicker gets 'Mile High Kicker' in rules_applied via player.team wiring."""
    await _seed_kickers(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Mile High Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Mile High Kicker" in by_id["k_den"]["rules_applied"]


async def test_mile_high_kicker_rule_does_not_fire_for_non_denver(async_client, test_db):
    """MIN kicker does NOT get 'Mile High Kicker' — not Denver."""
    await _seed_kickers(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Mile High Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Mile High Kicker" not in by_id["k_min"]["rules_applied"]


async def test_denver_kicker_does_not_get_dome_bonus(async_client, test_db):
    """DEN is not in DOME_TEAMS; DEN kicker gets Mile High only, not Dome Kicker."""
    await _seed_kickers(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [
        {"name": "Dome Kicker", "enabled": True, "weight": 1.0},
        {"name": "Mile High Kicker", "enabled": True, "weight": 1.0},
    ]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Dome Kicker" not in by_id["k_den"]["rules_applied"]
    assert "Mile High Kicker" in by_id["k_den"]["rules_applied"]


# ---------------------------------------------------------------------------
# Double-gate invariant (#204): the kicker-context fields (plays_in_dome /
# is_denver_kicker / cold_weather_kicker) are only populated for position "K"
# in generate.py, so every non-K player reaches the engine with them as None
# and `_evaluate` short-circuits to False. That context-level gate is
# INDEPENDENT of each kicker rule's own positions=["K"] gate — the two
# together are the "double gate".
#
# These tests isolate the CONTEXT gate. Note the /generate payload cannot
# re-point a rule at a non-K position: `_build_rules_for_position` only
# overrides enabled/weight and preserves each rule's `positions`, so merely
# listing "Dome Kicker" under "WR" is still blocked by the rule-level
# positions=["K"] gate and would not exercise the context gate at all. To
# leave the context field as the ONLY remaining defense, each test monkeypatches
# the built-in rule to positions=None (disabling the rule-level gate) and then
# asserts the bonus still does not leak to a non-K player on a trigger team.
# (cold_weather_kicker has the same guarantee asserted below in
# test_cold_weather_kicker_not_set_for_non_k...)
# ---------------------------------------------------------------------------

def _patch_rule_positions_none(monkeypatch, rule_name):
    """Replace generate.py's BUILTIN_RULES with a copy where ``rule_name`` has
    positions=None, disabling that rule's position gate so the context-level
    gate (the field staying None for non-K players) is the only defense left."""
    import dataclasses
    import app.api.generate as generate_mod
    patched = [
        dataclasses.replace(r, positions=None) if r.name == rule_name else r
        for r in generate_mod.BUILTIN_RULES
    ]
    monkeypatch.setattr(generate_mod, "BUILTIN_RULES", patched)


async def _seed_non_k_on_kicker_teams(db):
    """Seed non-K players on a dome team (MIN) and on Denver (DEN).

    These are the teams that would trip "Dome Kicker" / "Mile High Kicker"
    if those rules ever fired for non-kickers.
    """
    players = [
        Player(id="wr_min", name="MIN WR", position="WR", team="MIN", age=26, years_exp=4),
        Player(id="rb_den", name="DEN RB", position="RB", team="DEN", age=25, years_exp=3),
    ]
    for p in players:
        db.add(p)
    projs = [
        Projection(player_id="wr_min", source="fantasypros", scoring_format="ppr",
                   projected_points=180.0, last_updated=date.today()),
        Projection(player_id="rb_den", source="fantasypros", scoring_format="ppr",
                   projected_points=190.0, last_updated=date.today()),
    ]
    for proj in projs:
        db.add(proj)
    await db.commit()


async def test_dome_kicker_not_set_for_non_k_on_dome_team(async_client, test_db, monkeypatch):
    """With "Dome Kicker"'s rule-level position gate disabled (positions=None),
    a WR on MIN (a dome team) still must NOT get the bonus: generate.py leaves
    plays_in_dome=None for non-kickers, so the context-level gate alone blocks
    it (#204 double-gate invariant)."""
    _patch_rule_positions_none(monkeypatch, "Dome Kicker")
    await _seed_non_k_on_kicker_teams(test_db)
    body = {**_GENERATE_BODY, "rules": {"WR": [{"name": "Dome Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Dome Kicker" not in by_id["wr_min"]["rules_applied"]


async def test_mile_high_kicker_not_set_for_non_k_on_denver(async_client, test_db, monkeypatch):
    """With "Mile High Kicker"'s rule-level position gate disabled
    (positions=None), an RB on DEN still must NOT get the bonus: generate.py
    leaves is_denver_kicker=None for non-kickers, so the context-level gate alone
    blocks it (#204 double-gate invariant)."""
    _patch_rule_positions_none(monkeypatch, "Mile High Kicker")
    await _seed_non_k_on_kicker_teams(test_db)
    body = {**_GENERATE_BODY, "rules": {"RB": [{"name": "Mile High Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Mile High Kicker" not in by_id["rb_den"]["rules_applied"]


# ---------------------------------------------------------------------------
# Integration tests: cold-weather kicker rule wiring
# Validates that generate.py correctly populates cold_weather_kicker from
# player.team, and that dome-team Ks and DEN Ks are excluded.
# ---------------------------------------------------------------------------

async def _seed_kickers_cold(db):
    """Seed four kickers for cold-weather wiring tests.

    GB  — K on a cold-weather team (should get cold_weather_kicker=True)
    DET — K on a dome team (should get cold_weather_kicker=False, not penalized)
    DEN — K on the elevation team (excluded from COLD_WEATHER_TEAMS; False)
    BUF — a WR (non-K) on a cold-weather team, to verify the position guard
          leaves cold_weather_kicker=None for non-kickers.
    """
    from app.models.player import Player
    from app.models.projection import Projection
    from datetime import date

    kickers = [
        Player(id="cwk_gb",  name="GB Kicker",   position="K",  team="GB",  age=29, years_exp=4),
        Player(id="cwk_det", name="DET Kicker",  position="K",  team="DET", age=31, years_exp=6),
        Player(id="cwk_den", name="DEN Kicker2", position="K",  team="DEN", age=27, years_exp=2),
        Player(id="cwk_wr",  name="BUF WR",      position="WR", team="BUF", age=25, years_exp=3),
    ]
    for k in kickers:
        db.add(k)
    projs = [
        Projection(player_id="cwk_gb",  source="fantasypros", scoring_format="ppr",
                   projected_points=135.0, last_updated=date.today()),
        Projection(player_id="cwk_det", source="fantasypros", scoring_format="ppr",
                   projected_points=138.0, last_updated=date.today()),
        Projection(player_id="cwk_den", source="fantasypros", scoring_format="ppr",
                   projected_points=142.0, last_updated=date.today()),
        Projection(player_id="cwk_wr",  source="fantasypros", scoring_format="ppr",
                   projected_points=120.0, last_updated=date.today()),
    ]
    for proj in projs:
        db.add(proj)
    await db.commit()


async def test_cold_weather_kicker_rule_fires_for_cold_weather_team(async_client, test_db):
    """GB kicker gets 'Cold-Weather Kicker' in rules_applied via player.team wiring."""
    await _seed_kickers_cold(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Cold-Weather Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Cold-Weather Kicker" in by_id["cwk_gb"]["rules_applied"]


async def test_cold_weather_kicker_rule_does_not_fire_for_dome_team(async_client, test_db):
    """DET kicker does NOT get 'Cold-Weather Kicker' — dome team excluded."""
    await _seed_kickers_cold(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Cold-Weather Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Cold-Weather Kicker" not in by_id["cwk_det"]["rules_applied"]


async def test_cold_weather_kicker_rule_does_not_fire_for_denver(async_client, test_db):
    """DEN kicker does NOT get 'Cold-Weather Kicker' — DEN excluded from COLD_WEATHER_TEAMS."""
    await _seed_kickers_cold(test_db)
    body = {**_GENERATE_BODY, "rules": {"K": [{"name": "Cold-Weather Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Cold-Weather Kicker" not in by_id["cwk_den"]["rules_applied"]


async def test_cold_weather_kicker_not_set_for_non_k_on_cold_weather_team(async_client, test_db):
    """A WR on BUF (a cold-weather team) must NOT get penalized: the generate.py
    wiring guard (`if player.position == "K"`) leaves cold_weather_kicker=None for
    non-kickers, so the rule never fires even when explicitly enabled for "WR"."""
    await _seed_kickers_cold(test_db)
    body = {**_GENERATE_BODY, "rules": {"WR": [{"name": "Cold-Weather Kicker", "enabled": True, "weight": 1.0}]}}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
    by_id = {p["player_id"]: p for p in resp.json()["players"]}
    assert "Cold-Weather Kicker" not in by_id["cwk_wr"]["rules_applied"]


# ---------------------------------------------------------------------------
# FIX 3 — Rule weight clamp via HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_rejects_rule_weight_above_2(async_client):
    """A rule override with weight=2.1 must return 422 Unprocessable Entity."""
    body = {
        **_GENERATE_BODY,
        "rules": {"WR": [{"name": "Sophomore Leap", "enabled": True, "weight": 2.1}]},
    }
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_rejects_rule_weight_below_0(async_client):
    """A rule override with weight=-0.5 must return 422 Unprocessable Entity."""
    body = {
        **_GENERATE_BODY,
        "rules": {"WR": [{"name": "Sophomore Leap", "enabled": True, "weight": -0.5}]},
    }
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_accepts_rule_weight_at_boundary(async_client, test_db):
    """A rule override with weight=2.0 (upper boundary) must pass validation and return 200."""
    await _seed(test_db)
    body = {
        **_GENERATE_BODY,
        "rules": {"WR": [{"name": "Sophomore Leap", "enabled": True, "weight": 2.0}]},
    }
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 200
