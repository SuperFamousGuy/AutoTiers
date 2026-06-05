import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { TEAM_FULL_NAME, TEAM_TINT_COLORS, hexToRgb } from "@/lib/teams";
import { teamLogoUrl } from "@/lib/espn-cdn";
import type { TieredPlayer } from "@/api/types";

const POSITION_COLORS: Record<string, string> = {
  QB:  "#60a5fa",
  RB:  "#fb923c",
  WR:  "#4ade80",
  TE:  "#fbbf24",
  K:   "#94a3b8",
  DST: "#c084fc",
  DEF: "#c084fc",
};

function positionColor(position: string): string {
  return POSITION_COLORS[position] ?? "#94a3b8";
}

interface PlayerCardProps {
  player: TieredPlayer;
}

export function PlayerCard({ player }: PlayerCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [imgError, setImgError] = useState(false);

  const posColor = positionColor(player.position);
  const teamTint = player.team ? TEAM_TINT_COLORS[player.team] : null;
  const teamRgb = teamTint ? hexToRgb(teamTint) : null;
  const fullTeamName = player.team ? (TEAM_FULL_NAME[player.team] ?? player.team) : "—";

  const isFavPlayer = player.is_favorite_player === true;
  const isFavTeam = player.is_favorite_team === true;

  const cardStyle: React.CSSProperties =
    isFavTeam && teamRgb
      ? {
          backgroundColor: `rgba(${teamRgb}, 0.10)`,
          borderColor: `rgba(${teamRgb}, 0.35)`,
        }
      : {};

  const posRgb = hexToRgb(posColor);

  return (
    <div
      className="rounded-lg border border-l-4 transition-colors"
      style={{ ...cardStyle, borderLeftColor: posColor }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-sm text-left"
        aria-expanded={expanded}
        aria-label={`Toggle details for ${player.name}`}
      >
        {/* Rank */}
        <span
          className="w-6 text-right font-bold shrink-0"
          style={{ color: posColor }}
        >
          {player.overall_rank}
        </span>

        {/* Headshot */}
        {!imgError ? (
          <img
            src={`https://sleepercdn.com/content/nfl/players/thumb/${player.player_id}.jpg`}
            onError={() => setImgError(true)}
            alt={player.name}
            className="w-11 h-11 rounded-full object-cover object-top shrink-0"
            style={{ border: `2px solid ${posColor}` }}
          />
        ) : (
          <div
            className="w-11 h-11 rounded-full shrink-0 flex items-center justify-center text-[11px] font-bold"
            style={{
              border: `2px solid ${posColor}`,
              color: posColor,
              backgroundColor: `rgba(${posRgb}, 0.12)`,
            }}
          >
            {player.position}
          </div>
        )}

        {/* Name + subtitle */}
        <div className="flex-1 min-w-0">
          <div className="font-bold text-sm flex items-center gap-1 flex-wrap">
            <span className="truncate">{player.name}</span>
            {isFavPlayer && <span className="shrink-0">⭐</span>}
            {isFavTeam && player.team && (
              <img
                src={teamLogoUrl(player.team)}
                alt={fullTeamName}
                loading="lazy"
                decoding="async"
                className="w-[17px] h-[17px] rounded-sm object-contain shrink-0 opacity-90"
              />
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {player.position} · <span>{fullTeamName}</span>
          </div>
        </div>

        {/* Team logo + VBD */}
        <div className="flex items-center gap-2.5 shrink-0">
          {player.team && (
            <img
              src={teamLogoUrl(player.team)}
              alt={fullTeamName}
              aria-hidden="true"
              loading="lazy"
              decoding="async"
              className="w-7 h-7 rounded object-contain"
            />
          )}
          <div className="text-right">
            <div
              className="text-lg font-black leading-none"
              style={{ color: posColor }}
            >
              {player.vbd_score.toFixed(1)}
            </div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-wide">VBD</div>
          </div>
        </div>

        {/* Chevron */}
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform shrink-0",
            expanded && "rotate-180"
          )}
        />
      </button>

      {/* Expanded detail panel */}
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
              {player.avg_projection !== null && (
                <div className="flex justify-between">
                  <span>Avg projection (all sources)</span>
                  <span>{player.avg_projection.toFixed(1)}</span>
                </div>
              )}
              <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                <span>Blended raw</span>
                <span>{player.projected_score_raw.toFixed(1)}</span>
              </div>
            </div>
          </div>

          {/* Rule adjustments */}
          {(() => {
            const scoringApps = player.rule_applications.filter(
              (a) => a.effect_type !== "flag"
            );
            if (scoringApps.length === 0) {
              return (
                <div className="text-muted-foreground italic">
                  No score adjustments (adjusted = blended)
                </div>
              );
            }
            return (
              <div>
                <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
                  Rule adjustments
                </div>
                <div className="space-y-0.5 font-mono">
                  {scoringApps.map((app, i) => (
                    <div key={i} className="flex justify-between">
                      <span className="truncate pr-2">{app.name}</span>
                      <span
                        className={cn(
                          app.delta > 0 && "text-green-700 dark:text-green-400",
                          app.delta < 0 && "text-red-700 dark:text-red-400"
                        )}
                      >
                        {`${app.delta > 0 ? "+" : ""}${app.delta.toFixed(1)}`}
                        <span className="text-muted-foreground ml-2">
                          → {app.after_score.toFixed(1)}
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                    <span>Adjusted score</span>
                    <span>{player.adjusted_score.toFixed(1)}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Value-Based Drafting */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Value-Based Drafting (vs position replacement)
            </div>
            <div className="space-y-0.5 font-mono">
              <div className="flex justify-between">
                <span>Adjusted score</span>
                <span>{player.adjusted_score.toFixed(1)}</span>
              </div>
              <div className="flex justify-between">
                <span>Replacement ({player.position})</span>
                <span>−{player.position_replacement.toFixed(1)}</span>
              </div>
              <div className="flex justify-between border-t mt-1 pt-1 font-semibold">
                <span>VBD score</span>
                <span>{player.vbd_score.toFixed(1)}</span>
              </div>
            </div>
          </div>

          {/* Flags */}
          {player.flags.length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
                Flags
              </div>
              <div className="flex flex-wrap gap-1">
                {player.flags.map((f) => (
                  <span
                    key={f}
                    className="rounded bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300 px-1.5 py-0.5"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Tier placement */}
          <div>
            <div className="text-muted-foreground mb-1 font-semibold uppercase tracking-wider text-[10px]">
              Tier placement
            </div>
            <div className="flex gap-4">
              <div>
                <div className="text-muted-foreground">Overall</div>
                <div className="font-medium">
                  Tier {player.overall_tier} · #{player.overall_rank}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Positional</div>
                <div className="font-medium">{player.positional_tier}</div>
              </div>
            </div>
          </div>

          {/* Reference */}
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
        </div>
      )}
    </div>
  );
}
