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
          {/* Score breakdown */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Score breakdown
            </div>
            <div className="space-y-0.5 font-mono">
              {player.prior_year_actual !== null && (
                <div className="flex justify-between">
                  <span>Prior year actual</span>
                  <span>{player.prior_year_actual.toFixed(1)}</span>
                </div>
              )}
              {player.espn_projection !== null && (
                <div className="flex justify-between">
                  <span>ESPN projection</span>
                  <span>{player.espn_projection.toFixed(1)}</span>
                </div>
              )}
              {player.fantasypros_projection !== null && (
                <div className="flex justify-between">
                  <span>FantasyPros consensus</span>
                  <span>{player.fantasypros_projection.toFixed(1)}</span>
                </div>
              )}
              <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                <span>Blended raw</span>
                <span>{player.projected_score_raw.toFixed(1)}</span>
              </div>
            </div>
          </div>

          {/* Rule adjustments */}
          {player.rule_applications.length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
                Rule adjustments
              </div>
              <div className="space-y-0.5 font-mono">
                {player.rule_applications.map((app, i) => (
                  <div key={i} className="flex justify-between">
                    <span className="truncate pr-2">{app.name}</span>
                    <span className={cn(
                      app.effect_type === "flag" && "text-muted-foreground",
                      app.delta > 0 && "text-green-700",
                      app.delta < 0 && "text-red-700",
                    )}>
                      {app.effect_type === "flag" ? "flagged" : `${app.delta > 0 ? "+" : ""}${app.delta.toFixed(1)}`}
                      {app.effect_type !== "flag" && <span className="text-muted-foreground ml-2">→ {app.after_score.toFixed(1)}</span>}
                    </span>
                  </div>
                ))}
                <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                  <span>Adjusted score</span>
                  <span>{player.adjusted_score.toFixed(1)}</span>
                </div>
              </div>
            </div>
          )}

          {player.rule_applications.length === 0 && (
            <div className="text-muted-foreground italic">No rules applied (adjusted = blended)</div>
          )}

          {/* Tier placement */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Tier placement
            </div>
            <div className="flex gap-4">
              <div>
                <div className="text-muted-foreground">Overall</div>
                <div className="font-medium">Tier {player.overall_tier} · #{player.overall_rank}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Positional</div>
                <div className="font-medium">{player.positional_tier}</div>
              </div>
            </div>
          </div>

          {/* Metadata: position, age, ADPs, flags */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Reference
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <div className="text-muted-foreground">Position</div>
                <div>{player.position}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Age</div>
                <div>{player.age ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ADP (standard)</div>
                <div>{player.adp_standard ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ADP (PPR)</div>
                <div>{player.adp_ppr ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ADP (dynasty)</div>
                <div>{player.adp_dynasty ?? "—"}</div>
              </div>
            </div>
          </div>

          {player.flags.length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
                Flags
              </div>
              <div className="flex flex-wrap gap-1">
                {player.flags.map((f) => (
                  <span key={f} className="rounded bg-yellow-100 text-yellow-800 px-1.5 py-0.5">{f}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
