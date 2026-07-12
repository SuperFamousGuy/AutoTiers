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


def test_yahoo_to_settings_single_stat_dict_not_list():
    # Yahoo's XML→JSON conversion collapses a single-stat league's "stat" from a
    # list into a bare dict. The mapper must read it, not crash iterating string
    # keys (the raw-500 bug this regression guards).
    raw = {"stat": {"stat_id": "11", "value": "1"}}
    result = yahoo_to_settings(raw, league_size=12)
    assert result["scoring_format"] == "ppr"
    assert result["league_size"] == 12


def test_yahoo_to_settings_item_missing_stat_id_degrades():
    # An item without "stat_id" is skipped rather than raising KeyError.
    raw = {
        "stat": [
            {"value": "1"},              # no stat_id — must be ignored
            {"stat_id": "5", "value": "6"},
        ]
    }
    result = yahoo_to_settings(raw, league_size=10)
    assert result["qb_td_points"] == 6
    # No reception stat survived, so scoring degrades to standard.
    assert result["scoring_format"] == "standard"


def test_yahoo_to_settings_non_numeric_value_degrades():
    # A non-numeric "value" is skipped instead of raising ValueError.
    raw = {"stat": [{"stat_id": "11", "value": "not-a-number"}]}
    result = yahoo_to_settings(raw, league_size=12)
    assert result["scoring_format"] == "standard"
    assert result["qb_td_points"] == 4


def test_yahoo_to_settings_non_dict_item_in_list_skipped():
    # A stray non-dict entry in the "stat" list (e.g. a bare string from a
    # malformed payload) is skipped rather than crashing on .get().
    raw = {"stat": ["garbage", {"stat_id": "11", "value": "1"}]}
    result = yahoo_to_settings(raw, league_size=12)
    assert result["scoring_format"] == "ppr"


def test_yahoo_to_settings_stat_missing_entirely_degrades():
    # A payload with no "stat" key at all (or a non-list, non-dict value) must
    # degrade to defaults, never raise.
    assert yahoo_to_settings({}, league_size=8)["scoring_format"] == "standard"
    assert yahoo_to_settings({"stat": None}, league_size=8)["qb_td_points"] == 4


def test_yahoo_to_settings_non_dict_raw_scoring_returns_defaults():
    # Upstream settings.get(...).get("stats", {}) can yield None (or another
    # non-dict) on a malformed payload; must degrade to defaults, not raise.
    for bad in (None, [], "stats", 7):
        result = yahoo_to_settings(bad, league_size=12)
        assert result["scoring_format"] == "standard"
        assert result["qb_td_points"] == 4.0
        assert result["league_size"] == 12
