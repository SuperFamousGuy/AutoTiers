import { PlayerRow } from "./PlayerRow";
import type { TieredPlayer } from "@/api/types";

interface TierGroupProps {
  label: string;
  players: TieredPlayer[];
}

export function TierGroup({ label, players }: TierGroupProps) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground py-1">
        ── {label} ──
      </div>
      {players.map((p) => (
        <PlayerRow key={p.player_id} player={p} />
      ))}
    </div>
  );
}
