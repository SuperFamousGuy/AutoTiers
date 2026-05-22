import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { PositionFilter, type PositionFilterValue } from "./PositionFilter";
import { TierGroup } from "./TierGroup";
import type { GenerateResponse } from "@/api/types";

interface TiersPanelProps {
  result: GenerateResponse | null;
  isPending: boolean;
  onDownloadCsv: () => void;
}

export function TiersPanel({ result, isPending, onDownloadCsv }: TiersPanelProps) {
  const [filter, setFilter] = useState<PositionFilterValue>("ALL");

  const groupedByTier = useMemo(() => {
    if (!result) return [];
    const filtered = filter === "ALL"
      ? result.players
      : result.players.filter((p) => p.position === filter);
    const m = new Map<number, typeof filtered>();
    for (const p of filtered) {
      if (!m.has(p.overall_tier)) m.set(p.overall_tier, []);
      m.get(p.overall_tier)!.push(p);
    }
    return [...m.entries()].sort(([a], [b]) => a - b);
  }, [result, filter]);

  if (isPending) {
    return (
      <section className="p-6 overflow-y-auto">
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
      <section className="p-6">
        <h2 className="text-lg font-semibold mb-3">Tiers</h2>
        <p className="text-sm text-muted-foreground">
          Click Generate to build your tier list.
        </p>
      </section>
    );
  }

  return (
    <section className="p-6 overflow-y-auto space-y-4">
      <h2 className="text-lg font-semibold">Tiers</h2>
      <PositionFilter value={filter} onChange={setFilter} />
      <div className="space-y-4">
        {groupedByTier.map(([tier, players]) => (
          <TierGroup key={tier} tier={tier} players={players} />
        ))}
      </div>
      <Button onClick={onDownloadCsv} variant="outline" className="w-full">
        <Download className="mr-2 h-4 w-4" />
        Download CSV
      </Button>
    </section>
  );
}
