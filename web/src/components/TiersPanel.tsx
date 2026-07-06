import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, ListChecks } from "lucide-react";
import { PositionFilter, type PositionFilterValue } from "./PositionFilter";
import { TierGroup } from "./TierGroup";
import { getCustomTierLabel, getPositionalTierLabel } from "@/lib/tiers";
import { useDraftBoard } from "@/hooks/useDraftBoard";
import type { GenerateResponse, ScoringFormat } from "@/api/types";

const SCORING_FORMAT_LABELS: Record<ScoringFormat, string> = {
  standard: "Standard",
  half_ppr: "Half PPR",
  ppr: "PPR",
};

interface TiersPanelProps {
  result: GenerateResponse | null;
  isPending: boolean;
  onDownloadXlsx: () => void;
  keepers?: Array<{ player_name: string; position: string; team: string }>;
  scoringFormat?: ScoringFormat;
  tierLabelOverrides?: Partial<Record<number, string>>;
  /** When true, surfaces the dev-only "Download debug CSV" button (?debug=1). */
  debugMode?: boolean;
  onDownloadDebugCsv?: () => void;
  /** Stable id for the linked league (or "default"), used to scope Draft Mode persistence per league + scoring format. */
  leagueKey?: string;
  /** True when settings/rules changed since this list was generated — surfaces the staleness banner (#523). */
  isStale?: boolean;
  /** Regenerate handler invoked from the staleness banner's Generate affordance. */
  onRegenerate?: () => void;
  /** Whether a regenerate is currently allowed (valid weights + rules loaded); disables the banner's Generate button. */
  canRegenerate?: boolean;
}

export function TiersPanel({ result, isPending, onDownloadXlsx, keepers, scoringFormat, tierLabelOverrides, debugMode, onDownloadDebugCsv, leagueKey, isStale, onRegenerate, canRegenerate }: TiersPanelProps) {
  const [filter, setFilter] = useState<PositionFilterValue>("ALL");
  const [draftMode, setDraftMode] = useState(false);

  const draftStorageKey = `${leagueKey ?? "default"}:${scoringFormat ?? "standard"}`;
  const { isDrafted, draftedCount, toggleDrafted, reset: resetDraft, drafted } = useDraftBoard(draftStorageKey);

  // Reset Draft wipes the live drafted-players board (per-league, per-format,
  // persisted to localStorage) with no undo. On a phone during a live draft
  // this button sits next to the frequently-tapped Draft Mode toggle, so gate
  // the wipe behind a confirmation that names the count. When nothing is
  // drafted there is nothing to lose, so skip the prompt and no-op.
  const handleResetDraft = () => {
    if (draftedCount === 0) return;
    const noun = draftedCount === 1 ? "player" : "players";
    if (window.confirm(`Clear all ${draftedCount} drafted ${noun} for this board? This can't be undone.`)) {
      resetDraft();
    }
  };

  const groupedByTier = useMemo(() => {
    if (!result) return [] as { label: string; descriptiveLabel?: string; players: GenerateResponse["players"] }[];
    const filtered = filter === "ALL"
      ? result.players
      : result.players.filter((p) => p.position === filter);

    if (filter === "ALL") {
      // Group by overall_tier
      const m = new Map<number, typeof filtered>();
      for (const p of filtered) {
        if (!m.has(p.overall_tier)) m.set(p.overall_tier, []);
        m.get(p.overall_tier)!.push(p);
      }
      return [...m.entries()]
        .sort(([a], [b]) => a - b)
        .map(([tier, players]) => ({
          label: `Tier ${tier}`,
          descriptiveLabel: getCustomTierLabel(tier, tierLabelOverrides),
          players,
        }));
    } else {
      // Group by positional_tier (e.g., "WR1", "WR2"). Sort by the numeric suffix.
      const m = new Map<string, typeof filtered>();
      for (const p of filtered) {
        if (!m.has(p.positional_tier)) m.set(p.positional_tier, []);
        m.get(p.positional_tier)!.push(p);
      }
      return [...m.entries()]
        .sort(([a], [b]) => {
          const na = parseInt(a.replace(/^[A-Za-z]+/, ""), 10) || 0;
          const nb = parseInt(b.replace(/^[A-Za-z]+/, ""), 10) || 0;
          return na - nb;
        })
        .map(([tier, players]) => ({
          label: tier,
          descriptiveLabel: getPositionalTierLabel(tier),
          players,
        }));
    }
  }, [result, filter, tierLabelOverrides]);

  // For the collapsible "Drafted" list — every drafted player (regardless of
  // the active position filter), in their overall-rank order, so the list is
  // stable even while a position chip is selected.
  const draftedPlayers = useMemo(() => {
    if (!result || draftedCount === 0) return [] as GenerateResponse["players"];
    return result.players.filter((p) => isDrafted(p.player_id));
  }, [result, isDrafted, draftedCount, drafted]);

  if (isPending) {
    return (
      <section className="p-6 overflow-y-auto min-h-0">
        <h2 className="text-lg font-semibold mb-3">Tiers</h2>
        <p className="text-sm text-muted-foreground">Generating tier list…</p>
        <div className="mt-4 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 bg-muted rounded-md animate-pulse" />
          ))}
        </div>
      </section>
    );
  }

  if (!result) {
    return (
      <section className="p-6 min-h-0">
        <h2 className="text-lg font-semibold mb-3">Tiers</h2>
        <p className="text-sm text-muted-foreground">
          Click Generate to build your tier list.
        </p>
      </section>
    );
  }

  return (
    <section className="flex flex-col h-full min-h-0">
      {isStale && (
        <div
          role="status"
          className="flex items-center justify-between gap-3 border-b border-yellow-300 bg-yellow-50 px-4 py-2.5 text-yellow-900 dark:border-yellow-700/60 dark:bg-yellow-950/40 dark:text-yellow-200"
        >
          <p className="min-w-0 flex-1 text-xs">
            Settings changed since this list was generated — regenerate to update.
          </p>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 shrink-0 px-2 text-xs text-yellow-900 hover:bg-yellow-100 hover:text-yellow-900 dark:text-yellow-200 dark:hover:bg-yellow-900/30"
            onClick={onRegenerate}
            disabled={canRegenerate === false}
          >
            Generate
          </Button>
        </div>
      )}
      {keepers && keepers.length > 0 && (
        <div className="border-b px-3 py-2 text-xs text-muted-foreground">
          Excluded Keepers: {keepers.map((k) => k.player_name).join(", ")}
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">Tiers</h2>
            <p className="text-xs text-muted-foreground">
              {scoringFormat ? SCORING_FORMAT_LABELS[scoringFormat] : "Standard"} · {result.total ?? result.players.length} players
              {draftMode && ` · ${draftedCount} drafted`}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {draftMode && (
              <Button
                onClick={handleResetDraft}
                variant="outline"
                size="sm"
              >
                Reset Draft
              </Button>
            )}
            <Button
              onClick={() => setDraftMode((d) => !d)}
              variant={draftMode ? "default" : "outline"}
              size="sm"
              role="switch"
              aria-checked={draftMode}
              aria-label="Draft Mode"
            >
              <ListChecks className="mr-2 h-4 w-4" />
              Draft Mode
            </Button>
          </div>
        </div>
        <PositionFilter value={filter} onChange={setFilter} />
        {draftMode && draftedCount > 0 && (
          <details className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
            <summary className="cursor-pointer font-semibold text-foreground">
              Drafted ({draftedCount})
            </summary>
            <ul className="mt-2 space-y-1">
              {draftedPlayers.map((p) => (
                <li key={p.player_id}>
                  <button
                    type="button"
                    onClick={() => toggleDrafted(p.player_id)}
                    className="text-left text-muted-foreground hover:text-foreground hover:underline"
                  >
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}
        <div className="space-y-4">
          {groupedByTier.map((group) => (
            <TierGroup
              key={group.label}
              label={group.label}
              descriptiveLabel={group.descriptiveLabel}
              players={group.players}
              draftMode={draftMode}
              isDrafted={isDrafted}
              onToggleDraft={toggleDrafted}
            />
          ))}
        </div>
      </div>
      <div className="border-t bg-card px-6 py-3 flex justify-center gap-3">
        <Button data-tour="download" onClick={onDownloadXlsx} variant="default">
          <Download className="mr-2 h-4 w-4" />
          Download Excel
        </Button>
        {debugMode && onDownloadDebugCsv && (
          <Button onClick={onDownloadDebugCsv} variant="outline">
            <Download className="mr-2 h-4 w-4" />
            Download debug CSV
          </Button>
        )}
      </div>
    </section>
  );
}
