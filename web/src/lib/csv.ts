import type { ScoringFormat, TieredPlayer } from "@/api/types";
import { getCustomTierLabel } from "@/lib/tiers";

/**
 * Escapes a CSV field per RFC 4180: if the value contains a comma, double-quote,
 * or newline, wrap it in double-quotes and escape internal double-quotes by
 * doubling them.
 */
function csvField(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const str = String(value);
  if (str.includes(",") || str.includes('"') || str.includes("\n") || str.includes("\r")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Formats a rule_applications entry as a single delta string.
 * Flags become "name: flagged"; numeric effects become "name: +X.X" or "name: -X.X".
 */
function formatRuleDelta(app: TieredPlayer["rule_applications"][number]): string {
  if (app.effect_type === "flag") {
    return `${app.name}: flagged`;
  }
  const sign = app.delta >= 0 ? "+" : "";
  return `${app.name}: ${sign}${app.delta.toFixed(1)}`;
}

/**
 * Picks the single ADP value matching the chosen scoring format. `league_type`
 * is hardcoded "standard" in the generate request, so dynasty ADP is unreachable
 * from the UI and selection keys off scoring_format only. Half-PPR has no ADP
 * source of its own and tracks PPR boards more closely than standard, so it maps
 * to adp_ppr.
 */
function adpForFormat(p: TieredPlayer, format: ScoringFormat): number | null {
  switch (format) {
    case "ppr":
    case "half_ppr":
      return p.adp_ppr;
    case "standard":
      return p.adp_standard;
    default:
      // Exhaustiveness guard: adding a ScoringFormat without a case here is a
      // compile error; an unexpected runtime value yields an empty ADP, not undefined.
      format satisfies never;
      return null;
  }
}

const DRAFT_CSV_HEADERS = [
  "Rank",
  "Player",
  "Pos",
  "Team",
  "Age",
  "Tier",
  "Tier Label",
  "Pos Tier",
  "ADP",
  "Value",
  "Flags",
] as const;

export interface DraftCsvOptions {
  scoringFormat: ScoringFormat;
  tierLabelOverrides?: Partial<Record<number, string>>;
}

/**
 * Generates the customer-facing draft cheat-sheet CSV: lean, human-readable
 * columns a user can scan during a live draft. `Value` is vbd_score (points above
 * replacement) rounded to 1 decimal; `ADP` is the format-matched ADP.
 * Tier labels use the provided overrides (if any), falling back to static defaults.
 */
export function generateDraftCsvString(
  players: TieredPlayer[],
  options: DraftCsvOptions,
): string {
  const { scoringFormat, tierLabelOverrides } = options;
  const rows: string[] = [DRAFT_CSV_HEADERS.join(",")];

  for (const p of players) {
    const tierLabel = getCustomTierLabel(p.overall_tier, tierLabelOverrides);
    const adp = adpForFormat(p, scoringFormat);

    const row = [
      csvField(p.overall_rank),
      csvField(p.name),
      csvField(p.position),
      csvField(p.team),
      csvField(p.age),
      csvField(p.overall_tier),
      csvField(tierLabel),
      csvField(p.positional_tier),
      csvField(adp),
      csvField(p.vbd_score.toFixed(1)),
      csvField(p.flags.join("; ")),
    ].join(",");

    rows.push(row);
  }

  return rows.join("\r\n");
}

const DEBUG_CSV_HEADERS = [
  "overall_rank",
  "player",
  "position",
  "team",
  "age",
  "overall_tier",
  "tier_label",
  "positional_tier",
  "adjusted_score",
  "vbd_score",
  "position_replacement",
  "projected_score_raw",
  "prior_year_actual",
  "espn_projection",
  "fantasypros_projection",
  "avg_projection",
  "adp_standard",
  "adp_ppr",
  "adp_dynasty",
  "flags",
  "rules_applied",
  "rule_deltas",
] as const;

/**
 * Generates the full debug CSV: every internal column (scores, projections, rule
 * deltas). Reachable only via the ?debug=1 dev flag, not by normal users.
 * Tier labels use the provided overrides (if any), falling back to static defaults.
 */
export function generateDebugCsvString(
  players: TieredPlayer[],
  tierLabelOverrides?: Partial<Record<number, string>>,
): string {
  const rows: string[] = [DEBUG_CSV_HEADERS.join(",")];

  for (const p of players) {
    const tierLabel = getCustomTierLabel(p.overall_tier, tierLabelOverrides);
    const ruleDeltas = p.rule_applications.map(formatRuleDelta).join("; ");

    const row = [
      csvField(p.overall_rank),
      csvField(p.name),
      csvField(p.position),
      csvField(p.team),
      csvField(p.age),
      csvField(p.overall_tier),
      csvField(tierLabel),
      csvField(p.positional_tier),
      csvField(p.adjusted_score),
      csvField(p.vbd_score),
      csvField(p.position_replacement),
      csvField(p.projected_score_raw),
      csvField(p.prior_year_actual),
      csvField(p.espn_projection),
      csvField(p.fantasypros_projection),
      csvField(p.avg_projection),
      csvField(p.adp_standard),
      csvField(p.adp_ppr),
      csvField(p.adp_dynasty),
      csvField(p.flags.join("; ")),
      csvField(p.rules_applied.join("; ")),
      csvField(ruleDeltas),
    ].join(",");

    rows.push(row);
  }

  return rows.join("\r\n");
}
