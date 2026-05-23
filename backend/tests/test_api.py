import csv as csv_module
import io as io_module
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
    "weight_prior_year": 0.40,
    "weight_espn": 0.30,
    "weight_consensus": 0.30,
    "rules": [],
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
    rank1_score = by_rank[1]["adjusted_score"]
    assert all(rank1_score >= by_rank[r]["adjusted_score"] for r in [2, 3])


async def test_generate_empty_db_returns_empty(async_client):
    resp = await async_client.post("/api/generate", json=_GENERATE_BODY)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_generate_invalid_weights_returns_422(async_client):
    body = {**_GENERATE_BODY, "weight_prior_year": 0.5, "weight_espn": 0.5, "weight_consensus": 0.5}
    resp = await async_client.post("/api/generate", json=body)
    assert resp.status_code == 422


async def test_list_rules_returns_builtin_rules(async_client):
    resp = await async_client.get("/api/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 10
    assert all("name" in r and "conditions" in r for r in rules)


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
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 1.0,
        "weight_consensus": 0.0, "draft_rounds": 3, "rules": [],
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
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 1.0,
        "weight_consensus": 0.0, "draft_rounds": 15, "rules": [],
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
async def test_generate_validates_draft_rounds_range(async_client):
    """draft_rounds must be 1-30; values outside that range return 422."""
    base_payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.40, "weight_espn": 0.30,
        "weight_consensus": 0.30, "rules": [],
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
async def test_over_the_hill_position_aware_thresholds(async_client, test_db):
    """is_over_the_hill should be position-aware: 28 for RB, 30 for WR, 31 for TE, 36 for QB."""
    from app.models import Player, Projection
    from datetime import date

    cases = [
        # (id, position, age, expect_over_the_hill_applied)
        ("rb_27", "RB", 27, False),  # under threshold
        ("rb_28", "RB", 28, True),   # at threshold
        ("wr_29", "WR", 29, False),
        ("wr_30", "WR", 30, True),
        ("te_30", "TE", 30, False),
        ("te_31", "TE", 31, True),
        ("qb_35", "QB", 35, False),
        ("qb_36", "QB", 36, True),
        ("k_45",  "K",  45, False),  # K excluded — no threshold even at high age
        ("rb_no_age", "RB", None, False),  # missing age
    ]
    for pid, pos, age, _ in cases:
        test_db.add(Player(id=pid, name=pid, position=pos, team="DAL", age=age))
    await test_db.commit()
    for pid, _, _, _ in cases:
        test_db.add(Projection(
            player_id=pid, source="fantasypros", scoring_format="ppr",
            projected_points=100.0, last_updated=date.today(),
        ))
    await test_db.commit()

    payload = {
        "scoring_format": "ppr", "league_type": "standard", "league_size": 10,
        "qb_td_points": 4.0, "bonus_100yd_rushing": False, "bonus_100yd_receiving": False,
        "bonus_first_downs": False, "weight_prior_year": 0.0, "weight_espn": 0.0,
        "weight_consensus": 1.0, "draft_rounds": 15, "rules": [],
    }
    resp = await async_client.post("/api/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    by_id = {p["player_id"]: p for p in body["players"]}

    for pid, _, _, expected in cases:
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
        "weight_consensus": 1.0, "draft_rounds": 15, "rules": [],
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


async def test_generate_csv_returns_csv_file(async_client, test_db):
    await _seed(test_db)
    payload = {
        "scoring_format": "ppr",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
        "weight_prior_year": 0.40,
        "weight_espn": 0.30,
        "weight_consensus": 0.30,
        "rules": []
    }
    response = await async_client.post("/api/generate/csv", json=payload)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers.get("content-disposition", "")

    lines = response.text.strip().split("\n")
    assert len(lines) >= 2  # header + at least 1 data row
    header = lines[0].strip()
    assert "overall_rank" in header
    assert "player" in header
    assert "positional_tier" in header

    reader = csv_module.reader(io_module.StringIO(response.text))
    rows = list(reader)
    # 3 seeded players = 4 rows total (header + 3 data rows)
    assert len(rows) == 4
    data_row = rows[1]  # first data row (highest ranked player)
    assert data_row[0].isdigit()  # overall_rank is a number
    assert data_row[1] in {"Chase", "Henry", "Allen"}  # player name present
    assert data_row[2] in {"WR", "RB", "QB"}  # position present
