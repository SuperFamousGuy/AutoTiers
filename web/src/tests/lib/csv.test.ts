import { describe, it, expect } from "vitest";
import { generateCsvBlob } from "@/lib/csv";
import type { TieredPlayer } from "@/api/types";

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

describe("generateCsvBlob", () => {
  it("header row has all expected columns in order", () => {
    const csv = generateCsvBlob([]);
    const header = csv.split("\n")[0];
    expect(header).toBe(
      "overall_rank,player,position,team,age,overall_tier,tier_label,positional_tier,adjusted_score,vbd_score,position_replacement,projected_score_raw,prior_year_actual,espn_projection,fantasypros_projection,avg_projection,adp_standard,adp_ppr,adp_dynasty,flags,rules_applied,rule_deltas",
    );
  });

  it("tier_label uses static default when no overrides", () => {
    const csv = generateCsvBlob([makePlayer({ overall_tier: 1 })]);
    const dataRow = csv.split("\n")[1];
    const columns = dataRow.split(",");
    // tier_label is column index 6 (0-based)
    expect(columns[6]).toBe("Elite");
  });

  it("tier_label uses override when present", () => {
    const csv = generateCsvBlob([makePlayer({ overall_tier: 1 })], { 1: "Studs" });
    const dataRow = csv.split("\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Studs");
  });

  it("tier_label falls back to 'Late Round' for tier 7 with no override", () => {
    const csv = generateCsvBlob([makePlayer({ overall_tier: 7 })]);
    const dataRow = csv.split("\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Late Round");
  });

  it("fields containing commas are RFC 4180 quoted", () => {
    // "Streamers / Deep Flex" has no comma; use a player name that does
    const csv = generateCsvBlob([makePlayer({ name: "Smith, Jr." })]);
    const dataRow = csv.split("\n")[1];
    // player name is column index 1
    expect(dataRow).toContain('"Smith, Jr."');
  });

  it("fields containing double-quotes have them escaped by doubling", () => {
    const csv = generateCsvBlob([makePlayer({ name: 'He said "hello"' })]);
    const dataRow = csv.split("\n")[1];
    expect(dataRow).toContain('"He said ""hello"""');
  });

  it("rule_deltas formats flag effect as 'name: flagged'", () => {
    const csv = generateCsvBlob([
      makePlayer({
        rule_applications: [
          { name: "Contract Year", effect_type: "flag", before_score: 300, after_score: 300, delta: 0 },
        ],
      }),
    ]);
    const dataRow = csv.split("\n")[1];
    expect(dataRow).toContain("Contract Year: flagged");
  });

  it("rule_deltas formats positive numeric delta as '+X.X'", () => {
    const csv = generateCsvBlob([
      makePlayer({
        rule_applications: [
          { name: "Target Premium", effect_type: "flat_bonus", before_score: 280, after_score: 300, delta: 20 },
        ],
      }),
    ]);
    const dataRow = csv.split("\n")[1];
    expect(dataRow).toContain("Target Premium: +20.0");
  });

  it("rule_deltas formats negative numeric delta as '-X.X'", () => {
    const csv = generateCsvBlob([
      makePlayer({
        rule_applications: [
          { name: "TD Regression", effect_type: "multiplier", before_score: 300, after_score: 280, delta: -20 },
        ],
      }),
    ]);
    const dataRow = csv.split("\n")[1];
    expect(dataRow).toContain("TD Regression: -20.0");
  });

  it("null fields produce empty strings, not 'null'", () => {
    const csv = generateCsvBlob([makePlayer({ team: null, age: null, espn_projection: null })]);
    const dataRow = csv.split("\n")[1];
    // Check that 'null' string does not appear in the row
    expect(dataRow).not.toContain("null");
  });

  it("multiple players produce multiple data rows", () => {
    const csv = generateCsvBlob([makePlayer({ overall_rank: 1 }), makePlayer({ overall_rank: 2 })]);
    const lines = csv.split("\n");
    expect(lines).toHaveLength(3); // header + 2 data rows
  });

  it("tier 5 label uses 'Streamers / Deep Flex' static default — slash but no comma, not quoted", () => {
    const csv = generateCsvBlob([makePlayer({ overall_tier: 5 })]);
    const dataRow = csv.split("\n")[1];
    const columns = dataRow.split(",");
    expect(columns[6]).toBe("Streamers / Deep Flex");
  });
});
