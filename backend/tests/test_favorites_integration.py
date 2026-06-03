"""End-to-end: a favorited player gets the Favorites rule applied during generate."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.scoring import ScoringFormat, LeagueType
from app.api.generate import _run_generate
from app.models.player import Player, PlayerStat
from app.models.projection import Projection


async def _signup(async_client, email: str = "intg@example.com") -> None:
    await async_client.post("/api/auth/signup", json={
        "email": email, "password": "password-long-enough",
    })


async def _seed_two_wrs(test_db: AsyncSession) -> None:
    for pid, name, team in [("FAV", "Saquon Barkley", "PHI"), ("UNFAV", "Other Guy", "PHI")]:
        test_db.add(Player(id=pid, name=name, position="WR", team=team, age=26, years_exp=4))
        test_db.add(PlayerStat(
            player_id=pid, season=2024,
            targets=80, receptions=50, rec_yards=600.0, rec_tds=4,
            rush_att=0, rush_yards=0.0, rush_tds=0,
            pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
            snaps=900, snap_pct=0.8, target_share=0.20,
            games_played=16, red_zone_looks=10,
        ))
        test_db.add(Projection(
            player_id=pid, source="fantasypros",
            scoring_format="ppr", projected_points=180.0,
        ))
    await test_db.commit()


@pytest.mark.asyncio
async def test_favorited_player_gets_rule_applied_in_generate(async_client, test_db):
    await _signup(async_client)
    await _seed_two_wrs(test_db)

    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": ["FAV"], "favorite_teams": [],
    })
    assert r.status_code == 200

    r = await async_client.post("/api/generate", json={
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False, "bonus_100yd_receiving": False, "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        "rules": [{"name": "Favorites", "enabled": True, "weight": 1.0,
                      "conditions": [{"field": "is_favorite", "operator": "==", "value": True}],
                      "effect": {"type": "multiplier", "value": 1.05}}],
        "keepers": [],
    })
    assert r.status_code == 200, r.text
    by_id = {p["player_id"]: p for p in r.json()["players"]}
    assert "Favorites" in by_id["FAV"]["rules_applied"]
    assert "Favorites" not in by_id["UNFAV"]["rules_applied"]
    assert by_id["FAV"]["adjusted_score"] > by_id["UNFAV"]["adjusted_score"]


@pytest.mark.asyncio
async def test_favorite_team_boosts_all_team_players(async_client, test_db):
    await _signup(async_client, email="team@example.com")
    await _seed_two_wrs(test_db)

    r = await async_client.put("/api/favorites", json={
        "favorite_player_ids": [], "favorite_teams": ["PHI"],
    })
    assert r.status_code == 200

    r = await async_client.post("/api/generate", json={
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False, "bonus_100yd_receiving": False, "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        "rules": [{"name": "Favorites", "enabled": True, "weight": 1.0,
                      "conditions": [{"field": "is_favorite", "operator": "==", "value": True}],
                      "effect": {"type": "multiplier", "value": 1.05}}],
        "keepers": [],
    })
    by_id = {p["player_id"]: p for p in r.json()["players"]}
    assert "Favorites" in by_id["FAV"]["rules_applied"]
    assert "Favorites" in by_id["UNFAV"]["rules_applied"]


@pytest.mark.asyncio
async def test_anonymous_generate_does_not_apply_favorites(async_client, test_db):
    """Anon generate must not crash and must not fire the Favorites rule."""
    await _seed_two_wrs(test_db)
    r = await async_client.post("/api/generate", json={
        "scoring_format": "ppr", "league_type": "standard", "league_size": 12,
        "qb_td_points": 4.0,
        "bonus_100yd_rushing": False, "bonus_100yd_receiving": False, "bonus_first_downs": False,
        "weight_prior_year": 0.0, "weight_espn": 0.0, "weight_consensus": 1.0,
        "rules": [{"name": "Favorites", "enabled": True, "weight": 1.0,
                      "conditions": [{"field": "is_favorite", "operator": "==", "value": True}],
                      "effect": {"type": "multiplier", "value": 1.05}}],
        "keepers": [],
    })
    assert r.status_code == 200, r.text
    for p in r.json()["players"]:
        assert "Favorites" not in p["rules_applied"]
