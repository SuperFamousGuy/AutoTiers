import { describe, it, expect } from "vitest";
import { buildDraftWorkbookSheets } from "@/lib/xlsx";
import { DRAFT_CSV_HEADERS, draftRowValues, generateDraftCsvString } from "@/lib/csv";
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

const opts = (format: ScoringFormat = "standard") => ({ scoringFormat: format });

/** Flattens a write-excel-file sheet's cell objects back to their string values. */
function cellValues(sheet: { data: Array<Array<{ value?: unknown }>> }): string[][] {
  return sheet.data.map((row) => row.map((cell) => String(cell.value)));
}

describe("buildDraftWorkbookSheets", () => {
  it("always includes an 'All' sheet first, even with no players", () => {
    const sheets = buildDraftWorkbookSheets([], opts());
    expect(sheets.map((s) => s.sheet)).toEqual(["All"]);
  });

  it("'All' sheet content matches the legacy draft CSV exactly (header + rows)", () => {
    const players = [
      makePlayer({ overall_rank: 1, name: "QB One", position: "QB", positional_tier: "QB1" }),
      makePlayer({ overall_rank: 2, name: "Smith, Jr.", position: "RB", positional_tier: "RB1" }),
      makePlayer({ overall_rank: 3, name: "WR Guy", position: "WR", positional_tier: "WR1", adp_standard: null }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    const all = sheets.find((s) => s.sheet === "All")!;
    const allValues = cellValues(all as never);

    // Header row identical to the CSV header definition.
    expect(allValues[0]).toEqual([...DRAFT_CSV_HEADERS]);

    // Reconstruct the same content the CSV would produce for each player and
    // compare the per-row string projection 1:1 (null/undefined -> "").
    const expectedRows = players.map((p) =>
      draftRowValues(p, opts()).map((c) => (c === null || c === undefined ? "" : String(c))),
    );
    expect(allValues.slice(1)).toEqual(expectedRows);

    // Cross-check: the CSV builder consumes the SAME projection, so the All-sheet
    // data rows and the CSV data rows must agree field-for-field.
    const csvRows = generateDraftCsvString(players, opts()).split("\r\n").slice(1);
    csvRows.forEach((csvRow, i) => {
      // Strip CSV quoting for the comma-containing "Smith, Jr." case before compare.
      const expectedJoined = expectedRows[i]
        .map((f) => (f.includes(",") ? `"${f.replace(/"/g, '""')}"` : f))
        .join(",");
      expect(csvRow).toBe(expectedJoined);
    });
  });

  it("creates one tab per populated position, in PositionFilter order", () => {
    const players = [
      makePlayer({ position: "DST", name: "D1" }),
      makePlayer({ position: "QB", name: "Q1" }),
      makePlayer({ position: "WR", name: "W1" }),
      makePlayer({ position: "QB", name: "Q2" }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    // All first, then QB, WR, DST — TE/RB/K omitted (no players). Exact set + order.
    expect(sheets.map((s) => s.sheet)).toEqual(["All", "QB", "WR", "DST"]);
  });

  it("omits a position tab entirely when it has zero players", () => {
    const players = [makePlayer({ position: "QB" })];
    const sheets = buildDraftWorkbookSheets(players, opts());
    expect(sheets.map((s) => s.sheet)).toEqual(["All", "QB"]);
    expect(sheets.map((s) => s.sheet)).not.toContain("K");
    expect(sheets.map((s) => s.sheet)).not.toContain("RB");
  });

  it("each position tab contains only that position's players", () => {
    const players = [
      makePlayer({ position: "QB", name: "Q1" }),
      makePlayer({ position: "QB", name: "Q2" }),
      makePlayer({ position: "RB", name: "R1" }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    const qb = cellValues(sheets.find((s) => s.sheet === "QB")! as never);
    const rb = cellValues(sheets.find((s) => s.sheet === "RB")! as never);
    // header + 2 QB rows; header + 1 RB row
    expect(qb.length).toBe(3);
    expect(rb.length).toBe(2);
    // Player column (index 1) carries the right names.
    expect(qb.slice(1).map((r) => r[1])).toEqual(["Q1", "Q2"]);
    expect(rb.slice(1).map((r) => r[1])).toEqual(["R1"]);
  });

  it("every sheet name is a valid Excel tab name (<=31 chars, no forbidden chars)", () => {
    const players = [
      makePlayer({ position: "QB" }),
      makePlayer({ position: "DST" }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    for (const s of sheets) {
      expect(s.sheet!.length).toBeGreaterThan(0);
      expect(s.sheet!.length).toBeLessThanOrEqual(31);
      expect(s.sheet!).not.toMatch(/[:\\/?*[\]]/);
    }
  });

  it("respects scoring format for the ADP column on every sheet", () => {
    const player = makePlayer({ position: "WR", adp_standard: 5, adp_ppr: 3 });
    const sheetsPpr = buildDraftWorkbookSheets([player], opts("ppr"));
    const wr = cellValues(sheetsPpr.find((s) => s.sheet === "WR")! as never);
    const adpColIndex = DRAFT_CSV_HEADERS.indexOf("ADP");
    expect(wr[1][adpColIndex]).toBe("3"); // ppr ADP, not standard 5
  });
});
