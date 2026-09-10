import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { TeamLogo } from "@/components/TeamLogo";
import type { PlayerSearchResult } from "@/api/types";
import { NFL_CONFERENCES } from "@/lib/teams";

const PLAYER_CAP = 20;
const TEAM_CAP = 4;
const SEARCH_DEBOUNCE_MS = 300;

interface FavoritesPanelProps {
  favoritePlayerIds: string[];
  favoriteTeams: string[];
  onTogglePlayer: (id: string) => void;
  onToggleTeam: (code: string) => void;
  searchPlayers: (q: string) => Promise<PlayerSearchResult[]>;
  batchPlayers: (ids: string[]) => Promise<PlayerSearchResult[]>;
}

/**
 * Favorites live in `localStorage` (useLocalFavorites) — every toggle here is
 * synchronous and can't fail, so unlike the old server-backed panel there is
 * no loading/error/retry state and no optimistic-revert copy.
 */
export function FavoritesPanel({
  favoritePlayerIds,
  favoriteTeams,
  onTogglePlayer,
  onToggleTeam,
  searchPlayers,
  batchPlayers,
}: FavoritesPanelProps) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const resolvedPlayers = useRef<Record<string, PlayerSearchResult>>({});

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
        for (const p of r) resolvedPlayers.current[p.id] = p;
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

  useEffect(() => {
    const unresolved = favoritePlayerIds.filter((id) => !(id in resolvedPlayers.current));
    if (unresolved.length === 0) return;
    let cancelled = false;
    setBatchLoading(true);
    batchPlayers(unresolved)
      .then((results) => {
        if (cancelled) return;
        for (const p of results) resolvedPlayers.current[p.id] = p;
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setBatchLoading(false);
      });
    return () => { cancelled = true; setBatchLoading(false); };
  }, [favoritePlayerIds, batchPlayers]);

  const playersAtCap = favoritePlayerIds.length >= PLAYER_CAP;
  const teamsAtCap = favoriteTeams.length >= TEAM_CAP;

  const resolvedPlayer = (id: string): PlayerSearchResult | undefined =>
    resolvedPlayers.current[id];

  return (
    <div className="space-y-6 p-4">
      <section data-testid="player-favorites" data-batchloading={String(batchLoading)}>
        <header className="flex items-center justify-between mb-2">
          <h3 className="font-medium">Favorite Players</h3>
          <span className={`text-xs ${playersAtCap ? "text-amber-800 dark:text-amber-500" : "text-muted-foreground"}`}>
            {favoritePlayerIds.length} / {PLAYER_CAP}
          </span>
        </header>

        {favoritePlayerIds.length === 0 ? (
          <p className="text-sm text-muted-foreground mb-3">
            No favorite players yet. Search below to add one.
          </p>
        ) : batchLoading ? (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 mb-3">
            {favoritePlayerIds.map((id) => (
              <li key={id} className="flex items-center gap-3 rounded-lg border bg-card p-3 animate-pulse">
                <div className="h-12 w-12 shrink-0 rounded-md bg-muted" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-3/4 rounded bg-muted" />
                  <div className="h-3 w-1/2 rounded bg-muted" />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 mb-3">
            {favoritePlayerIds.map((id) => {
              const player = resolvedPlayer(id);
              return (
                <li
                  key={id}
                  className="relative flex items-center gap-3 rounded-lg border bg-card p-3"
                >
                  <PlayerHeadshot espnId={player?.espn_id ?? null} name={player?.name ?? id} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{player?.name ?? id}</p>
                    <p className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span>{player?.position ?? "—"}</span>
                      {player?.team && (
                        <>
                          <span aria-hidden="true">·</span>
                          <TeamLogo code={player.team} size={16} />
                          <span>{player.team}</span>
                        </>
                      )}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onTogglePlayer(id)}
                    aria-label={`Remove ${player?.name ?? id}`}
                    className="absolute right-1 top-1 h-6 w-6 p-0"
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </Button>
                </li>
              );
            })}
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
          <p className="text-xs text-amber-800 dark:text-amber-500 mt-1">
            Limit reached ({PLAYER_CAP} players). Remove one to add another.
          </p>
        )}

        <ul className="mt-2 space-y-1">
          {searched && results.length === 0 && (
            <li className="text-sm text-muted-foreground">No players match "{debouncedQuery}".</li>
          )}
          {results.map((p) => {
            const isFav = favoritePlayerIds.includes(p.id);
            return (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <span>{p.name} ({p.position}{p.team ? ` · ${p.team}` : ""})</span>
                <Button
                  type="button"
                  variant={isFav ? "ghost" : "outline"}
                  size="sm"
                  onClick={() => onTogglePlayer(p.id)}
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
          <span className={`text-xs ${teamsAtCap ? "text-amber-800 dark:text-amber-500" : "text-muted-foreground"}`}>
            {favoriteTeams.length} / {TEAM_CAP}
          </span>
        </header>
        {teamsAtCap && (
          <p className="text-xs text-amber-800 dark:text-amber-500 mb-1">
            Limit reached ({TEAM_CAP} teams). Remove one to add another.
          </p>
        )}
        {favoriteTeams.length === 0 && (
          <p className="text-sm text-muted-foreground mb-2">
            No favorite teams yet. Select up to {TEAM_CAP} teams.
          </p>
        )}
        <div className="space-y-5">
          {NFL_CONFERENCES.map((conf) => (
            <div key={conf.conference}>
              <h4 className="mb-2 text-sm font-bold text-foreground">{conf.conference}</h4>
              <div className="space-y-3">
                {conf.divisions.map((div) => (
                  <div key={div.division}>
                    <h5 className="mb-1 text-xs font-semibold text-muted-foreground">{div.division}</h5>
                    <div className="grid grid-cols-4 gap-2">
                      {div.teams.map((team) => {
                        const isFav = favoriteTeams.includes(team.code);
                        return (
                          <Button
                            key={team.code}
                            type="button"
                            variant={isFav ? "default" : "outline"}
                            size="sm"
                            onClick={() => onToggleTeam(team.code)}
                            disabled={!isFav && teamsAtCap}
                            aria-label={team.name}
                            aria-pressed={isFav}
                            className="flex flex-col items-center gap-0.5 h-auto py-1.5"
                          >
                            <TeamLogo code={team.code} size={24} />
                            <span className="text-[10px] leading-none">{team.code}</span>
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
