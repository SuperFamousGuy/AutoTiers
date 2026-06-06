import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { generateCsvString } from "@/lib/csv";
import type {
  DataStatusResponse,
  GenerateRequest,
  GenerateResponse,
  Rule,
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

export function downloadCsv(
  players: TieredPlayer[],
  tierLabelOverrides?: Partial<Record<number, string>>,
): void {
  const csv = generateCsvString(players, tierLabelOverrides);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tiers.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
