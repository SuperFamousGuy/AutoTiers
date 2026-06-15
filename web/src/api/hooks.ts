import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { generateDebugCsvString, generateDraftCsvString } from "@/lib/csv";
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

/** Triggers a browser download of `content` as a file named `filename`. */
function triggerCsvDownload(content: string, filename: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Downloads the customer-facing draft cheat-sheet CSV as `tiers.csv`. */
export function downloadDraftCsv(
  players: TieredPlayer[],
  scoringFormat: ScoringFormat,
  tierLabelOverrides?: Partial<Record<number, string>>,
): void {
  const csv = generateDraftCsvString(players, { scoringFormat, tierLabelOverrides });
  triggerCsvDownload(csv, "tiers.csv");
}

/** Downloads the full debug CSV as `tiers-debug.csv` (dev-only, ?debug=1). */
export function downloadDebugCsv(
  players: TieredPlayer[],
  tierLabelOverrides?: Partial<Record<number, string>>,
): void {
  const csv = generateDebugCsvString(players, tierLabelOverrides);
  triggerCsvDownload(csv, "tiers-debug.csv");
}
