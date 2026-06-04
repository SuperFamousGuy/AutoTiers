import { PlayerRow } from "./PlayerRow";
import type { TieredPlayer } from "@/api/types";

interface TierGroupProps {
  label: string;
  descriptiveLabel?: string;
  players: TieredPlayer[];
}

export function TierGroup({ label, descriptiveLabel, players }: TierGroupProps) {
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
          {players.length} {players.length === 1 ? "player" : "players"}
        </span>
      </div>
      {players.map((p) => (
        <PlayerRow key={p.player_id} player={p} />
      ))}
    </div>
  );
}
