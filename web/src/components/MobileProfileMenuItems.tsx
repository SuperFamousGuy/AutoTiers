import { DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import type { Profile } from "@/api/types";

interface MobileProfileMenuItemsProps {
  profiles: Profile[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onManage: () => void;
  canCreate: boolean;
}

/**
 * Profile switch/create/manage entries for the mobile hamburger menu.
 *
 * The desktop header renders `ProfilePicker` (a standalone dropdown) inside a
 * `hidden lg:flex` container, so on narrow viewports profile management was
 * unreachable (#499). These items live inside the always-present hamburger
 * menu and are `lg:hidden` so desktop keeps using `ProfilePicker`. They wire
 * to the SAME handlers App passes to `ProfilePicker` — no parallel logic.
 */
export function MobileProfileMenuItems({ profiles, activeId, onSelect, onNew, onManage, canCreate }: MobileProfileMenuItemsProps) {
  return (
    <>
      {profiles.map((p) => (
        <DropdownMenuItem key={p.id} className="lg:hidden" onSelect={() => onSelect(p.id)}>
          {p.id === activeId ? "✓ " : "  "}{p.name}
        </DropdownMenuItem>
      ))}
      <DropdownMenuItem className="lg:hidden" onSelect={onNew} disabled={!canCreate}>
        + New Profile
      </DropdownMenuItem>
      <DropdownMenuItem className="lg:hidden" onSelect={onManage}>
        Manage Profiles…
      </DropdownMenuItem>
      <DropdownMenuSeparator className="lg:hidden" />
    </>
  );
}
