import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
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

  // Per-tier collapse state. Only meaningful in Draft Mode — outside Draft Mode
  // the tier always renders fully and no toggle is shown.
  //
  // A tier auto-collapses once every player in it is drafted (its dead,
  // struck-through rows stop pushing the next-available tier off-screen on a
  // phone) and auto-expands again the moment a player is undrafted back into it.
  // Between those transitions the user can still collapse/expand manually via
  // the header chevron. We track the previous Draft-Mode and available-count
  // values and adjust `expanded` during render (the React "derived from props"
  // pattern) so the collapse lands in the same commit as the draft toggle —
  // no post-paint flash of the full list.
  const draftActive = draftMode === true;
  const [expanded, setExpanded] = useState(() => !(draftActive && availableCount === 0));
  const [prevDraftActive, setPrevDraftActive] = useState(draftActive);
  const [prevAvailable, setPrevAvailable] = useState(availableCount);

  if (prevDraftActive !== draftActive || prevAvailable !== availableCount) {
    setPrevDraftActive(draftActive);
    setPrevAvailable(availableCount);
    if (!draftActive) {
      // Leaving Draft Mode resets collapse state — the tier is fully expanded
      // again and any manual collapse is forgotten.
      setExpanded(true);
    } else if (!prevDraftActive) {
      // Entering Draft Mode — start collapsed only if the tier is already
      // fully drafted (e.g. restored from a persisted board).
      setExpanded(availableCount > 0);
    } else if (prevAvailable > 0 && availableCount === 0) {
      setExpanded(false); // last available player drafted → auto-collapse
    } else if (prevAvailable === 0 && availableCount > 0) {
      setExpanded(true); // undrafted back into an empty tier → auto-expand
    }
  }

  const showRows = !draftActive || expanded;

  const header = (
    <>
      <span className="text-sm font-bold text-foreground">
        {label}
        {descriptiveLabel && (
          <>
            <span className="mx-1.5 font-normal text-muted-foreground">·</span>
            <span className="font-normal text-muted-foreground">{descriptiveLabel}</span>
          </>
        )}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="text-xs bg-background rounded px-1.5 py-0.5 text-muted-foreground">
          {countShown} {countShown === 1 ? "player" : "players"}
        </span>
        {draftActive && (
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform shrink-0",
              !expanded && "-rotate-90",
            )}
            aria-hidden="true"
          />
        )}
      </span>
    </>
  );

  return (
    <div className="space-y-1">
      {draftActive ? (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-label={`${expanded ? "Collapse" : "Expand"} ${label}`}
          className="flex w-full items-center justify-between bg-muted/60 rounded px-3 py-1.5 my-1 text-left"
        >
          {header}
        </button>
      ) : (
        <div className="flex items-center justify-between bg-muted/60 rounded px-3 py-1.5 my-1">
          {header}
        </div>
      )}
      {showRows &&
        displayPlayers.map((p) => (
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
