"""Tests for favorites Pydantic schemas + the canonical 32-team set."""
import pytest
from pydantic import ValidationError

from app.schemas.favorites import FavoritesUpdate, FavoritesOut
from app.data.teams import NFL_TEAMS, is_valid_team


def test_canonical_teams_is_32():
    assert len(NFL_TEAMS) == 32


def test_canonical_teams_contains_known_codes():
    for code in ["KC", "BUF", "NYJ", "PHI", "DAL", "GB", "SEA"]:
        assert code in NFL_TEAMS, f"{code} should be in NFL_TEAMS"


def test_is_valid_team_accepts_canonical():
    assert is_valid_team("KC")


def test_is_valid_team_rejects_unknown():
    assert not is_valid_team("XYZ")


def test_is_valid_team_rejects_empty():
    assert not is_valid_team("")


def test_favorites_update_accepts_empty():
    """Default state: both lists empty."""
    f = FavoritesUpdate()
    assert f.favorite_player_ids == []
    assert f.favorite_teams == []


def test_favorites_update_accepts_populated():
    f = FavoritesUpdate(favorite_player_ids=["4046"], favorite_teams=["KC"])
    assert f.favorite_player_ids == ["4046"]
    assert f.favorite_teams == ["KC"]


def test_favorites_update_rejects_non_list_ids():
    with pytest.raises(ValidationError):
        FavoritesUpdate(favorite_player_ids="4046")  # string, not list


def test_favorites_out_from_attributes():
    """FavoritesOut must support ORM-attribute construction."""
    class _Stub:
        favorite_player_ids = ["4046"]
        favorite_teams = ["KC"]
    f = FavoritesOut.model_validate(_Stub())
    assert f.favorite_player_ids == ["4046"]
    assert f.favorite_teams == ["KC"]
