import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { generateDebugCsvString } from "@/lib/csv";
import type { DraftCsvOptions } from "@/lib/csv";
import type {
  DataStatusResponse,
  GenerateRequest,
  GenerateResponse,
  Rule,
  ScoringFormat,
  TieredPlayer,
} from "./types";

export function useRules() {
  return useQuery<Rule[]>({
    queryKey: ["rules"],
    queryFn: () => apiFetch<Rule[]>("/api/rules"),
    staleTime: Infinity,
  });
}

export function useDataStatus() {
  return useQuery<DataStatusResponse>({
    queryKey: ["data-status"],
    queryFn: () => apiFetch<DataStatusResponse>("/api/data/status"),
    staleTime: 60_000,
  });
}

export function useGenerateMutation() {
  return useMutation<GenerateResponse, Error, GenerateRequest>({
    mutationFn: (body) =>
      apiFetch<GenerateResponse>("/api/generate", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

/** Triggers a browser download of an already-constructed Blob as `filename`. */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Triggers a browser download of `content` as a CSV file named `filename`. */
function triggerCsvDownload(content: string, filename: string): void {
  triggerBlobDownload(
    new Blob([content], { type: "text/csv;charset=utf-8;" }),
    filename,
  );
}

/**
 * Downloads the customer-facing draft cheat-sheet as a multi-tab workbook
 * `tiers.xlsx`: an "All" sheet plus one sheet per position that has players.
 * Async because workbook construction (write-excel-file) is async.
 */
export async function downloadDraftXlsx(
  players: TieredPlayer[],
  scoringFormat: ScoringFormat,
  tierLabelOverrides?: Partial<Record<number, string>>,
): Promise<void> {
  const options: DraftCsvOptions = { scoringFormat, tierLabelOverrides };
  // Lazy-load the workbook builder (and the ~20 kB-gzip write-excel-file library
  // it pulls in) so it is code-split into its own async chunk and only fetched
  // when the user actually clicks Download Excel — keeping it out of the main
  // initial-load bundle. Do not convert this back to a static import.
  const { buildDraftXlsxBlob } = await import("@/lib/xlsx");
  const blob = await buildDraftXlsxBlob(players, options);
  triggerBlobDownload(blob, "tiers.xlsx");
}

/** Downloads the full debug CSV as `tiers-debug.csv` (dev-only, ?debug=1). */
export function downloadDebugCsv(
  players: TieredPlayer[],
  tierLabelOverrides?: Partial<Record<number, string>>,
): void {
  const csv = generateDebugCsvString(players, tierLabelOverrides);
  triggerCsvDownload(csv, "tiers-debug.csv");
}
