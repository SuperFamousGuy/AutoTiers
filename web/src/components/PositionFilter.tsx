import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type PositionFilterValue = "ALL" | "QB" | "RB" | "WR" | "TE" | "K" | "DST";

const OPTIONS: PositionFilterValue[] = ["ALL", "QB", "RB", "WR", "TE", "K", "DST"];

interface PositionFilterProps {
  value: PositionFilterValue;
  onChange: (next: PositionFilterValue) => void;
}

export function PositionFilter({ value, onChange }: PositionFilterProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {OPTIONS.map((opt) => (
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
