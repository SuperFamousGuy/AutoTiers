import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch, API_URL } from "./client";
import type {
  DataStatusResponse,
  GenerateRequest,
  GenerateResponse,
  Rule,
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

export async function downloadCsv(body: GenerateRequest): Promise<void> {
  const resp = await fetch(`${API_URL}/api/generate/csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`CSV download failed: ${resp.status}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tiers.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
