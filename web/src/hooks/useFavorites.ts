import { useCallback, useEffect, useRef, useState } from "react";
import { getFavorites, putFavorites } from "@/api/favorites";
import { createSingleFlight, type SerializedWrite } from "@/lib/singleFlight";
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

  // Last state the server confirmed (initial load or a successful PUT). A failed
  // write rolls back to this real server truth rather than to a captured local
  // snapshot, which could itself be a not-yet-persisted optimistic value.
  const serverState = useRef<FavoritesOut>(EMPTY);
  // The latest payload the user asked to persist. A settled write only writes
  // its normalized response (or its rollback) back into state while it still
  // matches this — otherwise a newer, queued write is the authority and an older
  // response must not stomp its optimistic state.
  const desired = useRef<FavoritesUpdate | null>(null);

  useEffect(() => {
    if (!authenticated) {
      setFavorites(EMPTY);
      serverState.current = EMPTY;
      desired.current = null;
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getFavorites()
      .then((fav) => {
        if (!cancelled) {
          setFavorites(fav);
          serverState.current = fav;
        }
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

  // PUT /api/favorites is a full-replace and fires on every star-click with no
  // debounce, so two quick clicks would otherwise issue two concurrent PUTs and
  // whichever response the server processed last would win regardless of which
  // click was last — a silent lost update. Single-flight the writes so the
  // server sees one at a time, in causal order, coalescing to the latest.
  const runSave = useRef<SerializedWrite<FavoritesUpdate> | undefined>(undefined);
  if (!runSave.current) {
    runSave.current = createSingleFlight<FavoritesUpdate>(async (_id, next) => {
      const persisted = await putFavorites(next);
      serverState.current = persisted;
      // Only adopt the normalized response when nothing newer is queued; a later
      // edit's optimistic state is the current truth otherwise.
      if (desired.current === next) setFavorites(persisted);
    });
  }

  const save = useCallback(async (next: FavoritesUpdate) => {
    desired.current = next;
    setFavorites(next);            // optimistic — immediate, even while a write is in flight
    try {
      await runSave.current!("favorites", next);
    } catch (e) {
      // Roll back only when this failed write is still the latest desired state;
      // otherwise a newer queued write is already the authority and will
      // reconcile. Revert to the last confirmed server truth.
      if (desired.current === next) {
        desired.current = null;
        setFavorites(serverState.current);
      }
      throw e;                     // caller (FavoritesPanel.commit) handles save-error UI
    }
  }, []);

  return { favorites, loading, error, save };
}
