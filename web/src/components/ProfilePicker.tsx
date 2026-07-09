import { Check, ChevronDown } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Profile } from "@/api/types";

interface ProfilePickerProps {
  profiles: Profile[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onManage: () => void;
  canCreate: boolean;
}

export function ProfilePicker({ profiles, activeId, onSelect, onNew, onManage, canCreate }: ProfilePickerProps) {
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
        <DropdownMenuItem onSelect={onNew} disabled={!canCreate}>+ New Profile</DropdownMenuItem>
        <DropdownMenuItem onSelect={onManage}>Manage Profiles…</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
