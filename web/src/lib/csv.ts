import type { ScoringFormat, TieredPlayer } from "@/api/types";
import { getCustomTierLabel } from "@/lib/tiers";

/**
 * Neutralizes spreadsheet formula injection (OWASP "CSV Injection"): Excel,
 * Google Sheets, and LibreOffice interpret a cell whose text begins with `=`,
 * `+`, `-`, `@`, tab, or CR as the start of a formula/command when the .csv is
 * opened. Tier labels are free text the user types (SettingsPanel.tsx), so a
 * label like `=1+cmd|'/c calc'!A0` or `@SUM(A1:A2)` would otherwise execute on
 * open. Prefixing a single apostrophe forces the cell to be read as text; the
 * apostrophe is not shown by the spreadsheet once imported. Applied to the raw
 * value before RFC 4180 quoting so the neutralized cell is still quoted when it
 * also contains a comma/quote/newline.
 */
function neutralizeFormula(str: string): string {
  return /^[=+\-@\t\r]/.test(str) ? `'${str}` : str;
}

/**
 * Escapes a CSV field per RFC 4180: if the value contains a comma, double-quote,
 * or newline, wrap it in double-quotes and escape internal double-quotes by
 * doubling them. First neutralizes any leading formula trigger (see
 * neutralizeFormula) so exported labels can't execute in a spreadsheet.
 *
 * Formula neutralization only applies to string inputs (user-entered labels,
 * player/team names, flags, etc.). Numeric inputs are exempt: a negative number
 * like vbd_score = -5.2 starts with `-`, which would otherwise be apostrophe-
 * prefixed and imported as text, breaking numeric sorting/calcs in spreadsheets.
 */
function csvField(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const str = typeof value === "string" ? neutralizeFormula(value) : String(value);
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

/**
 * Column headers for the customer-facing draft cheat-sheet. Exported so the XLSX
 * exporter (web/src/lib/xlsx.ts) renders the "All" sheet — and every per-position
 * sheet — with exactly the same columns in the same order as the legacy CSV.
 */
export const DRAFT_CSV_HEADERS = [
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

/**
 * Builds one draft cheat-sheet row as an array of raw (un-escaped) cell values,
 * aligned 1:1 with DRAFT_CSV_HEADERS. This is the single source of truth for the
 * draft export's per-row projection: generateDraftCsvString CSV-escapes these
 * values, and the XLSX exporter consumes them directly. `null`/`undefined` cells
 * render as empty (matching the CSV's empty-field behaviour).
 */
export function draftRowValues(
  p: TieredPlayer,
  options: DraftCsvOptions,
): (string | number | null | undefined)[] {
  const { scoringFormat, tierLabelOverrides } = options;
  const tierLabel = getCustomTierLabel(p.overall_tier, tierLabelOverrides);
  const adp = adpForFormat(p, scoringFormat);
  return [
    p.overall_rank,
    p.name,
    p.position,
    p.team,
    p.age,
    p.overall_tier,
    tierLabel,
    p.positional_tier,
    adp,
    p.vbd_score.toFixed(1),
    p.flags.join("; "),
  ];
}

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
  const rows: string[] = [DRAFT_CSV_HEADERS.join(",")];

  for (const p of players) {
    const row = draftRowValues(p, options).map(csvField).join(",");
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
