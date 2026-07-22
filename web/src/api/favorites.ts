import { apiFetch } from "@/api/client";
import type { PlayerSearchResult } from "@/api/types";

export async function searchPlayers(q: string): Promise<PlayerSearchResult[]> {
  const params = new URLSearchParams({ q });
  return apiFetch<PlayerSearchResult[]>(`/api/players/search?${params.toString()}`);
}

export async function batchPlayers(ids: string[]): Promise<PlayerSearchResult[]> {
  if (ids.length === 0) return [];
  const params = new URLSearchParams({ ids: ids.join(",") });
  return apiFetch<PlayerSearchResult[]>(`/api/players/batch?${params.toString()}`);
}
