import { PlayerRow } from "./PlayerRow";
import type { TieredPlayer } from "@/api/types";

interface TierGroupProps {
  tier: number;
  players: TieredPlayer[];
}

export function TierGroup({ tier, players }: TierGroupProps) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground py-1">
        ── Tier {tier} ──
      </div>
      {players.map((p) => (
        <PlayerRow key={p.player_id} player={p} />
      ))}
    </div>
  );
}
