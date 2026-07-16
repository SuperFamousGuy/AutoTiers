export type ScoringFormat = "standard" | "half_ppr" | "ppr";
export type LeagueType = "standard" | "dynasty" | "keeper";
export type LeagueSize = 8 | 10 | 12 | 14 | 16;
export type QbTdPoints = 4 | 6;

export type RuleOperator = ">" | ">=" | "<" | "<=" | "==" | "!=";
export type EffectType = "multiplier" | "flat_bonus" | "flat_penalty" | "flag";

export interface RuleCondition {
  field: string;
  operator: RuleOperator;
  value: number | string | boolean;
}

export interface RuleEffect {
  type: EffectType;
  value: number | string;
}

export interface Rule {
  name: string;
  conditions: RuleCondition[];
  effect: RuleEffect;
  enabled: boolean;
  weight: number;
  is_builtin: boolean;
  category: string;
  description?: string;
  positions: string[] | null;  // null (or []) = apply to all positions
}

// Per-position rule override map. Outer key: position string ("QB", "RB", etc.)
// Inner array: only rules whose settings differ from built-in defaults.
export type PositionRulesState = Record<string, PositionRuleOverride[]>;

export interface PositionRuleOverride {
  name: string;
  enabled: boolean;
  weight: number;
}

export interface GenerateRequest {
  scoring_format: ScoringFormat;
  league_type: LeagueType;
  league_size: LeagueSize;
  // Number of QB slots the league starts per team: 1 = standard, 2 = superflex/2-QB.
  // Driven by the Superflex toggle in SettingsPanel (#724); deepens the QB VBD
  // replacement baseline. Omitted → backend applies its single-QB default.
  qb_starters?: 1 | 2;
  qb_td_points: QbTdPoints;
  bonus_100yd_rushing: boolean;
  bonus_100yd_receiving: boolean;
  bonus_first_downs: boolean;
  // TE Premium (#525): bonus points per tight-end reception, additive on top of
  // the PPR/half-PPR value. Optional — omitted requests use the backend default 0.0.
  te_premium_bonus?: number;
  weight_prior_year: number;
  weight_espn: number;
  weight_consensus: number;
  // Prior-year games-played discount knobs (#315). Optional: omitted profiles
  // fall back to the backend defaults (14 / "linear") unchanged.
  full_season_games?: number;
  prior_year_ramp?: "linear" | "steep";
  draft_rounds: number;
  overall_tier_count?: number;
  rules: Record<string, Array<{ name: string; enabled: boolean; weight: number }>>;
  keepers?: string[];
  league_adp?: Record<string, number>;
}

export interface RuleApplication {
  name: string;
  effect_type: EffectType;
  before_score: number;
  after_score: number;
  delta: number;
}

export interface TieredPlayer {
  overall_rank: number;
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  overall_tier: number;
  positional_tier: string;
  adjusted_score: number;
  projected_score_raw: number;
  prior_year_actual: number | null;
  espn_projection: number | null;
  fantasypros_projection: number | null;
  avg_projection: number | null;
  adp_standard: number | null;
  adp_ppr: number | null;
  adp_dynasty: number | null;
  league_adp: number | null;
  vbd_score: number;
  position_replacement: number;
  flags: string[];
  rules_applied: string[];
  rule_applications: RuleApplication[];
  is_favorite_player: boolean | null;
  is_favorite_team: boolean | null;
}

export interface GenerateResponse {
  players: TieredPlayer[];
  total: number;
  data_as_of: string | null;
  // Sources attempted but never once successfully refreshed (#547). Absent from
  // data_as_of despite contributing no data, so surfaced for a warning.
  never_succeeded: string[];
}

export interface DataSourceStatus {
  last_updated: string | null;
  last_attempted: string | null;
  last_error: string | null;
  rows_upserted: number;
}

export type DataStatusResponse = Record<string, DataSourceStatus>;

// ---------- accounts & profiles ----------

export interface User {
  id: string;
  email: string | null;
  yahoo_subject: string | null;
  yahoo_fantasy_connected: boolean;
  google_subject: string | null;
  last_active_profile_id: string | null;
  has_password: boolean;
  email_verified: boolean;
  password_changed_at: string | null;  // ISO 8601
}

export interface LinkedLeague {
  profile_id: string;
  provider: "sleeper" | "espn" | "yahoo" | "cbs" | "nfl";
  // Null when the user pre-linked a provider account without selecting a league.
  league_id: string | null;
  league_metadata_json: { name: string; season: number } | null;
  keepers_json: Array<{ player_name: string; position: string; team: string }> | null;
  adp_json: Record<string, number> | null;
  last_synced_at: string;
}

export interface SleeperLeagueSummary {
  id: string;
  name: string;
  season: number;
}

export interface Profile {
  id: string;
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Record<string, Array<{ name: string; enabled: boolean; weight: number }>>;
  linked_league: LinkedLeague | null;
}

export interface MeResponse {
  user: User;
  profiles: Profile[];
}

export interface ProfilesListResponse {
  profiles: Profile[];
  active_profile_id: string | null;
}

export interface FavoritesOut {
  favorite_player_ids: string[];
  favorite_teams: string[];
}

export type FavoritesUpdate = FavoritesOut;  // same shape

export interface PlayerSearchResult {
  id: string;
  name: string;
  position: string;
  team: string | null;
  espn_id: string | null;
}
