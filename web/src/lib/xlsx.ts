import type { ScoringFormat, TieredPlayer } from "@/api/types";
import type { PositionFilterValue } from "@/components/PositionFilter";
import { POSITION_FILTER_OPTIONS } from "@/components/PositionFilter";
import {
  DRAFT_CSV_HEADERS,
  draftRowValues,
  type DraftCsvOptions,
} from "@/lib/csv";

// write-excel-file has no root export — the browser bundle lives under the
// `/browser` subpath. `Sheet` is its multi-sheet type: `{ data, sheet?, columns?,
// stickyRowsCount?, … }` — per-sheet presentation options live on the same object.
import writeXlsxFile, { type Sheet } from "write-excel-file/browser";

/**
 * Excel sheet (tab) names are constrained: max 31 characters and may not contain
 * any of : \ / ? * [ ]. All of our tab names ("All", "QB", … "DST") are well
 * within these limits, but the rule is enforced here so a future position label
 * change can't silently produce an invalid workbook.
 */
const MAX_SHEET_NAME_LENGTH = 31;
const INVALID_SHEET_NAME_CHARS = /[:\\/?*[\]]/;

function assertValidSheetName(name: string): string {
  if (name.length === 0 || name.length > MAX_SHEET_NAME_LENGTH) {
    throw new Error(`Invalid xlsx sheet name length: "${name}"`);
  }
  if (INVALID_SHEET_NAME_CHARS.test(name)) {
    throw new Error(`Invalid xlsx sheet name characters: "${name}"`);
  }
  return name;
}

/** Display label for a tab: "ALL" renders as "All"; every other position is verbatim. */
function tabLabel(pos: PositionFilterValue): string {
  return pos === "ALL" ? "All" : pos;
}

/**
 * Number of header rows frozen at the top of every sheet. The header occupies
 * row 1 only, so freezing one row keeps the column labels visible while a drafter
 * scrolls through the board. write-excel-file calls this "sticky"; Excel/Sheets
 * surface it as a frozen row.
 */
const STICKY_HEADER_ROWS = 1;

/**
 * Per-column widths (in "characters", the unit write-excel-file uses) aligned
 * 1:1 with DRAFT_CSV_HEADERS so player name, team, position, and tier columns
 * read without manual resizing. Widening here is presentation-only — it never
 * touches cell values, so the "All" sheet stays byte-equal to the legacy CSV.
 *
 * Kept as a single shared constant so every sheet (All + each position tab) is
 * styled identically. A length mismatch with DRAFT_CSV_HEADERS is a build error
 * (see the satisfies guard below), preventing widths from silently drifting out
 * of alignment with the columns if a header is ever added or removed.
 */
const DRAFT_COLUMN_WIDTHS = [
  6, // Rank
  24, // Player — longest field (e.g. "Christian McCaffrey")
  6, // Pos
  6, // Team
  6, // Age
  6, // Tier
  16, // Tier Label — custom labels can be a few words
  10, // Pos Tier
  8, // ADP
  8, // Value
  30, // Flags — can carry several semicolon-separated tags
] as const;

// Compile-time guard: the width list must stay aligned 1:1 with the headers.
// If a header is added or removed without updating the widths above, the lengths
// diverge and this assignment fails to type-check.
const _WIDTHS_MATCH_HEADERS: (typeof DRAFT_CSV_HEADERS)["length"] =
  DRAFT_COLUMN_WIDTHS.length satisfies (typeof DRAFT_CSV_HEADERS)["length"];
void _WIDTHS_MATCH_HEADERS;

/** Shared per-sheet width config; every sheet gets the same column geometry. */
const DRAFT_SHEET_COLUMNS = DRAFT_COLUMN_WIDTHS.map((width) => ({ width }));

/**
 * Converts a list of players into one sheet's worth of write-excel-file rows.
 * Row 0 is the header; each subsequent row is the same projection the draft CSV
 * uses (draftRowValues), rendered as string cells so the sheet's content matches
 * the legacy CSV exactly. `null`/`undefined` values become empty strings.
 */
function buildSheet(
  name: PositionFilterValue,
  players: TieredPlayer[],
  options: DraftCsvOptions,
): Sheet<Blob> {
  const headerRow = DRAFT_CSV_HEADERS.map((h) => ({ value: h, type: String }));
  const dataRows = players.map((p) =>
    draftRowValues(p, options).map((cell) => ({
      value: cell === null || cell === undefined ? "" : String(cell),
      type: String,
    })),
  );
  return {
    sheet: assertValidSheetName(tabLabel(name)),
    data: [headerRow, ...dataRows],
    // Presentation-only: freeze the header row and size columns. These options
    // live alongside the data on the same Sheet object and never alter any cell
    // value, so the "All" sheet stays byte-equal to the legacy CSV content.
    stickyRowsCount: STICKY_HEADER_ROWS,
    columns: DRAFT_SHEET_COLUMNS,
  };
}

/** Filename used when no usable profile name is available. */
export const DEFAULT_XLSX_FILENAME = "tiers.xlsx";

/**
 * Short, filename-safe label per scoring format. Kept separate from the API's
 * underscore token ("half_ppr") so the download reads with hyphens ("half-ppr")
 * like the rest of the slug. A `Record<ScoringFormat, string>` so a new format
 * added to the union is a build error until it gets a label here.
 */
const SCORING_FORMAT_SLUG: Record<ScoringFormat, string> = {
  standard: "standard",
  half_ppr: "half-ppr",
  ppr: "ppr",
};

/**
 * Lowercases, replaces every run of non-alphanumerics with a single hyphen, and
 * trims leading/trailing hyphens. Returns "" when nothing usable remains (e.g. a
 * name that is only punctuation/emoji), which the caller treats as "no name".
 */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Local calendar date as YYYY-MM-DD (zero-padded), for the filename suffix. */
function formatDatePart(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Derives the Excel export filename from the active profile name, scoring format,
 * and date — e.g. `redraft-half-ppr-tiers-2026-07-12.xlsx`. This lets a user
 * exporting for several leagues/profiles on draft day tell the files apart
 * instead of ending up with `tiers.xlsx`, `tiers (1).xlsx`, …
 *
 * Falls back to `DEFAULT_XLSX_FILENAME` ("tiers.xlsx") when no usable profile
 * name is available — `null`/`undefined`/empty, or a name that slugifies to "".
 *
 * `date` is injectable so the output is deterministic under test; production
 * callers omit it and get the current local date.
 */
export function buildXlsxFilename(
  profileName: string | null | undefined,
  scoringFormat: ScoringFormat,
  date: Date = new Date(),
): string {
  const slug = profileName ? slugify(profileName) : "";
  if (!slug) return DEFAULT_XLSX_FILENAME;
  return `${slug}-${SCORING_FORMAT_SLUG[scoringFormat]}-tiers-${formatDatePart(date)}.xlsx`;
}

/**
 * Builds the multi-sheet draft workbook structure: an "All" sheet (always present,
 * matching the legacy tiers.csv content exactly) followed by one sheet per position
 * in PositionFilter order. A position with zero players is OMITTED entirely (no
 * phantom empty tab) — the "All" sheet still carries every player. "All" is always
 * present even when `players` is empty, because a zero-sheet workbook is invalid.
 *
 * Exported (not just the download fn) so tests can assert sheet set + contents
 * without invoking the browser download path.
 */
export function buildDraftWorkbookSheets(
  players: TieredPlayer[],
  options: DraftCsvOptions,
): Sheet<Blob>[] {
  const sheets: Sheet<Blob>[] = [];
  for (const pos of POSITION_FILTER_OPTIONS) {
    if (pos === "ALL") {
      sheets.push(buildSheet(pos, players, options));
      continue;
    }
    const forPosition = players.filter((p) => p.position === pos);
    if (forPosition.length === 0) continue; // omit empty position tabs
    sheets.push(buildSheet(pos, forPosition, options));
  }
  return sheets;
}

/**
 * Builds the draft tiers workbook as an xlsx Blob. Pure (no DOM side effects) so
 * it is unit-testable; the download trigger lives in web/src/api/hooks.ts.
 */
export async function buildDraftXlsxBlob(
  players: TieredPlayer[],
  options: DraftCsvOptions,
): Promise<Blob> {
  const sheets = buildDraftWorkbookSheets(players, options);
  // The browser build returns a handle with `.toBlob()` / `.toFile()`; it does NOT
  // itself return a Blob. We produce the Blob and let hooks.ts trigger the download.
  return writeXlsxFile(sheets).toBlob();
}
