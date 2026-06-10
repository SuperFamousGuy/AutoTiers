from app.integrations.scoring_mappers import yahoo_to_settings


def test_yahoo_to_settings_ppr():
    raw = {
        "stat": [
            {"stat_id": "4", "value": "0.04"},   # passing yards
            {"stat_id": "5", "value": "4"},        # passing TDs
            {"stat_id": "9", "value": "0.1"},      # rushing yards
            {"stat_id": "10", "value": "6"},       # rushing TDs
            {"stat_id": "11", "value": "1"},       # receptions — PPR
            {"stat_id": "12", "value": "0.1"},     # receiving yards
            {"stat_id": "13", "value": "6"},       # receiving TDs
        ]
    }
    result = yahoo_to_settings(raw, league_size=12)
    assert result["scoring_format"] == "ppr"
    assert result["league_size"] == 12
    assert result["qb_td_points"] == 4


def test_yahoo_to_settings_half_ppr():
    raw = {
        "stat": [
            {"stat_id": "11", "value": "0.5"},
            {"stat_id": "5", "value": "4"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=10)
    assert result["scoring_format"] == "half_ppr"


def test_yahoo_to_settings_standard():
    raw = {
        "stat": [
            {"stat_id": "11", "value": "0"},
            {"stat_id": "5", "value": "4"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=8)
    assert result["scoring_format"] == "standard"


def test_yahoo_to_settings_six_point_passing_td():
    raw = {
        "stat": [
            {"stat_id": "5", "value": "6"},
            {"stat_id": "11", "value": "1"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=12)
    assert result["qb_td_points"] == 6


def test_yahoo_to_settings_missing_stats_defaults():
    result = yahoo_to_settings({"stat": []}, league_size=12)
    assert result["scoring_format"] == "standard"
    assert result["qb_td_points"] == 4
    assert result["league_size"] == 12
