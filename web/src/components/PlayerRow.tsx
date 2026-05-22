import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TieredPlayer } from "@/api/types";

interface PlayerRowProps {
  player: TieredPlayer;
}

export function PlayerRow({ player }: PlayerRowProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-md hover:bg-muted/50 transition-colors">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-3 py-2 text-sm text-left"
        aria-expanded={expanded}
        aria-label={`Toggle details for ${player.name}`}
      >
        <span className="w-8 text-right font-mono text-muted-foreground">{player.overall_rank}</span>
        <span className="flex-1 truncate font-medium">{player.name}</span>
        <span className="w-12 text-xs text-muted-foreground">{player.team ?? "—"}</span>
        <span className="w-12 text-right font-mono">{player.adjusted_score.toFixed(1)}</span>
        <ChevronDown
          className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")}
        />
      </button>
      {expanded && (
        <div className="px-3 pb-3 pt-1 space-y-3 text-xs border-t bg-muted/20">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <div className="text-muted-foreground">Position tier</div>
              <div className="font-medium">{player.positional_tier}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Position</div>
              <div className="font-medium">{player.position}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Age</div>
              <div className="font-medium">{player.age ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Projected (raw)</div>
              <div className="font-medium font-mono">{player.projected_score_raw.toFixed(1)}</div>
            </div>
            {player.prior_year_actual !== null && (
              <div>
                <div className="text-muted-foreground">Prior year actual</div>
                <div className="font-medium font-mono">{player.prior_year_actual.toFixed(1)}</div>
              </div>
            )}
            <div>
              <div className="text-muted-foreground">ADP (standard)</div>
              <div className="font-medium">{player.adp_standard ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">ADP (PPR)</div>
              <div className="font-medium">{player.adp_ppr ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">ADP (dynasty)</div>
              <div className="font-medium">{player.adp_dynasty ?? "—"}</div>
            </div>
          </div>
          {player.flags.length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1">Flags</div>
              <div className="flex flex-wrap gap-1">
                {player.flags.map((f) => (
                  <span key={f} className="rounded bg-yellow-100 text-yellow-800 px-1.5 py-0.5">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}
          {player.rules_applied.length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1">Rules applied</div>
              <ul className="list-disc list-inside space-y-0.5">
                {player.rules_applied.map((r) => <li key={r}>{r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
