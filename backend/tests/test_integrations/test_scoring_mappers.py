import pytest
from app.integrations.scoring_mappers import sleeper_to_settings, espn_to_settings


def test_sleeper_full_ppr_with_4_qb_td_no_bonuses():
    raw = {"rec": 1.0, "pass_td": 4, "rush_yd": 0.1, "rec_yd": 0.1}
    s = sleeper_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 4
    assert s["bonus_100yd_rushing"] is False
    assert s["bonus_100yd_receiving"] is False
    assert s["bonus_first_downs"] is False
    assert s["league_size"] == 12


def test_sleeper_half_ppr_with_6_qb_td_and_yardage_bonuses():
    raw = {"rec": 0.5, "pass_td": 6, "bonus_rec_yd_100": 3.0, "bonus_rush_yd_100": 3.0}
    s = sleeper_to_settings(raw, league_size=10)
    assert s["scoring_format"] == "half_ppr"
    assert s["qb_td_points"] == 6
    assert s["bonus_100yd_rushing"] is True
    assert s["bonus_100yd_receiving"] is True


def test_sleeper_standard_no_ppr():
    raw = {"rec": 0.0, "pass_td": 4}
    s = sleeper_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "standard"


def test_sleeper_first_down_bonuses_detected():
    raw = {"rec": 1.0, "pass_td": 4, "bonus_rec_fd": 0.5}
    s = sleeper_to_settings(raw, league_size=12)
    assert s["bonus_first_downs"] is True


def test_espn_full_ppr_via_stat_id_53():
    # ESPN stat 53 = receptions (full PPR when value=1.0).
    raw = {"scoringItems": [{"statId": 53, "points": 1.0}, {"statId": 4, "points": 4.0}]}
    # statId 4 = pass TD.
    s = espn_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 4


def test_espn_half_ppr_with_6_qb_td():
    raw = {"scoringItems": [{"statId": 53, "points": 0.5}, {"statId": 4, "points": 6.0}]}
    s = espn_to_settings(raw, league_size=10)
    assert s["scoring_format"] == "half_ppr"
    assert s["qb_td_points"] == 6


def test_espn_standard():
    raw = {"scoringItems": [{"statId": 4, "points": 4.0}]}
    s = espn_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "standard"
