"""Provider-specific scoring → AutoTiers SettingsState shape.

Both mappers return a plain dict matching the frontend `SettingsState` keys.
We don't construct the full SettingsState (which lives in the frontend) —
we return the JSON-serializable subset that gets written into
`profile.settings_json`.
"""


def _classify_ppr(rec_value: float) -> str:
    if rec_value >= 0.75:
        return "ppr"
    if rec_value >= 0.25:
        return "half_ppr"
    return "standard"


def sleeper_to_settings(raw_scoring: dict, league_size: int) -> dict:
    rec = float(raw_scoring.get("rec", 0.0))
    pass_td = float(raw_scoring.get("pass_td", 4.0))
    bonus_rush = "bonus_rush_yd_100" in raw_scoring
    bonus_rec = "bonus_rec_yd_100" in raw_scoring
    # Any first-down bonus key (e.g. bonus_rec_fd, bonus_rush_fd) → True.
    bonus_fd = any(k.endswith("_fd") for k in raw_scoring.keys())
    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        "bonus_100yd_rushing": bonus_rush,
        "bonus_100yd_receiving": bonus_rec,
        "bonus_first_downs": bonus_fd,
        # weights stay user-controlled — mappers do not touch them.
    }


# Subset of ESPN statId mappings we actually consume.
_ESPN_RECEPTION = 53
_ESPN_PASS_TD = 4


def espn_to_settings(raw_scoring: dict, league_size: int) -> dict:
    items = raw_scoring.get("scoringItems") or []
    by_stat = {item.get("statId"): float(item.get("points") or 0) for item in items}

    rec = by_stat.get(_ESPN_RECEPTION, 0.0)
    pass_td = by_stat.get(_ESPN_PASS_TD, 4.0)

    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        # ESPN exposes yardage bonuses via separate stat ids we don't currently parse;
        # leaving them false matches what AutoTiers expects until a user reports a miss.
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
    }
