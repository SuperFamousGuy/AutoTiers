import type { TieredPlayer } from "@/api/types";

interface PlayerRowProps {
  player: TieredPlayer;
}

export function PlayerRow({ player }: PlayerRowProps) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 hover:bg-muted/50 rounded-md text-sm">
      <span className="w-8 text-right font-mono text-muted-foreground">{player.overall_rank}</span>
      <span className="flex-1 truncate font-medium">{player.name}</span>
      <span className="w-16 text-xs text-muted-foreground">{player.positional_tier}</span>
      <span className="w-12 text-xs text-muted-foreground">{player.team ?? "—"}</span>
      <span className="w-10 text-right font-mono">{player.adjusted_score.toFixed(1)}</span>
      {player.flags.length > 0 && (
        <span className="flex flex-wrap gap-1">
          {player.flags.map((f) => (
            <span key={f} className="rounded bg-yellow-100 text-yellow-800 px-1.5 py-0.5 text-xs">
              {f}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}
