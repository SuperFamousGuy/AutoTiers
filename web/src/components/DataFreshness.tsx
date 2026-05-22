import { useDataStatus } from "@/api/hooks";
import { relativeTime, freshnessLevel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function DataFreshness() {
  const { data, isLoading } = useDataStatus();

  if (isLoading) {
    return <span className="text-sm text-muted-foreground">Loading data status…</span>;
  }
  if (!data) {
    return <span className="text-sm text-muted-foreground">Data status unavailable</span>;
  }

  const updates = Object.values(data)
    .map((s) => s.last_updated)
    .filter((v): v is string => v !== null);
  const oldest = updates.length ? updates.reduce((a, b) => (a < b ? a : b)) : null;
  const level = freshnessLevel(oldest);

  const colorClass = {
    fresh: "text-green-600",
    stale: "text-yellow-600",
    old: "text-red-600",
    unknown: "text-muted-foreground",
  }[level];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("text-sm cursor-help", colorClass)}>
            Data updated {relativeTime(oldest)}
          </span>
        </TooltipTrigger>
        <TooltipContent>
          <div className="space-y-1 text-xs">
            {Object.entries(data).map(([source, status]) => (
              <div key={source} className="flex gap-3">
                <span className="font-semibold w-24">{source}</span>
                <span>
                  {status.last_error
                    ? `error: ${status.last_error.slice(0, 60)}`
                    : relativeTime(status.last_updated)}
                </span>
              </div>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
