import { useMemo } from "react";
import { PlayerCard } from "./PlayerCard";
import type { TieredPlayer } from "@/api/types";

interface TierGroupProps {
  label: string;
  descriptiveLabel?: string;
  players: TieredPlayer[];
  /** When true, drafted players sink to the bottom of the group and the count badge shows the available count. */
  draftMode?: boolean;
  isDrafted?: (id: string) => boolean;
  onToggleDraft?: (id: string) => void;
}

export function TierGroup({ label, descriptiveLabel, players, draftMode, isDrafted, onToggleDraft }: TierGroupProps) {
  // Tiers never renumber and drafted players are never removed from the DOM.
  // In Draft Mode, undrafted players float to the top of their tier group —
  // a stable sort so within "undrafted" and within "drafted" the original
  // (ranked) order is preserved.
  const displayPlayers = useMemo(() => {
    if (!draftMode || !isDrafted) return players;
    const undrafted: TieredPlayer[] = [];
    const drafted: TieredPlayer[] = [];
    for (const p of players) {
      (isDrafted(p.player_id) ? drafted : undrafted).push(p);
    }
    return [...undrafted, ...drafted];
  }, [players, draftMode, isDrafted]);

  const availableCount = useMemo(() => {
    if (!draftMode || !isDrafted) return players.length;
    return players.filter((p) => !isDrafted(p.player_id)).length;
  }, [players, draftMode, isDrafted]);

  const countShown = draftMode ? availableCount : players.length;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between bg-muted/60 rounded px-3 py-1.5 my-1">
        <span className="text-sm font-bold text-foreground">
          {label}
          {descriptiveLabel && (
            <>
              <span className="mx-1.5 font-normal text-muted-foreground">·</span>
              <span className="font-normal text-muted-foreground">{descriptiveLabel}</span>
            </>
          )}
        </span>
        <span className="text-xs bg-background rounded px-1.5 py-0.5 text-muted-foreground">
          {countShown} {countShown === 1 ? "player" : "players"}
        </span>
      </div>
      {displayPlayers.map((p) => (
        <PlayerCard
          key={p.player_id}
          player={p}
          draftMode={draftMode}
          drafted={isDrafted?.(p.player_id) ?? false}
          onToggleDraft={onToggleDraft}
        />
      ))}
    </div>
  );
}
