import { useEffect, useState } from "react";
import type { FavoritesOut, FavoritesUpdate, PlayerSearchResult } from "@/api/types";

const NFL_TEAMS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB",  "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV",  "MIA", "MIN", "NE",  "NO",  "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF",  "TB",  "TEN", "WAS",
] as const;

const PLAYER_CAP = 20;
const TEAM_CAP = 4;

interface FavoritesPanelProps {
  favorites: FavoritesOut;
  onSave: (next: FavoritesUpdate) => Promise<void>;
  searchPlayers: (q: string) => Promise<PlayerSearchResult[]>;
}

export function FavoritesPanel({ favorites, onSave, searchPlayers }: FavoritesPanelProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    searchPlayers(query.trim()).then((r) => {
      if (!cancelled) setResults(r);
    }).catch(() => {
      if (!cancelled) setResults([]);
    });
    return () => { cancelled = true; };
  }, [query, searchPlayers]);

  const playersAtCap = favorites.favorite_player_ids.length >= PLAYER_CAP;
  const teamsAtCap = favorites.favorite_teams.length >= TEAM_CAP;

  const togglePlayer = (id: string) => {
    const isFav = favorites.favorite_player_ids.includes(id);
    if (isFav) {
      void onSave({
        favorite_player_ids: favorites.favorite_player_ids.filter((x) => x !== id),
        favorite_teams: favorites.favorite_teams,
      });
    } else if (!playersAtCap) {
      void onSave({
        favorite_player_ids: [...favorites.favorite_player_ids, id],
        favorite_teams: favorites.favorite_teams,
      });
    }
  };

  const toggleTeam = (team: string) => {
    const isFav = favorites.favorite_teams.includes(team);
    if (isFav) {
      void onSave({
        favorite_player_ids: favorites.favorite_player_ids,
        favorite_teams: favorites.favorite_teams.filter((t) => t !== team),
      });
    } else if (!teamsAtCap) {
      void onSave({
        favorite_player_ids: favorites.favorite_player_ids,
        favorite_teams: [...favorites.favorite_teams, team],
      });
    }
  };

  return (
    <div className="space-y-6 p-4">
      <section>
        <header className="flex items-center justify-between mb-2">
          <h3 className="font-medium">Favorite Players</h3>
          <span className={`text-xs ${playersAtCap ? "text-amber-600" : "text-muted-foreground"}`}>
            {favorites.favorite_player_ids.length} / {PLAYER_CAP}
          </span>
        </header>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search players…"
          className="w-full border rounded px-3 py-2 text-sm"
        />
        {playersAtCap && (
          <p className="text-xs text-amber-700 mt-1">
            Limit reached ({PLAYER_CAP} players). Remove one to add another.
          </p>
        )}
        <ul className="mt-2 space-y-1">
          {results.length === 0 && favorites.favorite_player_ids.length === 0 && !query && (
            <li className="text-sm text-muted-foreground">No favorite players yet. Search above to add one.</li>
          )}
          {results.map((p) => {
            const isFav = favorites.favorite_player_ids.includes(p.id);
            return (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <span>{p.name} ({p.position}{p.team ? ` · ${p.team}` : ""})</span>
                <button
                  type="button"
                  onClick={() => togglePlayer(p.id)}
                  disabled={!isFav && playersAtCap}
                  aria-label={isFav ? `Remove ${p.name}` : `Add ${p.name}`}
                  className="px-2 py-1 text-xs border rounded"
                >
                  {isFav ? "Remove" : "Add"}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <header className="flex items-center justify-between mb-2">
          <h3 className="font-medium">Favorite Teams</h3>
          <span className={`text-xs ${teamsAtCap ? "text-amber-600" : "text-muted-foreground"}`}>
            {favorites.favorite_teams.length} / {TEAM_CAP}
          </span>
        </header>
        {teamsAtCap && (
          <p className="text-xs text-amber-700 mb-1">
            Limit reached ({TEAM_CAP} teams). Remove one to add another.
          </p>
        )}
        {favorites.favorite_teams.length === 0 && (
          <p className="text-sm text-muted-foreground mb-2">
            No favorite teams yet. Select up to {TEAM_CAP} teams.
          </p>
        )}
        <div className="grid grid-cols-8 gap-2">
          {NFL_TEAMS.map((team) => {
            const isFav = favorites.favorite_teams.includes(team);
            const disabled = !isFav && teamsAtCap;
            return (
              <button
                key={team}
                type="button"
                onClick={() => toggleTeam(team)}
                disabled={disabled}
                aria-label={`team-${team}`}
                aria-pressed={isFav}
                className={`px-2 py-1 text-xs border rounded ${
                  isFav ? "bg-primary text-primary-foreground" : disabled ? "opacity-40" : ""
                }`}
              >
                {team}
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
