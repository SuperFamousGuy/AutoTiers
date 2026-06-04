import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { FavoritesOut, FavoritesUpdate, PlayerSearchResult } from "@/api/types";

const NFL_DIVISIONS: { division: string; teams: { code: string; name: string }[] }[] = [
  { division: "AFC East", teams: [
    { code: "BUF", name: "Buffalo Bills" }, { code: "MIA", name: "Miami Dolphins" },
    { code: "NE", name: "New England Patriots" }, { code: "NYJ", name: "New York Jets" },
  ] },
  { division: "AFC North", teams: [
    { code: "BAL", name: "Baltimore Ravens" }, { code: "CIN", name: "Cincinnati Bengals" },
    { code: "CLE", name: "Cleveland Browns" }, { code: "PIT", name: "Pittsburgh Steelers" },
  ] },
  { division: "AFC South", teams: [
    { code: "HOU", name: "Houston Texans" }, { code: "IND", name: "Indianapolis Colts" },
    { code: "JAX", name: "Jacksonville Jaguars" }, { code: "TEN", name: "Tennessee Titans" },
  ] },
  { division: "AFC West", teams: [
    { code: "DEN", name: "Denver Broncos" }, { code: "KC", name: "Kansas City Chiefs" },
    { code: "LV", name: "Las Vegas Raiders" }, { code: "LAC", name: "Los Angeles Chargers" },
  ] },
  { division: "NFC East", teams: [
    { code: "DAL", name: "Dallas Cowboys" }, { code: "NYG", name: "New York Giants" },
    { code: "PHI", name: "Philadelphia Eagles" }, { code: "WAS", name: "Washington Commanders" },
  ] },
  { division: "NFC North", teams: [
    { code: "CHI", name: "Chicago Bears" }, { code: "DET", name: "Detroit Lions" },
    { code: "GB", name: "Green Bay Packers" }, { code: "MIN", name: "Minnesota Vikings" },
  ] },
  { division: "NFC South", teams: [
    { code: "ATL", name: "Atlanta Falcons" }, { code: "CAR", name: "Carolina Panthers" },
    { code: "NO", name: "New Orleans Saints" }, { code: "TB", name: "Tampa Bay Buccaneers" },
  ] },
  { division: "NFC West", teams: [
    { code: "ARI", name: "Arizona Cardinals" }, { code: "LAR", name: "Los Angeles Rams" },
    { code: "SF", name: "San Francisco 49ers" }, { code: "SEA", name: "Seattle Seahawks" },
  ] },
];

const TEAM_NAME: Record<string, string> = Object.fromEntries(
  NFL_DIVISIONS.flatMap((d) => d.teams.map((t) => [t.code, t.name])),
);

const PLAYER_CAP = 20;
const TEAM_CAP = 4;
const SEARCH_DEBOUNCE_MS = 300;

interface FavoritesPanelProps {
  favorites: FavoritesOut;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onSave: (next: FavoritesUpdate) => Promise<void>;
  searchPlayers: (q: string) => Promise<PlayerSearchResult[]>;
}

export function FavoritesPanel({
  favorites,
  loading = false,
  error = null,
  onRetry,
  onSave,
  searchPlayers,
}: FavoritesPanelProps) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const playerNames = useRef<Record<string, string>>({});

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(query.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      setSearched(false);
      return;
    }
    let cancelled = false;
    searchPlayers(debouncedQuery)
      .then((r) => {
        if (cancelled) return;
        for (const p of r) playerNames.current[p.id] = p.name;
        setResults(r);
        setSearched(true);
      })
      .catch(() => {
        if (cancelled) return;
        setResults([]);
        setSearched(true);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, searchPlayers]);

  const playersAtCap = favorites.favorite_player_ids.length >= PLAYER_CAP;
  const teamsAtCap = favorites.favorite_teams.length >= TEAM_CAP;

  const commit = (next: FavoritesUpdate) => {
    setSaveError(null);
    onSave(next).catch(() => {
      setSaveError("Couldn't save your change — it was reverted. Please try again.");
    });
  };

  const playerLabel = (id: string) => playerNames.current[id] ?? id;

  const addPlayer = (id: string) => {
    if (favorites.favorite_player_ids.includes(id) || playersAtCap) return;
    commit({
      favorite_player_ids: [...favorites.favorite_player_ids, id],
      favorite_teams: favorites.favorite_teams,
    });
  };

  const removePlayer = (id: string) => {
    commit({
      favorite_player_ids: favorites.favorite_player_ids.filter((x) => x !== id),
      favorite_teams: favorites.favorite_teams,
    });
  };

  const toggleTeam = (team: string) => {
    const isFav = favorites.favorite_teams.includes(team);
    if (isFav) {
      commit({
        favorite_player_ids: favorites.favorite_player_ids,
        favorite_teams: favorites.favorite_teams.filter((t) => t !== team),
      });
    } else if (!teamsAtCap) {
      commit({
        favorite_player_ids: favorites.favorite_player_ids,
        favorite_teams: [...favorites.favorite_teams, team],
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        <span role="status">Loading favorites…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 p-8 text-center">
        <p className="text-sm text-destructive">{error}</p>
        {onRetry && (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4">
      {saveError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {saveError}
        </p>
      )}

      <section>
        <header className="flex items-center justify-between mb-2">
          <h3 className="font-medium">Favorite Players</h3>
          <span className={`text-xs ${playersAtCap ? "text-amber-600" : "text-muted-foreground"}`}>
            {favorites.favorite_player_ids.length} / {PLAYER_CAP}
          </span>
        </header>

        {favorites.favorite_player_ids.length === 0 ? (
          <p className="text-sm text-muted-foreground mb-3">
            No favorite players yet. Search below to add one.
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2 mb-3">
            {favorites.favorite_player_ids.map((id) => (
              <li key={id}>
                <span className="inline-flex items-center gap-1 rounded-full border bg-secondary px-3 py-1 text-xs">
                  {playerLabel(id)}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removePlayer(id)}
                    aria-label={`Remove ${playerLabel(id)}`}
                    className="h-4 w-4 p-0 leading-none"
                  >
                    ×
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <Input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search players…"
          aria-label="Search players"
        />
        {playersAtCap && (
          <p className="text-xs text-amber-700 mt-1">
            Limit reached ({PLAYER_CAP} players). Remove one to add another.
          </p>
        )}

        <ul className="mt-2 space-y-1">
          {searched && results.length === 0 && (
            <li className="text-sm text-muted-foreground">No players match "{debouncedQuery}".</li>
          )}
          {results.map((p) => {
            const isFav = favorites.favorite_player_ids.includes(p.id);
            return (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <span>{p.name} ({p.position}{p.team ? ` · ${p.team}` : ""})</span>
                <Button
                  type="button"
                  variant={isFav ? "ghost" : "outline"}
                  size="sm"
                  onClick={() => (isFav ? removePlayer(p.id) : addPlayer(p.id))}
                  disabled={!isFav && playersAtCap}
                  aria-label={isFav ? `Remove ${p.name}` : `Add ${p.name}`}
                >
                  {isFav ? "Remove" : "Add"}
                </Button>
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
        <div className="space-y-3">
          {NFL_DIVISIONS.map((group) => (
            <div key={group.division}>
              <h4 className="mb-1 text-xs font-semibold text-muted-foreground">{group.division}</h4>
              <div className="grid grid-cols-4 gap-2">
                {group.teams.map((team) => {
                  const isFav = favorites.favorite_teams.includes(team.code);
                  return (
                    <Button
                      key={team.code}
                      type="button"
                      variant={isFav ? "default" : "outline"}
                      size="sm"
                      onClick={() => toggleTeam(team.code)}
                      disabled={!isFav && teamsAtCap}
                      aria-label={team.name}
                      aria-pressed={isFav}
                    >
                      {team.code}
                    </Button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export { TEAM_NAME };
