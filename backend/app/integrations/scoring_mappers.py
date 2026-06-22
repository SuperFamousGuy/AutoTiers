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


# Yahoo stat IDs — verified against Yahoo Fantasy API v2 settings response.
# Update these if a real league response shows different IDs.
_YAHOO_PASSING_TD = "5"
_YAHOO_RECEPTIONS = "11"


def yahoo_to_settings(raw_scoring: dict, league_size: int) -> dict:
    """Map Yahoo stat_modifiers.stats payload to AutoTiers settings fields.

    raw_scoring is the value of fantasy_content.league[1].settings.stat_modifiers.stats
    i.e. a dict with key "stat" containing a list of {"stat_id": str, "value": str}.
    """
    stats = {item["stat_id"]: float(item.get("value") or 0) for item in raw_scoring.get("stat", [])}
    rec = stats.get(_YAHOO_RECEPTIONS, 0.0)
    pass_td = stats.get(_YAHOO_PASSING_TD, 4.0)
    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
    }


# CBS stat-key names — UNVERIFIED against a live /league/rules payload (no
# Engineer access to a real CBS account during implementation; the FFMWR
# reference implementation reads roster/schedule/transactions sub-keys of
# /league/rules but never the per-stat point-value scoring sub-key, so it
# gave no example to confirm against). These are the most plausible
# abbreviations based on CBS's public scoring-rules page categories
# ("Passing" -> passTD, "Receiving" -> rec). cbs_to_settings degrades to the
# qb_td_points/rec defaults below (same honest-placeholder pattern as ESPN's
# fallback) if a key isn't found, rather than raising. Update these constants
# once a real CBS /league/rules response is available — see Implementation
# Report "token-reusability/CBS field names" escalation.
_CBS_RECEPTION_KEYS = ("rec", "REC", "Rec")
_CBS_PASS_TD_KEYS = ("passTD", "PassTD", "pass_td")


def cbs_to_settings(raw_scoring: dict, league_size: int) -> dict:
    """Map CBS /league/rules payload to AutoTiers settings fields.

    raw_scoring is the "rules" body of GET /league/rules — expected to expose
    a "scoring" sub-key whose entries are keyed by stat abbreviation with a
    nested {"value": ...} the same way /league/rules exposes other settings
    (e.g. num_playoff_teams, add_drop_faab_starting_budget per the FFMWR
    reference). Falls back to 4.0 QB TD points / standard (non-PPR) scoring
    when the expected keys aren't present, mirroring ESPN/Sleeper's defaults.
    """
    scoring = raw_scoring.get("scoring") or {}

    def _stat_value(keys: tuple[str, ...], default: float) -> float:
        for key in keys:
            entry = scoring.get(key)
            if entry is None:
                continue
            if isinstance(entry, dict):
                value = entry.get("value")
            else:
                value = entry
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return default

    rec = _stat_value(_CBS_RECEPTION_KEYS, 0.0)
    pass_td = _stat_value(_CBS_PASS_TD_KEYS, 4.0)

    return {
        "scoring_format": _classify_ppr(rec),
        "league_size": league_size,
        "qb_td_points": pass_td,
        # CBS's /league/rules sub-keys for yardage/first-down bonuses are not
        # confirmed (same caveat ESPN and Yahoo carry today) — honest
        # placeholder until verified against a live league.
        "bonus_100yd_rushing": False,
        "bonus_100yd_receiving": False,
        "bonus_first_downs": False,
    }
