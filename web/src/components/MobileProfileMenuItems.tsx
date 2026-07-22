import { DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { MAX_PROFILES, type LocalProfile } from "@/hooks/useLocalProfiles";

interface MobileProfileMenuItemsProps {
  profiles: LocalProfile[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onManage: () => void;
  canCreate: boolean;
  onUndo?: () => void;
  canUndo?: boolean;
}

/**
 * Profile switch/create/manage entries for the mobile hamburger menu.
 *
 * The desktop header renders `ProfilePicker` (a standalone dropdown) inside a
 * `hidden lg:flex` container, so on narrow viewports profile management was
 * unreachable (#499). These items live inside the always-present hamburger
 * menu and are `lg:hidden` so desktop keeps using `ProfilePicker`. They wire
 * to the SAME handlers App passes to `ProfilePicker` — no parallel logic.
 *
 * The "Undo last change" item mirrors the desktop Undo button that sits beside
 * `ProfilePicker`; both call the SAME `handleUndo`/`canUndo` App computes, so a
 * phone user who fat-fingers a settings/rules edit mid-draft can still revert
 * (#726). It renders only when `canUndo` AND `onUndo` are both provided —
 * omitted, not shown disabled, and never a clickable entry that no-ops.
 */
export function MobileProfileMenuItems({ profiles, activeId, onSelect, onNew, onManage, canCreate, onUndo, canUndo }: MobileProfileMenuItemsProps) {
  return (
    <>
      {profiles.map((p) => (
        <DropdownMenuItem key={p.id} className="lg:hidden" onSelect={() => onSelect(p.id)}>
          {p.id === activeId ? "✓ " : "  "}{p.name}
        </DropdownMenuItem>
      ))}
      <DropdownMenuItem
        className="lg:hidden"
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
      <DropdownMenuItem className="lg:hidden" onSelect={onManage}>
        Manage Profiles…
      </DropdownMenuItem>
      {canUndo && onUndo && (
        <DropdownMenuItem className="lg:hidden" onSelect={onUndo}>
          Undo last change
        </DropdownMenuItem>
      )}
      <DropdownMenuSeparator className="lg:hidden" />
    </>
  );
}
