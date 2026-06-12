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
}

export function MobilePanelTabBar({ active, onChange }: MobilePanelTabBarProps) {
  return (
    <div
      role="tablist"
      aria-label="Panel navigation"
      className="flex w-full border-b bg-card lg:hidden"
    >
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={active === id}
          aria-controls={`panel-${id}`}
          onClick={() => onChange(id)}
          className={cn(
            "flex-1 py-3 text-sm font-medium text-center transition-colors",
            active === id
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
