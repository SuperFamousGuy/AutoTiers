"""Server-side defaults mirrored from the frontend.

`DEFAULT_PROFILE_SETTINGS` is a server-side copy of the frontend's
`DEFAULT_SETTINGS` object in `web/src/App.tsx`. It exists so that OAuth
first-login callbacks — which, unlike email/password signup, never receive
the frontend's live `currentState` — can still seed a new user's "My setup"
profile with the same defaults the app itself starts from.

If you change `DEFAULT_SETTINGS` in `web/src/App.tsx`, update this to match
(and vice versa). The frontend re-hydrates settings from the profile it loads,
so a drift here only affects the very first render before the profile is
fetched — but keeping them in lockstep avoids a surprising snap-back.
"""
from typing import Any


# Mirror of web/src/App.tsx DEFAULT_SETTINGS. The nested defaults
# (te_premium_bonus, full_season_games, prior_year_ramp) mirror the
# DEFAULT_* constants exported from web/src/components/SettingsPanel.tsx.
DEFAULT_PROFILE_SETTINGS: dict[str, Any] = {
    "scoring_format": "standard",
    "league_size": 12,
    "draft_rounds": 15,
    "tier_count": 12,
    "qb_td_points": 4,
    "bonus_100yd_rushing": False,
    "bonus_100yd_receiving": False,
    "bonus_first_downs": False,
    "te_premium_bonus": 0,
    "weights": {"prior": 30, "consensus": 70},
    "full_season_games": 14,
    "prior_year_ramp": "linear",
}
