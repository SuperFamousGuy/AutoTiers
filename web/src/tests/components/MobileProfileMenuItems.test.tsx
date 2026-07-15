import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileProfileMenuItems } from "@/components/MobileProfileMenuItems";
import { DropdownMenu, DropdownMenuContent } from "@/components/ui/dropdown-menu";

const profiles = [
  { id: "p1", name: "PPR 12-team", settings_json: {}, rules_json: {}, linked_league: null },
  { id: "p2", name: "Standard Keeper", settings_json: {}, rules_json: {}, linked_league: null },
];

// The items rely on a DropdownMenu Root/Content context (radix). Render them
// inside an open menu so the items are mounted, mirroring the hamburger menu.
function renderInMenu(ui: React.ReactNode) {
  return render(
    <DropdownMenu defaultOpen>
      <DropdownMenuContent>{ui}</DropdownMenuContent>
    </DropdownMenu>,
  );
}

describe("MobileProfileMenuItems", () => {
  it("marks the active profile and lists the others", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    expect(screen.getByRole("menuitem", { name: /✓ PPR 12-team/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Standard Keeper/ })).toBeInTheDocument();
  });

  it("calls onSelect with the profile id when a different profile is chosen", async () => {
    const onSelect = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={onSelect} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    await userEvent.setup().click(screen.getByRole("menuitem", { name: /Standard Keeper/ }));
    expect(onSelect).toHaveBeenCalledWith("p2");
  });

  it("calls onNew when + New Profile is chosen", async () => {
    const onNew = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={onNew} onManage={() => {}} canCreate />,
    );
    await userEvent.setup().click(screen.getByRole("menuitem", { name: /\+ New Profile/i }));
    expect(onNew).toHaveBeenCalled();
  });

  it("calls onManage when Manage Profiles is chosen", async () => {
    const onManage = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={onManage} canCreate />,
    );
    await userEvent.setup().click(screen.getByRole("menuitem", { name: /Manage Profiles/i }));
    expect(onManage).toHaveBeenCalled();
  });

  it("disables + New Profile when canCreate is false", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={profiles} activeId="p1" onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate={false} />,
    );
    expect(screen.getByRole("menuitem", { name: /\+ New Profile/i })).toHaveAttribute("data-disabled");
  });

  it("still offers create/manage when the user has no profiles", () => {
    renderInMenu(
      <MobileProfileMenuItems profiles={[]} activeId={null} onSelect={() => {}} onNew={() => {}} onManage={() => {}} canCreate />,
    );
    expect(screen.getByRole("menuitem", { name: /\+ New Profile/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Manage Profiles/i })).toBeInTheDocument();
  });

  it("shows Undo last change and calls onUndo when canUndo is true (#726)", async () => {
    const onUndo = vi.fn();
    renderInMenu(
      <MobileProfileMenuItems
        profiles={profiles}
        activeId="p1"
        onSelect={() => {}}
        onNew={() => {}}
        onManage={() => {}}
        canCreate
        onUndo={onUndo}
        canUndo
      />,
    );
    const undo = screen.getByRole("menuitem", { name: /Undo last change/i });
    expect(undo).toBeInTheDocument();
    await userEvent.setup().click(undo);
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("omits Undo last change entirely when canUndo is false (#726)", () => {
    renderInMenu(
      <MobileProfileMenuItems
        profiles={profiles}
        activeId="p1"
        onSelect={() => {}}
        onNew={() => {}}
        onManage={() => {}}
        canCreate
        onUndo={() => {}}
        canUndo={false}
      />,
    );
    // Absent, not merely disabled.
    expect(screen.queryByRole("menuitem", { name: /Undo last change/i })).toBeNull();
  });
});
