import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type PositionFilterValue = "ALL" | "QB" | "RB" | "WR" | "TE" | "K" | "DST";

/**
 * Canonical position list + ordering. Single source of truth for the filter
 * buttons AND the multi-sheet XLSX export (web/src/lib/xlsx.ts), so the export
 * tabs always mirror the on-screen filter.
 */
export const POSITION_FILTER_OPTIONS: PositionFilterValue[] = ["ALL", "QB", "RB", "WR", "TE", "K", "DST"];

interface PositionFilterProps {
  value: PositionFilterValue;
  onChange: (next: PositionFilterValue) => void;
}

export function PositionFilter({ value, onChange }: PositionFilterProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {POSITION_FILTER_OPTIONS.map((opt) => (
        <Button
          key={opt}
          variant={value === opt ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(opt)}
          className={cn(value === opt && "pointer-events-none")}
        >
          {opt === "ALL" ? "All" : opt}
        </Button>
      ))}
    </div>
  );
}
