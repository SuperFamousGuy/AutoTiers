import { Check, ChevronDown } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MAX_PROFILES, type LocalProfile } from "@/hooks/useLocalProfiles";

interface ProfileSwitcherProps {
  profiles: LocalProfile[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onManage: () => void;
  canCreate: boolean;
}

/**
 * Desktop profile switcher — a dropdown backed entirely by localStorage
 * (`useLocalProfiles`). Replaces the deleted server-backed `ProfilePicker`;
 * same trigger label / list / "+ New Profile" affordance so switching profiles
 * doesn't relearn muscle memory, just the data source underneath changed.
 * Rename/delete live in `ProfileManagerDialog`, opened via "Manage Profiles…".
 */
export function ProfileSwitcher({ profiles, activeId, onSelect, onNew, onManage, canCreate }: ProfileSwitcherProps) {
  const active = profiles.find((p) => p.id === activeId);
  const label = active?.name ?? "No profile";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          Profile: {label} <ChevronDown className="ml-2 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        {profiles.map((p) => (
          <DropdownMenuItem
            key={p.id}
            onSelect={() => onSelect(p.id)}
            aria-current={p.id === activeId ? "true" : undefined}
          >
            <Check className={cn("mr-2 h-4 w-4 shrink-0", p.id === activeId ? "opacity-100" : "opacity-0")} />
            {p.name}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={onNew}
          disabled={!canCreate}
          title={canCreate ? undefined : `Profile limit reached (${profiles.length}/${MAX_PROFILES}). Delete one to add another.`}
        >
          + New Profile
          {!canCreate && (
            <span className="ml-1 text-xs text-muted-foreground">
              ({profiles.length}/{MAX_PROFILES} — delete one to add another)
            </span>
          )}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onManage}>Manage Profiles…</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
