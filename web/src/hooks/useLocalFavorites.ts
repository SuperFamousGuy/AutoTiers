import { useCallback, useEffect, useState } from "react";

const KEY = "autotiers.favorites.v1";
const MAX_PLAYERS = 20;
const MAX_TEAMS = 4;

interface Favorites { players: string[]; teams: string[]; }

function read(): Favorites {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { players: [], teams: [] };
    const p = JSON.parse(raw) as Favorites;
    return { players: p.players ?? [], teams: p.teams ?? [] };
  } catch {
    return { players: [], teams: [] };
  }
}

// localStorage is the single source of truth. Every hook instance subscribes to
// this shared listener set, and every write re-notifies all instances to re-read
// — so two independent `useLocalFavorites()` callers (e.g. App's tier-list star
// badges and the Favorites dialog) never drift out of sync within a session.
// We deliberately do NOT cache the value in a module-level variable: reading
// straight from localStorage keeps test isolation intact (a test's
// `localStorage.clear()` is immediately observed by the next mount, with no
// stale singleton to reset).
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((l) => l());
}

function persist(next: Favorites): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage full / disabled (private mode) — favorites are best-effort.
  }
  notify();
}

export function useLocalFavorites() {
  const [fav, setFav] = useState<Favorites>(read);

  useEffect(() => {
    const refresh = () => setFav(read());
    listeners.add(refresh);
    // Cross-tab sync: another tab's write fires a `storage` event here.
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY || e.key === null) refresh();
    };
    window.addEventListener("storage", onStorage);
    // Re-sync on mount in case another instance wrote before this one mounted.
    refresh();
    return () => {
      listeners.delete(refresh);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const togglePlayer = useCallback((id: string) => {
    const cur = read();
    if (cur.players.includes(id)) {
      persist({ ...cur, players: cur.players.filter((x) => x !== id) });
    } else if (cur.players.length < MAX_PLAYERS) {
      persist({ ...cur, players: [...cur.players, id] });
    }
  }, []);

  const toggleTeam = useCallback((abbr: string) => {
    const cur = read();
    if (cur.teams.includes(abbr)) {
      persist({ ...cur, teams: cur.teams.filter((x) => x !== abbr) });
    } else if (cur.teams.length < MAX_TEAMS) {
      persist({ ...cur, teams: [...cur.teams, abbr] });
    }
  }, []);

  return {
    players: fav.players,
    teams: fav.teams,
    isFavoritePlayer: (id: string) => fav.players.includes(id),
    isFavoriteTeam: (abbr: string) => fav.teams.includes(abbr),
    togglePlayer,
    toggleTeam,
  };
}
