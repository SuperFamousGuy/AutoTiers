import csv as csv_module
import io as io_module
import pytest
from datetime import date
from app.models.player import Player, PlayerStat
from app.models.projection import Projection


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
    assert len(rules) >= 15
    assert all("name" in r and "conditions" in r for r in rules)


async def test_data_status_returns_dict(async_client, test_db):
    resp = await async_client.get("/api/data/status")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


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
