import { apiFetch } from "@/api/client";
import type { FavoritesOut, FavoritesUpdate, PlayerSearchResult } from "@/api/types";

export async function getFavorites(): Promise<FavoritesOut> {
  return apiFetch<FavoritesOut>("/api/favorites");
}

export async function putFavorites(body: FavoritesUpdate): Promise<FavoritesOut> {
  return apiFetch<FavoritesOut>("/api/favorites", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function searchPlayers(q: string): Promise<PlayerSearchResult[]> {
  const params = new URLSearchParams({ q });
  return apiFetch<PlayerSearchResult[]>(`/api/players/search?${params.toString()}`);
}

export async function batchPlayers(ids: string[]): Promise<PlayerSearchResult[]> {
  if (ids.length === 0) return [];
  const params = new URLSearchParams({ ids: ids.join(",") });
  return apiFetch<PlayerSearchResult[]>(`/api/players/batch?${params.toString()}`);
}
