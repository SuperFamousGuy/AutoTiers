import type { TieredPlayer } from "@/api/types";
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

const CSV_HEADERS = [
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
 * Generates a CSV string from a list of tiered players.
 * Tier labels use the provided overrides (if any), falling back to the static defaults.
 */
export function generateCsvString(
  players: TieredPlayer[],
  tierLabelOverrides?: Partial<Record<number, string>>,
): string {
  const rows: string[] = [CSV_HEADERS.join(",")];

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
