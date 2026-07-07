import { cn } from "@/lib/utils";

export type MobilePanel = "settings" | "rules" | "tiers";

const TABS: { id: MobilePanel; label: string }[] = [
  { id: "settings", label: "Settings" },
  { id: "rules", label: "Rules" },
  { id: "tiers", label: "Tiers" },
];

interface MobilePanelTabBarProps {
  active: MobilePanel;
  onChange: (tab: MobilePanel) => void;
  /**
   * True while a generate mutation is in flight. Drives a busy affordance on the
   * "Tiers" tab (pulsing dot + aria-busy) so a mobile user who taps Generate from
   * another tab knows a result is coming — even if they don't notice the small
   * inline spinner in the header button (#563).
   */
  generateIsPending?: boolean;
}

export function MobilePanelTabBar({ active, onChange, generateIsPending = false }: MobilePanelTabBarProps) {
  return (
    <>
      <div
        role="tablist"
        aria-label="Panel navigation"
        className="flex w-full border-b bg-card lg:hidden"
      >
        {TABS.map(({ id, label }) => {
          const busy = id === "tiers" && generateIsPending;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active === id}
              aria-busy={busy || undefined}
              aria-controls={`panel-${id}`}
              onClick={() => onChange(id)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 py-3 text-sm font-medium text-center transition-colors",
                active === id
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
              {busy && (
                <span
                  aria-hidden="true"
                  data-testid="tiers-busy-indicator"
                  className="h-2 w-2 animate-pulse rounded-full bg-amber-500"
                />
              )}
            </button>
          );
        })}
      </div>
      {/*
        Screen-reader-only live region. The element stays mounted; only its text
        content changes. The message is non-empty only while a generate is pending,
        so the polite announcement fires once when it starts and nothing is
        announced when the text clears on success or error (#563).
      */}
      <span
        aria-live="polite"
        aria-atomic="true"
        data-testid="tiers-live-region"
        className="sr-only"
      >
        {generateIsPending ? "Generating tiers…" : ""}
      </span>
    </>
  );
}
