import { useCallback, useEffect, useState } from "react";

const STORAGE_PREFIX = "autotiers_draft:";

// Mirrors the graceful-degradation pattern in useDarkMode / useOnboarding:
// try/catch around all localStorage access. If storage is blocked (private
// browsing, quota, disabled), Draft Mode still works for the current session
// — it just doesn't persist across reloads.
function readDrafted(storageKey: string): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + storageKey);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((id): id is string => typeof id === "string"));
  } catch {
    // storage blocked or corrupt JSON — start with an empty (in-memory-only) set
    return new Set();
  }
}

function persistDrafted(storageKey: string, drafted: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + storageKey, JSON.stringify([...drafted]));
  } catch {
    // storage blocked — draft picks not persisted; session-only.
  }
}

/**
 * Draft Mode state — tracks which players have been marked drafted, keyed by
 * `storageKey` (typically `${leagueKey}:${scoringFormat}` so switching leagues
 * or scoring formats doesn't bleed drafted state across contexts).
 *
 * Tiers never renumber and drafted players are never removed from the list —
 * this hook only tracks membership in the drafted set; the caller (TierGroup)
 * decides how to visually sink/dim drafted rows.
 */
export function useDraftBoard(storageKey: string) {
  const [drafted, setDrafted] = useState<Set<string>>(() => readDrafted(storageKey));

  // Re-seed from storage whenever the caller switches context (league or
  // scoring format changes) so drafted state doesn't leak between contexts.
  useEffect(() => {
    setDrafted(readDrafted(storageKey));
  }, [storageKey]);

  // Persist on every change. Skipped on the initial mount's first render is
  // unnecessary — re-writing the same value we just read is harmless and
  // keeps this effect simple.
  useEffect(() => {
    persistDrafted(storageKey, drafted);
  }, [storageKey, drafted]);

  const isDrafted = useCallback((id: string) => drafted.has(id), [drafted]);

  const toggleDrafted = useCallback((id: string) => {
    setDrafted((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setDrafted(new Set());
  }, []);

  return {
    drafted,
    draftedCount: drafted.size,
    isDrafted,
    toggleDrafted,
    reset,
  } as const;
}
