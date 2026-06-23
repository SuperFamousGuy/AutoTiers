import pytest
from app.integrations.scoring_mappers import sleeper_to_settings, espn_to_settings, cbs_to_settings, nfl_to_settings


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


def test_cbs_full_ppr_with_nested_value_dict():
    # CBS's /league/rules sub-key shape (per the cbs_to_settings docstring)
    # nests each stat's point value under {"value": ...}.
    raw = {"scoring": {"rec": {"value": "1.0"}, "passTD": {"value": "4"}}}
    s = cbs_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 4.0
    assert s["league_size"] == 12
    assert s["bonus_100yd_rushing"] is False
    assert s["bonus_100yd_receiving"] is False
    assert s["bonus_first_downs"] is False


def test_cbs_half_ppr_with_6_point_passing_td():
    raw = {"scoring": {"rec": {"value": "0.5"}, "passTD": {"value": "6"}}}
    s = cbs_to_settings(raw, league_size=10)
    assert s["scoring_format"] == "half_ppr"
    assert s["qb_td_points"] == 6.0


def test_cbs_standard_no_ppr():
    raw = {"scoring": {"rec": {"value": "0"}, "passTD": {"value": "4"}}}
    s = cbs_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "standard"


def test_cbs_accepts_bare_value_not_just_nested_dict():
    """Some CBS scoring entries may not be {"value": ...} wrapped — the
    mapper must tolerate a bare numeric/string value too."""
    raw = {"scoring": {"rec": "1.0", "passTD": "4"}}
    s = cbs_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 4.0


def test_cbs_missing_scoring_keys_falls_back_to_defaults():
    """Honest placeholder behaviour (matches ESPN/Yahoo): an empty or
    unrecognized scoring payload must not raise — it degrades to standard
    scoring and the documented 4.0 default QB TD value."""
    s = cbs_to_settings({}, league_size=12)
    assert s["scoring_format"] == "standard"
    assert s["qb_td_points"] == 4.0
    assert s["league_size"] == 12


def test_cbs_tolerates_unparseable_stat_value():
    """A non-numeric value for a recognized key must fall through to the
    next candidate key / default rather than raising ValueError."""
    raw = {"scoring": {"rec": {"value": "not-a-number"}, "passTD": {"value": "4"}}}
    s = cbs_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "standard"  # rec fell back to 0.0 default
    assert s["qb_td_points"] == 4.0


def test_cbs_tries_alternate_key_casings():
    """_CBS_RECEPTION_KEYS / _CBS_PASS_TD_KEYS try multiple plausible
    abbreviations since the real CBS key casing is unverified (see module
    docstring) — confirm the fallback-through-candidates behaviour works."""
    raw = {"scoring": {"REC": {"value": "1.0"}, "PassTD": {"value": "6"}}}
    s = cbs_to_settings(raw, league_size=12)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 6.0


def test_nfl_empty_scoring_emits_only_league_size():
    """NFL scoring is appKey-gated and not fetched (raw_scoring={}). The mapper
    must emit ONLY league_size and NO scoring keys, so _apply_settings' merge
    does not clobber the user's existing scoring (QA blocker fix)."""
    s = nfl_to_settings({}, league_size=14)
    assert s == {"league_size": 14}
    assert "scoring_format" not in s
    assert "qb_td_points" not in s


def test_nfl_honors_scoring_if_ever_populated():
    """If a future appKey-gated fetch populates raw_scoring, the same
    _classify_ppr path the other mappers use should honor it — proving wiring
    scoring in later is a fetch_league change, not a mapper rewrite."""
    s = nfl_to_settings({"rec": 1.0, "pass_td": 6}, league_size=10)
    assert s["scoring_format"] == "ppr"
    assert s["qb_td_points"] == 6.0


def test_nfl_tolerates_non_dict_raw_scoring():
    """Defensive: a non-dict raw_scoring degrades to league_size only, never raises."""
    s = nfl_to_settings(None, league_size=12)  # type: ignore[arg-type]
    assert s == {"league_size": 12}
