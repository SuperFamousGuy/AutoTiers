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
}

export interface GenerateRequest {
  scoring_format: ScoringFormat;
  league_type: LeagueType;
  league_size: LeagueSize;
  qb_td_points: QbTdPoints;
  bonus_100yd_rushing: boolean;
  bonus_100yd_receiving: boolean;
  bonus_first_downs: boolean;
  weight_prior_year: number;
  weight_espn: number;
  weight_consensus: number;
  draft_rounds: number;
  rules: Rule[];
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
  vbd_score: number;
  position_replacement: number;
  flags: string[];
  rules_applied: string[];
  rule_applications: RuleApplication[];
}

export interface GenerateResponse {
  players: TieredPlayer[];
  total: number;
  data_as_of: string | null;
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
  google_subject: string | null;
  last_active_profile_id: string | null;
}

export interface Profile {
  id: string;
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Array<{ name: string; enabled: boolean; weight: number }>;
}

export interface MeResponse {
  user: User;
  profiles: Profile[];
}

export interface ProfilesListResponse {
  profiles: Profile[];
  active_profile_id: string | null;
}
