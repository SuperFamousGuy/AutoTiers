import { describe, it, expect } from "vitest";
import { generateDraftCsvString, generateDebugCsvString } from "@/lib/csv";
import { resolveTierLabelOverrides } from "@/lib/tiers";
import type { ScoringFormat, TieredPlayer } from "@/api/types";

function makePlayer(overrides: Partial<TieredPlayer> = {}): TieredPlayer {
  return {
    overall_rank: 1,
    player_id: "001",
    name: "Test Player",
    position: "WR",
    team: "KC",
    age: 25,
    overall_tier: 1,
    positional_tier: "WR1",
    adjusted_score: 300.0,
    projected_score_raw: 290.0,
    prior_year_actual: 280.0,
    espn_projection: null,
    fantasypros_projection: 285.0,
    avg_projection: 287.5,
    adp_standard: 5.0,
    adp_ppr: 3.0,
    adp_dynasty: 4.0,
    league_adp: null,
    vbd_score: 150.0,
    position_replacement: 150.0,
    flags: [],
    rules_applied: [],
    rule_applications: [],
    is_favorite_player: null,
    is_favorite_team: null,
    ...overrides,
  };
}

const draftOpts = (format: ScoringFormat = "standard", tierLabelOverrides?: Partial<Record<number, string>>) => ({
  scoringFormat: format,
  tierLabelOverrides,
});

describe("generateDraftCsvString", () => {
  it("header row has the lean human-readable columns in order", () => {
    const csv = generateDraftCsvString([], draftOpts());
    const header = csv.split("\r\n")[0];
    expect(header).toBe("Rank,Player,Pos,Team,Age,Tier,Tier Label,Pos Tier,ADP,Value,Flags");
  });

  it("empty player list produces a header-only file", () => {
    const csv = generateDraftCsvString([], draftOpts());
    expect(csv.split("\r\n")).toHaveLength(1);
  });

  it("uses CRLF line endings per RFC 4180", () => {
    const csv = generateDraftCsvString([makePlayer()], draftOpts());
    expect(csv).toContain("\r\n");
    expect(csv.split("\r\n")).toHaveLength(2); // header + 1 data row
  });

  it("Value column is vbd_score rounded to 1 decimal", () => {
    const csv = generateDraftCsvString([makePlayer({ vbd_score: 87.46 })], draftOpts());
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[9]).toBe("87.5");
  });

  it("standard format selects adp_standard", () => {
    const csv = generateDraftCsvString([makePlayer({ adp_standard: 5, adp_ppr: 3 })], draftOpts("standard"));
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[8]).toBe("5");
  });

  it("ppr format selects adp_ppr", () => {
    const csv = generateDraftCsvString([makePlayer({ adp_standard: 5, adp_ppr: 3 })], draftOpts("ppr"));
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[8]).toBe("3");
  });

  it("half_ppr format maps to adp_ppr", () => {
    const csv = generateDraftCsvString([makePlayer({ adp_standard: 5, adp_ppr: 3 })], draftOpts("half_ppr"));
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[8]).toBe("3");
  });

  it("unexpected scoring format yields an empty ADP, not undefined", () => {
    // Exercises the exhaustiveness default branch with a runtime value outside the union.
    const csv = generateDraftCsvString(
      [makePlayer({ adp_standard: 5, adp_ppr: 3 })],
      draftOpts("superflex" as unknown as ScoringFormat),
    );
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[8]).toBe("");
  });

  it("null ADP produces an empty field, not 'null'", () => {
    const csv = generateDraftCsvString([makePlayer({ adp_standard: null })], draftOpts("standard"));
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[8]).toBe("");
  });

  it("Flags column joins flags with '; '", () => {
    const csv = generateDraftCsvString([makePlayer({ flags: ["Sleeper", "Injury Risk"] })], draftOpts());
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain("Sleeper; Injury Risk");
  });

  it("tier label uses static default when no overrides", () => {
    const csv = generateDraftCsvString([makePlayer({ overall_tier: 1 })], draftOpts());
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[6]).toBe("Elite");
  });

  it("tier label uses override when present", () => {
    const csv = generateDraftCsvString([makePlayer({ overall_tier: 1 })], draftOpts("standard", { 1: "Studs" }));
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[6]).toBe("Studs");
  });

  it("CSV uses the active format's per-format tier label (#164)", () => {
    // Same player, same global labels — but the resolved labels differ by format.
    const global = { 1: "Global Studs" };
    const byFormat = { ppr: { 1: "PPR Studs" }, standard: { 1: "Standard Studs" } };
    const player = makePlayer({ overall_tier: 1 });

    const pprCsv = generateDraftCsvString(
      [player],
      draftOpts("ppr", resolveTierLabelOverrides(global, byFormat, "ppr")),
    );
    const stdCsv = generateDraftCsvString(
      [player],
      draftOpts("standard", resolveTierLabelOverrides(global, byFormat, "standard")),
    );

    expect(pprCsv.split("\r\n")[1].split(",")[6]).toBe("PPR Studs");
    expect(stdCsv.split("\r\n")[1].split(",")[6]).toBe("Standard Studs");
  });

  it("CSV falls back to the global tier label for a format with no per-format override (#164)", () => {
    const global = { 1: "Global Studs" };
    const byFormat = { ppr: { 1: "PPR Studs" } };
    // half_ppr has no per-format entry → falls back to the global label
    const csv = generateDraftCsvString(
      [makePlayer({ overall_tier: 1 })],
      draftOpts("half_ppr", resolveTierLabelOverrides(global, byFormat, "half_ppr")),
    );
    expect(csv.split("\r\n")[1].split(",")[6]).toBe("Global Studs");
  });

  it("fields containing commas are RFC 4180 quoted", () => {
    const csv = generateDraftCsvString([makePlayer({ name: "Smith, Jr." })], draftOpts());
    expect(csv.split("\r\n")[1]).toContain('"Smith, Jr."');
  });

  it("does not include debug-only columns", () => {
    const csv = generateDraftCsvString([makePlayer()], draftOpts());
    const header = csv.split("\r\n")[0];
    expect(header).not.toContain("adjusted_score");
    expect(header).not.toContain("projected_score_raw");
    expect(header).not.toContain("rule_deltas");
  });

  it("multiple players produce multiple data rows", () => {
    const csv = generateDraftCsvString(
      [makePlayer({ overall_rank: 1 }), makePlayer({ overall_rank: 2 })],
      draftOpts(),
    );
    expect(csv.split("\r\n")).toHaveLength(3);
  });

  // CSV formula-injection mitigation (OWASP): a user-typed tier label that a
  // spreadsheet would read as a formula is prefixed with a single apostrophe.
  describe("formula injection in tier labels (#555)", () => {
    const cases: [string, string][] = [
      ["=2+2", "'=2+2"],
      ["+1", "'+1"],
      ["-1", "'-1"],
      ["@SUM(A1:A2)", "'@SUM(A1:A2)"],
    ];

    it.each(cases)("neutralizes a tier label of %s with a leading apostrophe", (label, expected) => {
      const csv = generateDraftCsvString([makePlayer({ overall_tier: 1 })], draftOpts("standard", { 1: label }));
      const columns = csv.split("\r\n")[1].split(",");
      expect(columns[6]).toBe(expected);
    });

    it("neutralizes a tab-led label", () => {
      const csv = generateDraftCsvString([makePlayer({ overall_tier: 1 })], draftOpts("standard", { 1: "\tcmd" }));
      const columns = csv.split("\r\n")[1].split(",");
      expect(columns[6]).toBe("'\tcmd");
    });

    it("neutralizes a formula that also needs RFC 4180 quoting", () => {
      // Leading '=' plus an embedded comma: apostrophe first, then quote-wrap.
      const csv = generateDraftCsvString(
        [makePlayer({ overall_tier: 1 })],
        draftOpts("standard", { 1: "=HYPERLINK(1,2)" }),
      );
      const dataRow = csv.split("\r\n")[1];
      expect(dataRow).toContain('"\'=HYPERLINK(1,2)"');
    });

    it("leaves a benign label untouched (no visible prefix)", () => {
      const csv = generateDraftCsvString([makePlayer({ overall_tier: 1 })], draftOpts("standard", { 1: "Studs" }));
      const columns = csv.split("\r\n")[1].split(",");
      expect(columns[6]).toBe("Studs");
    });

    it("does not prefix a label that merely contains a trigger char mid-string", () => {
      const csv = generateDraftCsvString([makePlayer({ overall_tier: 1 })], draftOpts("standard", { 1: "A+ Tier" }));
      const columns = csv.split("\r\n")[1].split(",");
      expect(columns[6]).toBe("A+ Tier");
    });
  });
});

describe("generateDebugCsvString", () => {
  it("header row has all expected columns in order", () => {
    const csv = generateDebugCsvString([]);
    const header = csv.split("\r\n")[0];
    expect(header).toBe(
      "overall_rank,player,position,team,age,overall_tier,tier_label,positional_tier,adjusted_score,vbd_score,position_replacement,projected_score_raw,prior_year_actual,espn_projection,fantasypros_projection,avg_projection,adp_standard,adp_ppr,adp_dynasty,flags,rules_applied,rule_deltas",
    );
  });

  it("uses CRLF line endings per RFC 4180", () => {
    const csv = generateDebugCsvString([makePlayer()]);
    expect(csv).toContain("\r\n");
    expect(csv.split("\r\n")).toHaveLength(2); // header + 1 data row
  });

  it("tier_label uses static default when no overrides", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 1 })]);
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    // tier_label is column index 6 (0-based)
    expect(columns[6]).toBe("Elite");
  });

  it("tier_label uses override when present", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 1 })], { 1: "Studs" });
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Studs");
  });

  it("tier_label falls back to static default when override is empty string", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 1 })], { 1: "" });
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Elite");
  });

  it("tier_label falls back to static default when override is whitespace-only", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 1 })], { 1: "   " });
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Elite");
  });

  it("tier_label uses 'Deep Sleepers' for tier 7 (now a named tier)", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 7 })]);
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Deep Sleepers");
  });

  it("tier_label falls back to 'Late Round' for tier 12 with no override", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 12 })]);
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Late Round");
  });

  it("fields containing commas are RFC 4180 quoted", () => {
    const csv = generateDebugCsvString([makePlayer({ name: "Smith, Jr." })]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain('"Smith, Jr."');
  });

  it("fields containing double-quotes have them escaped by doubling", () => {
    const csv = generateDebugCsvString([makePlayer({ name: 'He said "hello"' })]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain('"He said ""hello"""');
  });

  it("fields containing carriage returns are RFC 4180 quoted", () => {
    const csv = generateDebugCsvString([makePlayer({ name: "Line1\rLine2" })]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain('"Line1\rLine2"');
  });

  it("rule_deltas formats flag effect as 'name: flagged'", () => {
    const csv = generateDebugCsvString([
      makePlayer({
        rule_applications: [
          { name: "Contract Year", effect_type: "flag", before_score: 300, after_score: 300, delta: 0 },
        ],
      }),
    ]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain("Contract Year: flagged");
  });

  it("rule_deltas formats positive numeric delta as '+X.X'", () => {
    const csv = generateDebugCsvString([
      makePlayer({
        rule_applications: [
          { name: "Target Premium", effect_type: "flat_bonus", before_score: 280, after_score: 300, delta: 20 },
        ],
      }),
    ]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain("Target Premium: +20.0");
  });

  it("rule_deltas formats negative numeric delta as '-X.X'", () => {
    const csv = generateDebugCsvString([
      makePlayer({
        rule_applications: [
          { name: "TD Regression", effect_type: "multiplier", before_score: 300, after_score: 280, delta: -20 },
        ],
      }),
    ]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).toContain("TD Regression: -20.0");
  });

  it("null fields produce empty strings, not 'null'", () => {
    const csv = generateDebugCsvString([makePlayer({ team: null, age: null, espn_projection: null })]);
    const dataRow = csv.split("\r\n")[1];
    expect(dataRow).not.toContain("null");
  });

  it("multiple players produce multiple data rows", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_rank: 1 }), makePlayer({ overall_rank: 2 })]);
    const lines = csv.split("\r\n");
    expect(lines).toHaveLength(3); // header + 2 data rows
  });

  it("tier 5 label uses 'Streamers / Deep Flex' static default — slash but no comma, not quoted", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 5 })]);
    const dataRow = csv.split("\r\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Streamers / Deep Flex");
  });

  it("neutralizes a formula-injecting tier label (#555)", () => {
    const csv = generateDebugCsvString([makePlayer({ overall_tier: 1 })], { 1: "=2+2" });
    const columns = csv.split("\r\n")[1].split(",");
    expect(columns[6]).toBe("'=2+2");
  });
});
