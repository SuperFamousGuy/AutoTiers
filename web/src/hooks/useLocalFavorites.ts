import { useCallback, useEffect, useMemo, useState } from "react";

const KEY = "autotiers.favorites.v1";
const MAX_PLAYERS = 20;
const MAX_TEAMS = 4;

interface Favorites { players: string[]; teams: string[]; }

function load(): Favorites {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { players: [], teams: [] };
    const p = JSON.parse(raw) as Favorites;
    return { players: p.players ?? [], teams: p.teams ?? [] };
  } catch {
    return { players: [], teams: [] };
  }
}

export function useLocalFavorites() {
  const [fav, setFav] = useState<Favorites>(load);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(fav));
  }, [fav]);

  const togglePlayer = useCallback((id: string) => {
    setFav((prev) => {
      if (prev.players.includes(id)) return { ...prev, players: prev.players.filter((x) => x !== id) };
      if (prev.players.length >= MAX_PLAYERS) return prev;
      return { ...prev, players: [...prev.players, id] };
    });
  }, []);

  const toggleTeam = useCallback((abbr: string) => {
    setFav((prev) => {
      if (prev.teams.includes(abbr)) return { ...prev, teams: prev.teams.filter((x) => x !== abbr) };
      if (prev.teams.length >= MAX_TEAMS) return prev;
      return { ...prev, teams: [...prev.teams, abbr] };
    });
  }, []);

  const playerSet = useMemo(() => new Set(fav.players), [fav.players]);
  const teamSet = useMemo(() => new Set(fav.teams), [fav.teams]);

  return {
    players: fav.players,
    teams: fav.teams,
    isFavoritePlayer: (id: string) => playerSet.has(id),
    isFavoriteTeam: (abbr: string) => teamSet.has(abbr),
    togglePlayer,
    toggleTeam,
  };
}
