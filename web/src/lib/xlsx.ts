import type { TieredPlayer } from "@/api/types";
import type { PositionFilterValue } from "@/components/PositionFilter";
import { POSITION_FILTER_OPTIONS } from "@/components/PositionFilter";
import {
  DRAFT_CSV_HEADERS,
  draftRowValues,
  type DraftCsvOptions,
} from "@/lib/csv";

// write-excel-file has no root export — the browser bundle lives under the
// `/browser` subpath. `Sheet` is its multi-sheet type: `{ data, sheet? }`.
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
  };
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
