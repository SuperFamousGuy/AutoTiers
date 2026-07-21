import { describe, it, expect } from "vitest";
import {
  buildDraftWorkbookSheets,
  buildXlsxFilename,
  DEFAULT_XLSX_FILENAME,
} from "@/lib/xlsx";
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
    ...overrides,
  };
}

const opts = (format: ScoringFormat = "standard") => ({ scoringFormat: format });

/** Flattens a write-excel-file sheet's cell objects back to their string values. */
function cellValues(sheet: { data: Array<Array<{ value?: unknown }>> }): string[][] {
  return sheet.data.map((row) => row.map((cell) => String(cell.value)));
}

describe("buildXlsxFilename", () => {
  // Fixed date so the date suffix is deterministic (2026-07-12).
  const date = new Date(2026, 6, 12);

  it("derives the filename from profile name, scoring format, and date", () => {
    expect(buildXlsxFilename("Redraft", "half_ppr", date)).toBe(
      "redraft-half-ppr-tiers-2026-07-12.xlsx",
    );
  });

  it("maps each scoring format to a hyphenated label", () => {
    expect(buildXlsxFilename("League", "standard", date)).toBe(
      "league-standard-tiers-2026-07-12.xlsx",
    );
    expect(buildXlsxFilename("League", "half_ppr", date)).toBe(
      "league-half-ppr-tiers-2026-07-12.xlsx",
    );
    expect(buildXlsxFilename("League", "ppr", date)).toBe(
      "league-ppr-tiers-2026-07-12.xlsx",
    );
  });

  it("slugifies messy names (case, spaces, punctuation) into a safe token", () => {
    expect(buildXlsxFilename("  My League #1!  ", "ppr", date)).toBe(
      "my-league-1-ppr-tiers-2026-07-12.xlsx",
    );
  });

  it("zero-pads single-digit month and day", () => {
    expect(buildXlsxFilename("League", "ppr", new Date(2026, 0, 3))).toBe(
      "league-ppr-tiers-2026-01-03.xlsx",
    );
  });

  it("falls back to tiers.xlsx when no profile name is available", () => {
    expect(buildXlsxFilename(null, "ppr", date)).toBe(DEFAULT_XLSX_FILENAME);
    expect(buildXlsxFilename(undefined, "ppr", date)).toBe(DEFAULT_XLSX_FILENAME);
    expect(buildXlsxFilename("", "ppr", date)).toBe(DEFAULT_XLSX_FILENAME);
  });

  it("falls back to tiers.xlsx when the name slugifies to nothing", () => {
    expect(buildXlsxFilename("!!!", "ppr", date)).toBe(DEFAULT_XLSX_FILENAME);
    expect(buildXlsxFilename("   ", "ppr", date)).toBe(DEFAULT_XLSX_FILENAME);
  });

  it("uses the current date when none is provided", () => {
    const name = buildXlsxFilename("League", "ppr");
    expect(name).toMatch(/^league-ppr-tiers-\d{4}-\d{2}-\d{2}\.xlsx$/);
  });
});

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

  it("freezes the header row (stickyRowsCount=1) on every sheet", () => {
    const players = [
      makePlayer({ position: "QB", name: "Q1" }),
      makePlayer({ position: "WR", name: "W1" }),
      makePlayer({ position: "DST", name: "D1" }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    // All + every populated position tab — uniform, no exceptions.
    expect(sheets.map((s) => s.sheet)).toEqual(["All", "QB", "WR", "DST"]);
    for (const s of sheets) {
      expect(s.stickyRowsCount).toBe(1);
    }
  });

  it("sets readable column widths aligned 1:1 with the headers on every sheet", () => {
    const players = [makePlayer({ position: "QB" }), makePlayer({ position: "RB" })];
    const sheets = buildDraftWorkbookSheets(players, opts());
    expect(sheets.length).toBeGreaterThan(1);
    for (const s of sheets) {
      // One width entry per column, in header order.
      expect(s.columns).toHaveLength(DRAFT_CSV_HEADERS.length);
      // Every width is a positive number (no zero/negative/NaN widths).
      for (const col of s.columns!) {
        expect(typeof col.width).toBe("number");
        expect(col.width!).toBeGreaterThan(0);
      }
      // The Player column is wider than the narrow numeric columns so long
      // names (e.g. "Christian McCaffrey") aren't truncated.
      const widthOf = (h: (typeof DRAFT_CSV_HEADERS)[number]) =>
        s.columns![DRAFT_CSV_HEADERS.indexOf(h)].width!;
      for (const narrow of ["Rank", "Pos", "Team", "Age", "Tier"] as const) {
        expect(widthOf("Player")).toBeGreaterThan(widthOf(narrow));
      }
    }
  });

  it("applies identical width config across All and every position tab", () => {
    const players = [
      makePlayer({ position: "QB" }),
      makePlayer({ position: "WR" }),
      makePlayer({ position: "TE" }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    const widthsOf = (sheetName: string) =>
      sheets.find((s) => s.sheet === sheetName)!.columns!.map((c) => c.width);
    const allWidths = widthsOf("All");
    for (const name of ["QB", "WR", "TE"]) {
      expect(widthsOf(name)).toEqual(allWidths);
    }
  });

  it("styling does not alter cell values — 'All' content stays byte-equal to the CSV", () => {
    const players = [
      makePlayer({ overall_rank: 1, name: "Christian McCaffrey", position: "RB" }),
      makePlayer({ overall_rank: 2, name: "Comma, Name", position: "WR" }),
    ];
    const sheets = buildDraftWorkbookSheets(players, opts());
    const all = sheets.find((s) => s.sheet === "All")!;
    const allValues = cellValues(all as never);

    const expectedRows = players.map((p) =>
      draftRowValues(p, opts()).map((c) => (c === null || c === undefined ? "" : String(c))),
    );
    expect(allValues[0]).toEqual([...DRAFT_CSV_HEADERS]);
    expect(allValues.slice(1)).toEqual(expectedRows);
  });
});
