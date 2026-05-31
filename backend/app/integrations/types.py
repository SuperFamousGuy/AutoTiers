"""Shared types for per-user-league provider integrations."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LeagueSummary:
    """Lightweight league info used to populate a selection dropdown."""
    id: str
    name: str
    season: int


@dataclass
class LeagueData:
    """Everything we fetch from a provider on connect/refresh.

    raw_scoring is a provider-native dict (Sleeper or ESPN's own keys) —
    scoring_mappers convert it to AutoTiers SettingsState shape.

    keepers is a list of {player_name, position, team}. adp_json is
    {player_name: avg_pick_overall} or None when the platform doesn't
    expose draft data for the league.
    """
    league_id: str
    name: str
    season: int
    raw_scoring: dict
    league_size: int
    keepers: list[dict] = field(default_factory=list)
    adp_json: Optional[dict] = None
