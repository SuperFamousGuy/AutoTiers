import { useCallback, useEffect, useState } from "react";
import { getFavorites, putFavorites } from "@/api/favorites";
import type { FavoritesOut, FavoritesUpdate } from "@/api/types";

const EMPTY: FavoritesOut = { favorite_player_ids: [], favorite_teams: [] };

interface UseFavoritesResult {
  favorites: FavoritesOut;
  loading: boolean;
  error: string | null;
  save: (next: FavoritesUpdate) => Promise<void>;
}

/**
 * Hook for the current user's favorites. Pass `authenticated=true` only when
 * the user is logged in (typically `user !== null` from AuthContext). When
 * unauthenticated, no fetch fires and `favorites` stays the empty default.
 *
 * `save` is optimistic: the local `favorites` state updates immediately and
 * reverts on server error.
 */
export function useFavorites(authenticated: boolean): UseFavoritesResult {
  const [favorites, setFavorites] = useState<FavoritesOut>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authenticated) {
      setFavorites(EMPTY);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getFavorites()
      .then((fav) => {
        if (!cancelled) setFavorites(fav);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message ?? "Failed to load favorites");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated]);

  const save = useCallback(async (next: FavoritesUpdate) => {
    const prev = favorites;
    setFavorites(next);            // optimistic
    try {
      const persisted = await putFavorites(next);
      setFavorites(persisted);     // accept server's normalized version (dedup, etc.)
    } catch (e) {
      setFavorites(prev);          // revert
      throw e;                     // caller (FavoritesPanel.commit) handles save-error UI
    }
  }, [favorites]);

  return { favorites, loading, error, save };
}
