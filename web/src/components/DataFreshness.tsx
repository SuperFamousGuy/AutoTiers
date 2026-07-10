import { useDataStatus } from "@/api/hooks";
import { relativeTime, freshnessLevel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function DataFreshness() {
  const { data, isLoading, isError, refetch } = useDataStatus();

  // Three distinct states, checked in precedence order below:
  //  - ERROR  : the fetch failed AND there is no data to fall back on. A hard
  //             failure (retries exhausted, e.g. a CORS misconfig) surfaces a
  //             role="alert" with a Retry affordance instead of masquerading as
  //             the generic "Data status unavailable" span (issue #614). If a
  //             prior fetch already seeded data, react-query keeps it on a failed
  //             refetch — we keep rendering that usable freshness signal.
  //  - LOADING: no data yet AND no error → still in flight.
  //  - UNAVAILABLE: the request succeeded but returned nothing usable — distinct
  //             from a failed request, so it stays a plain non-alert span.
  if (isError && !data) {
    return (
      <span role="alert" className="inline-flex items-center gap-2 text-sm text-destructive">
        Couldn't load data status.
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded bg-primary px-2 py-0.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Retry
        </button>
      </span>
    );
  }
  if (isLoading) {
    return <span className="text-sm text-muted-foreground">Loading data status…</span>;
  }
  if (!data) {
    return <span className="text-sm text-muted-foreground">Data status unavailable</span>;
  }

  const updates = Object.values(data)
    .map((s) => s.last_updated)
    .filter((v): v is string => v !== null);
  const oldest = updates.length ? updates.reduce((a, b) => (Date.parse(a) < Date.parse(b) ? a : b)) : null;
  const level = freshnessLevel(oldest);
  const oldestRelative = relativeTime(oldest);

  const colorClass = {
    fresh: "text-green-600",
    stale: "text-yellow-600",
    old: "text-red-600",
    unknown: "text-muted-foreground",
  }[level];

  const dotClass = {
    fresh: "bg-green-600",
    stale: "bg-yellow-600",
    old: "bg-red-600",
    unknown: "bg-muted-foreground",
  }[level];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {/*
            A real <button> (not a bare <span>) so the indicator joins the tab
            order and Radix's focus-triggered tooltip fires for keyboard and
            screen-reader users. The dot + relative time stay visible at every
            width; the "Data updated" prefix collapses on narrow screens so the
            freshness signal is reachable on mobile without opening a menu.
          */}
          <button
            type="button"
            aria-label={`Data updated ${oldestRelative}`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md text-sm ring-offset-background",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              colorClass,
            )}
          >
            <span aria-hidden="true" className={cn("h-2 w-2 shrink-0 rounded-full", dotClass)} />
            <span className="hidden lg:inline">Data updated&nbsp;</span>
            {oldestRelative}
          </button>
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
