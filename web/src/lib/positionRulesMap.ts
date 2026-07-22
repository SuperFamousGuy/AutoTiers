export const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const;
export type Position = typeof POSITIONS[number];

// Authoritative mapping of which rule names appear under each position tab.
// Order within each array determines display order within a category group.
export const POSITION_RULES_MAP: Record<Position, readonly string[]> = {
  QB: [
    "New Team Penalty", "New Head Coach", "Sophomore Leap", "Bad Offense",
    "Follow the Money", "Injury History", "TD Regression",
    "Opportunity Over-Producer", "Opportunity Under-Producer",
    "Red Zone Usage Premium", "Projection Unavailable",
    "Year After the Year After", "Over the Hill", "Favorites",
  ],
  RB: [
    "RB Committee Penalty", "Target Share Premium", "Declining Snap%",
    "New Team Penalty", "New Head Coach", "Sophomore Leap",
    "Rookie RB Draft Capital", "Bad Offense",
    "Follow the Money", "Injury History", "TD Regression",
    "Opportunity Over-Producer", "Opportunity Under-Producer",
    "Red Zone Usage Premium", "Projection Unavailable",
    "Year After the Year After", "Over the Hill", "Favorites",
  ],
  WR: [
    "Target Share Premium", "Declining Snap%", "New Team Penalty",
    "New Head Coach", "Sophomore Leap", "Rookie WR Draft Capital",
    "Bad Offense", "Follow the Money",
    "Injury History", "TD Regression", "Opportunity Over-Producer",
    "Opportunity Under-Producer", "Red Zone Usage Premium",
    "Projection Unavailable", "Year After the Year After",
    "Over the Hill", "Favorites",
  ],
  TE: [
    "Target Share Premium", "Declining Snap%", "New Team Penalty",
    "New Head Coach", "TE Year-3 Leap", "Bad Offense", "Follow the Money",
    "Injury History", "TD Regression", "Opportunity Over-Producer",
    "Opportunity Under-Producer", "Red Zone Usage Premium",
    "Projection Unavailable", "Year After the Year After",
    "Over the Hill", "Favorites",
  ],
  K: [
    // Kicker-specific rules (backend positions=["K"]). Must include every
    // builtin K rule or RulesPanel silently drops it — see the guard test in
    // backend/tests/test_kicker_rules_allowlist.py.
    "Dome Kicker", "Mile High Kicker", "Cold-Weather Kicker",
    "Projection Unavailable", "Year After the Year After",
    "Over the Hill", "Favorites",
  ],
  DST: [
    "Projection Unavailable", "Favorites",
  ],
};
