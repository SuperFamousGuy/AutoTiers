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
  // Mobile-first tap targets: on small screens (live-draft-on-a-phone) the chips
  // are 40px tall with 6px gaps to meet issue #578's >=40px tap-target acceptance
  // criteria; from the `sm` breakpoint up we restore the denser desktop sizing
  // (h-9 / 4px gap).
  return (
    <div className="flex flex-wrap gap-1.5 sm:gap-1">
      {POSITION_FILTER_OPTIONS.map((opt) => (
        <Button
          key={opt}
          variant={value === opt ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(opt)}
          className={cn("h-10 sm:h-9", value === opt && "pointer-events-none")}
        >
          {opt === "ALL" ? "All" : opt}
        </Button>
      ))}
    </div>
  );
}
