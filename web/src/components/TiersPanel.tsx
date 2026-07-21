import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Download, ListChecks, Loader2, X } from "lucide-react";
import { PositionFilter, type PositionFilterValue } from "./PositionFilter";
import { TierGroup } from "./TierGroup";
import { getCustomTierLabel, getPositionalTierLabel } from "@/lib/tiers";
import { describeGenerateError } from "@/lib/errors";
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
  /** True when the last generate failed (500, network blip, weight-tolerance reject, or the 30s client timeout). */
  isError?: boolean;
  /** The error the failed generate threw — used to name the failure in the alert. */
  error?: unknown;
  /**
   * Builds and triggers the Excel download. Returns a promise so the panel can
   * show a busy spinner while the code-split workbook chunk loads + the blob is
   * built, and surface an inline error + Retry if either step rejects (#647).
   * A synchronous handler is still accepted (awaiting a non-promise is a no-op).
   */
  onDownloadXlsx: () => void | Promise<void>;
  scoringFormat?: ScoringFormat;
  tierLabelOverrides?: Partial<Record<number, string>>;
  /** When true, surfaces the dev-only "Download debug CSV" button (?debug=1). */
  debugMode?: boolean;
  onDownloadDebugCsv?: () => void;
  /** localStorage favorites lookups (useLocalFavorites), forwarded down to each PlayerCard. */
  isFavoritePlayer?: (id: string) => boolean;
  isFavoriteTeam?: (code: string) => boolean;
  /** Stable id for the linked league (or "default"), used to scope Draft Mode persistence per league + scoring format. */
  leagueKey?: string;
  /** True when settings/rules changed since this list was generated — surfaces the staleness banner (#523). */
  isStale?: boolean;
  /** Regenerate handler invoked from the staleness banner's Generate affordance. */
  onRegenerate?: () => void;
  /** Whether a regenerate is currently allowed (valid weights + rules loaded); disables the banner's Generate button. */
  canRegenerate?: boolean;
}

export function TiersPanel({ result, isPending, isError, error, onDownloadXlsx, scoringFormat, tierLabelOverrides, debugMode, onDownloadDebugCsv, leagueKey, isStale, onRegenerate, canRegenerate, isFavoritePlayer, isFavoriteTeam }: TiersPanelProps) {
  const [filter, setFilter] = useState<PositionFilterValue>("ALL");
  // Live player-name lookup. With 150-200+ ranked players the position chips
  // alone don't answer "is Player X still on the board / what tier are they in"
  // without scrolling — this composes a case-insensitive substring match on top
  // of the position filter, entirely client-side (no regenerate round-trip) (#708).
  const [search, setSearch] = useState("");
  // Excel export lifecycle. `downloadDraftXlsx` lazy-loads a code-split chunk and
  // then builds the workbook async — either step can reject (offline, a stale
  // chunk hash after a redeploy, a future throw). Track it so the button shows a
  // spinner while pending and an inline error + Retry on failure, instead of the
  // old fire-and-forget rejection that gave the user no feedback at all (#647).
  const [xlsxState, setXlsxState] = useState<"idle" | "pending" | "error">("idle");
  // Whether the inline Reset Draft confirm/cancel affordance is showing. Mirrors
  // ManageProfilesDialog's delete flow: the first click swaps the button for a
  // Confirm/Cancel pair rather than firing a native window.confirm (#731).
  const [confirmingReset, setConfirmingReset] = useState(false);

  const handleDownloadXlsx = async () => {
    setXlsxState("pending");
    try {
      await onDownloadXlsx();
      setXlsxState("idle");
    } catch {
      setXlsxState("error");
    }
  };

  const draftStorageKey = `${leagueKey ?? "default"}:${scoringFormat ?? "standard"}`;
  // draftMode is persisted per-context in useDraftBoard so a reload or remount
  // mid-draft doesn't flip the toggle off and hide the saved picks (#707).
  const { isDrafted, draftedCount, toggleDrafted, reset: resetDraft, drafted, draftMode, setDraftMode } = useDraftBoard(draftStorageKey);

  // Reset Draft wipes the live drafted-players board (per-league, per-format,
  // persisted to localStorage) with no undo. On a phone during a live draft
  // this button sits next to the frequently-tapped Draft Mode toggle, so gate
  // the wipe behind an inline confirm/cancel that names the count (matching the
  // app's ManageProfilesDialog delete flow rather than a native window.confirm
  // that ignores dark mode + app styling and blocks the JS thread — #731). When
  // nothing is drafted there is nothing to lose, so skip the prompt and no-op.
  const handleResetDraft = () => {
    if (draftedCount === 0) return;
    setConfirmingReset(true);
  };

  const handleConfirmReset = () => {
    resetDraft();
    setConfirmingReset(false);
  };

  // Leaving Draft Mode hides the Reset controls entirely, so clear any pending
  // confirm too — otherwise re-enabling Draft Mode would resurface the mid-reset
  // Confirm/Cancel state instead of a fresh "Reset Draft" button.
  const toggleDraftMode = () => {
    setConfirmingReset(false);
    setDraftMode((d) => !d);
  };

  // Clear a pending Reset Draft confirmation whenever the drafted set empties
  // out from under the confirm UI — e.g. the user un-drafts the last player via
  // the "Drafted" list while the Confirm/Cancel pair is showing. Otherwise the
  // pair lingers as a stale "Confirm Reset (0)" with nothing left to wipe (#737
  // review).
  useEffect(() => {
    if (draftedCount === 0) setConfirmingReset(false);
  }, [draftedCount]);

  // A draft-context switch (different league or scoring format) loads a
  // different board, so drop any confirmation pending on the previous one —
  // otherwise the Confirm/Cancel pair would resurface over a board the user
  // never asked to reset (#737 review).
  useEffect(() => {
    setConfirmingReset(false);
  }, [draftStorageKey]);

  const trimmedSearch = search.trim();

  const groupedByTier = useMemo(() => {
    if (!result) return [] as { label: string; descriptiveLabel?: string; players: GenerateResponse["players"] }[];
    // Position filter and name search compose: a player must satisfy both. The
    // grouping (overall vs positional tier) is still driven solely by the
    // position filter, so a name search never changes how the surviving players
    // are bucketed.
    const query = search.trim().toLowerCase();
    const filtered = result.players.filter((p) => {
      const matchesPosition = filter === "ALL" || p.position === filter;
      const matchesSearch = query === "" || p.name.toLowerCase().includes(query);
      return matchesPosition && matchesSearch;
    });

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
  }, [result, filter, search, tierLabelOverrides]);

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

  // A failed generate must NOT fall through to the empty state below — that copy
  // ("Click Generate…") implies the user never tried and silently swallows the
  // failure (#607). Surface a distinct, announced error affordance with a Retry
  // that re-fires the same request. Checked before `!result` because a failed
  // mutation leaves `result` null.
  if (isError) {
    return (
      <section className="p-6 min-h-0" role="alert">
        <h2 className="text-lg font-semibold mb-3">Tiers</h2>
        <p className="text-sm font-medium text-destructive">
          Couldn't generate your tier list.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          {describeGenerateError(error)}
        </p>
        {onRegenerate && (
          <Button
            onClick={onRegenerate}
            variant="outline"
            size="sm"
            className="mt-3"
            disabled={canRegenerate === false}
          >
            Retry
          </Button>
        )}
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
              confirmingReset ? (
                <>
                  <Button
                    onClick={handleConfirmReset}
                    variant="destructive"
                    size="sm"
                  >
                    Confirm Reset ({draftedCount})
                  </Button>
                  <Button
                    onClick={() => setConfirmingReset(false)}
                    variant="ghost"
                    size="sm"
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  onClick={handleResetDraft}
                  variant="outline"
                  size="sm"
                >
                  Reset Draft
                </Button>
              )
            )}
            <Button
              onClick={toggleDraftMode}
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
        <div className="space-y-2">
          <div className="relative">
            <Input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find a player…"
              aria-label="Find a player"
              // Hide the browser-native type="search" clear (×) — it's absent in
              // Firefox and inconsistently placed elsewhere, so we render our own
              // keyboard-operable Clear search button below instead (#720).
              className="pr-9 [&::-webkit-search-cancel-button]:appearance-none"
            />
            {/* Explicit, always-visible clear control whenever a non-empty query
                still has matches. In the zero-match case the dashed empty-state
                card renders its own "Clear search" button, so the two never
                coexist (keeps a single accessible "clear search" affordance). */}
            {trimmedSearch !== "" && groupedByTier.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
          <PositionFilter value={filter} onChange={setFilter} />
        </div>
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
        {groupedByTier.length === 0 && trimmedSearch !== "" ? (
          // A name search that matches nothing takes precedence over the
          // position empty-state — clearing the search restores the prior view
          // (which may still be position-filtered), mirroring the position
          // filter's "Show all positions" affordance.
          <div className="rounded-md border border-dashed py-8 px-4 text-center">
            <p className="text-sm text-muted-foreground">
              No players match “{trimmedSearch}”.
            </p>
            <Button
              onClick={() => setSearch("")}
              variant="outline"
              size="sm"
              className="mt-3"
            >
              Clear search
            </Button>
          </div>
        ) : groupedByTier.length === 0 && filter !== "ALL" ? (
          <div className="rounded-md border border-dashed py-8 px-4 text-center">
            <p className="text-sm text-muted-foreground">
              No {filter} players in this tier list.
            </p>
            <Button
              onClick={() => setFilter("ALL")}
              variant="outline"
              size="sm"
              className="mt-3"
            >
              Show all positions
            </Button>
          </div>
        ) : (
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
                isFavoritePlayer={isFavoritePlayer}
                isFavoriteTeam={isFavoriteTeam}
              />
            ))}
          </div>
        )}
      </div>
      <div className="border-t bg-card px-6 py-3 flex flex-col items-center gap-2">
        <div className="flex justify-center gap-3">
          <Button
            data-tour="download"
            onClick={handleDownloadXlsx}
            variant="default"
            disabled={xlsxState === "pending"}
            aria-busy={xlsxState === "pending"}
          >
            {xlsxState === "pending" ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            Download Excel
          </Button>
          {debugMode && onDownloadDebugCsv && (
            <Button onClick={onDownloadDebugCsv} variant="outline">
              <Download className="mr-2 h-4 w-4" />
              Download debug CSV
            </Button>
          )}
        </div>
        {xlsxState === "error" && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-center gap-2 text-sm text-destructive"
          >
            <span>Couldn't build the Excel file. Try again — if it keeps failing, check your connection.</span>
            <Button onClick={handleDownloadXlsx} variant="outline" size="sm">
              Retry
            </Button>
          </div>
        )}
        {/* Announce the in-flight build to assistive tech, matching GenerateButton.
            Rendered only while pending so we don't leave an always-present live
            region in the DOM (the staleness banner is a separate role=status
            that may coexist with this while an export is in flight). */}
        {xlsxState === "pending" && (
          <span role="status" aria-live="polite" className="sr-only">
            Building the Excel file…
          </span>
        )}
      </div>
    </section>
  );
}
