import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { PositionFilter, type PositionFilterValue } from "./PositionFilter";
import { TierGroup } from "./TierGroup";
import { getCustomTierLabel, getPositionalTierLabel } from "@/lib/tiers";
import type { GenerateResponse, ScoringFormat } from "@/api/types";

const SCORING_FORMAT_LABELS: Record<ScoringFormat, string> = {
  standard: "Standard",
  half_ppr: "Half PPR",
  ppr: "PPR",
};

interface TiersPanelProps {
  result: GenerateResponse | null;
  isPending: boolean;
  onDownloadCsv: () => void;
  keepers?: Array<{ player_name: string; position: string; team: string }>;
  scoringFormat?: ScoringFormat;
  tierLabelOverrides?: Partial<Record<number, string>>;
  /** When true, surfaces the dev-only "Download debug CSV" button (?debug=1). */
  debugMode?: boolean;
  onDownloadDebugCsv?: () => void;
}

export function TiersPanel({ result, isPending, onDownloadCsv, keepers, scoringFormat, tierLabelOverrides, debugMode, onDownloadDebugCsv }: TiersPanelProps) {
  const [filter, setFilter] = useState<PositionFilterValue>("ALL");

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
      {keepers && keepers.length > 0 && (
        <div className="border-b px-3 py-2 text-xs text-muted-foreground">
          Excluded Keepers: {keepers.map((k) => k.player_name).join(", ")}
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Tiers</h2>
          <p className="text-xs text-muted-foreground">
            {scoringFormat ? SCORING_FORMAT_LABELS[scoringFormat] : "Standard"} · {result.total ?? result.players.length} players
          </p>
        </div>
        <PositionFilter value={filter} onChange={setFilter} />
        <div className="space-y-4">
          {groupedByTier.map((group) => (
            <TierGroup
              key={group.label}
              label={group.label}
              descriptiveLabel={group.descriptiveLabel}
              players={group.players}
            />
          ))}
        </div>
      </div>
      <div className="border-t bg-card px-6 py-3 flex justify-center gap-3">
        <Button onClick={onDownloadCsv} variant="default">
          <Download className="mr-2 h-4 w-4" />
          Download CSV
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
